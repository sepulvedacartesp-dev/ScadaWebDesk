from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from asyncpg.pool import Pool

from alarms import service as alarm_service
from alarms.schemas import AlarmOperator

try:
    from .emailer import EmailNotifier
except ImportError:
    from emailer import EmailNotifier  # type: ignore


DEFAULT_PLANTA_ID = os.environ.get("DEFAULT_PLANTA_ID", "default")


@dataclass(slots=True)
class TrendPoint:
    empresa_id: str
    planta_id: str
    tag: str
    value: float
    timestamp: datetime


@dataclass(slots=True)
class AlarmRuleState:
    id: int
    empresa_id: str
    planta_id: str
    tag: str
    operator: AlarmOperator
    threshold_value: float
    value_type: str
    notify_email: str
    cooldown_seconds: int
    active: bool
    last_triggered_at: Optional[datetime] = None
    last_notified_at: Optional[datetime] = None

    def is_triggered(self, observed_value: float) -> bool:
        if self.operator == "gte":
            return observed_value >= self.threshold_value
        if self.operator == "lte":
            return observed_value <= self.threshold_value
        if self.operator == "eq":
            return observed_value == self.threshold_value
        return False

    def cooldown_remaining(self, now: datetime) -> Optional[timedelta]:
        if not self.last_notified_at:
            return None
        delta = now - self.last_notified_at
        remaining_seconds = self.cooldown_seconds - delta.total_seconds()
        if remaining_seconds > 0:
            return timedelta(seconds=remaining_seconds)
        return None


class AlarmEngine:
    def __init__(
        self,
        pool: Pool,
        notifier: EmailNotifier,
        *,
        refresh_seconds: int = 60,
        queue_maxsize: int = 1024,
        logger: Optional[logging.Logger] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self._pool = pool
        self._notifier = notifier
        self._refresh_seconds = max(5, refresh_seconds)
        self._queue: asyncio.Queue[TrendPoint] = asyncio.Queue(maxsize=queue_maxsize)
        self._logger = logger or logging.getLogger("alarm-engine")
        self._rules: Dict[int, AlarmRuleState] = {}
        self._rules_by_topic: Dict[Tuple[str, str, str], List[AlarmRuleState]] = defaultdict(list)
        self._consumer_task: Optional[asyncio.Task] = None
        self._refresh_task: Optional[asyncio.Task] = None
        self._pending_triggers: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        self._closed = False
        self._loop = loop

    async def start(self) -> None:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        await self._load_rules()
        loop = self._loop
        self._consumer_task = loop.create_task(self._consume())
        self._refresh_task = loop.create_task(self._refresh_loop())
        self._logger.info(
            "Motor de alarmas iniciado con %d reglas activas",
            len(self._rules),
        )

    async def stop(self) -> None:
        self._closed = True
        tasks_to_wait: List[asyncio.Task] = []
        if self._refresh_task:
            self._refresh_task.cancel()
            tasks_to_wait.append(self._refresh_task)
        if self._consumer_task:
            self._consumer_task.cancel()
            tasks_to_wait.append(self._consumer_task)
        tasks_to_wait.extend(self._pending_triggers)
        for task in tasks_to_wait:
            try:
                await task
            except asyncio.CancelledError:
                continue
            except Exception as exc:  # noqa: BLE001
                self._logger.error("Tarea pendiente fallo durante stop: %s", exc)
        self._pending_triggers.clear()

    def submit_point(self, point: TrendPoint) -> None:
        loop = self._loop
        if self._closed or loop is None or loop.is_closed():
            return

        def _enqueue() -> None:
            if self._closed:
                return
            try:
                self._queue.put_nowait(point)
            except asyncio.QueueFull:
                self._logger.warning(
                    "Cola de alarmas llena; descartando punto %s, empresa %s",
                    point.tag,
                    point.empresa_id,
                )

        loop.call_soon_threadsafe(_enqueue)

    async def _refresh_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._refresh_seconds)
                await self._load_rules()
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            self._logger.error("Error refrescando reglas de alarma: %s", exc)

    async def _load_rules(self) -> None:
        async with self._lock:
            records = await alarm_service.load_active_rules_for_worker(self._pool)
            new_rules: Dict[int, AlarmRuleState] = {}
            new_rules_by_topic: Dict[Tuple[str, str, str], List[AlarmRuleState]] = defaultdict(list)

            for record in records:
                data = dict(record)
                rule_id = int(data["id"])
                existing = self._rules.get(rule_id)
                planta_id = str(data.get("planta_id") or DEFAULT_PLANTA_ID)
                state = AlarmRuleState(
                    id=rule_id,
                    empresa_id=str(data["empresa_id"]),
                    planta_id=planta_id,
                    tag=str(data["tag"]),
                    operator=str(data["operator"]),
                    threshold_value=float(data["threshold_value"]),
                    value_type=str(data["value_type"]),
                    notify_email=str(data["notify_email"]),
                    cooldown_seconds=int(data["cooldown_seconds"]),
                    active=bool(data["active"]),
                    last_triggered_at=data.get("last_triggered_at"),
                    last_notified_at=existing.last_notified_at if existing else None,
                )
                new_rules[rule_id] = state
                new_rules_by_topic[(state.empresa_id, state.planta_id, state.tag)].append(state)

            self._rules = new_rules
            self._rules_by_topic = new_rules_by_topic
            self._logger.info(
                "Reglas de alarma sincronizadas: %d activas, %d topics",
                len(self._rules),
                len(self._rules_by_topic),
            )

    async def _consume(self) -> None:
        try:
            while True:
                point = await self._queue.get()
                try:
                    await self._process_point(point)
                except Exception as exc:  # noqa: BLE001
                    self._logger.error("Error procesando punto %s/%s: %s", point.empresa_id, point.tag, exc)
                finally:
                    self._queue.task_done()
        except asyncio.CancelledError:
            return

    async def _process_point(self, point: TrendPoint) -> None:
        key = (point.empresa_id, point.planta_id or DEFAULT_PLANTA_ID, point.tag)
        rules = self._rules_by_topic.get(key)
        if not rules:
            return
        for rule in list(rules):
            if not rule.active:
                continue
            if not rule.is_triggered(point.value):
                continue
            task = asyncio.create_task(self._handle_trigger(rule, point))
            task.add_done_callback(self._pending_triggers.discard)
            self._pending_triggers.add(task)

    async def _handle_trigger(self, rule: AlarmRuleState, point: TrendPoint) -> None:
        triggered_at = datetime.now(timezone.utc)
        cooldown_remaining = rule.cooldown_remaining(triggered_at)
        email_sent = False
        email_error: Optional[str] = None
        notified_at: Optional[datetime] = None

        if cooldown_remaining:
            email_error = f"Cooldown activo ({int(cooldown_remaining.total_seconds())}s restantes)"
        else:
            email_sent, email_error = await self._notifier.send_alarm(
                empresa_id=rule.empresa_id,
                planta_id=rule.planta_id,
                tag=rule.tag,
                operator=rule.operator,
                threshold_value=rule.threshold_value,
                observed_value=point.value,
                triggered_at=triggered_at,
                recipient=rule.notify_email,
            )
            if email_sent:
                notified_at = triggered_at
                rule.last_notified_at = triggered_at

        try:
            await alarm_service.insert_event(
                self._pool,
                rule_id=rule.id,
                empresa_id=rule.empresa_id,
                planta_id=rule.planta_id,
                tag=rule.tag,
                observed_value=point.value,
                operator=rule.operator,
                threshold_value=rule.threshold_value,
                email_sent=email_sent,
                email_error=email_error,
                notified_at=notified_at,
            )
            await alarm_service.update_rule_last_triggered(self._pool, rule.id, triggered_at)
        except Exception as exc:  # noqa: BLE001
            self._logger.error("No se pudo registrar evento de alarma %s: %s", rule.id, exc)
