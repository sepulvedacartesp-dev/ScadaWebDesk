from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import asyncpg
from asyncpg.pool import Pool

from .schemas import (
    AlarmEventOut,
    AlarmRuleCreate,
    AlarmRuleOut,
    AlarmRuleUpdate,
    AlarmValueType,
    AlarmOperator,
)


ALLOWED_OPERATORS: set[AlarmOperator] = {"lte", "gte", "eq"}
ALLOWED_VALUE_TYPES: set[AlarmValueType] = {"number", "boolean"}
DEFAULT_PLANTA_ID = "default"

_COLUMN_CACHE: Dict[Tuple[str, str], bool] = {}


async def _table_has_column(pool: Pool, table: str, column: str) -> bool:
    key = (table, column)
    if key in _COLUMN_CACHE:
        return _COLUMN_CACHE[key]
    query = """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = $1
          AND column_name = $2
        LIMIT 1
    """
    async with pool.acquire() as conn:
        exists = await conn.fetchval(query, table, column)
    _COLUMN_CACHE[key] = bool(exists)
    return _COLUMN_CACHE[key]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _record_to_rule(record: asyncpg.Record) -> AlarmRuleOut:
    data = dict(record)
    if not data.get("planta_id"):
        data["planta_id"] = DEFAULT_PLANTA_ID
    return AlarmRuleOut.model_validate(data)


def _record_to_event(record: asyncpg.Record) -> AlarmEventOut:
    data = dict(record)
    if not data.get("planta_id"):
        data["planta_id"] = DEFAULT_PLANTA_ID
    return AlarmEventOut.model_validate(data)


async def list_rules(pool: Pool, empresa_id: str) -> List[AlarmRuleOut]:
    has_planta = await _table_has_column(pool, "alarm_rules", "planta_id")
    query = f"""
        SELECT
            id,
            empresa_id,
            {"planta_id," if has_planta else "NULL AS planta_id,"}
            tag,
            operator,
            threshold_value AS threshold,
            value_type,
            notify_email,
            cooldown_seconds,
            active,
            created_at,
            updated_at,
            last_triggered_at
        FROM alarm_rules
        WHERE empresa_id = $1
        ORDER BY tag ASC, id ASC
        """
    rows = await pool.fetch(query, empresa_id)
    return [_record_to_rule(row) for row in rows]


async def get_rule(pool: Pool, empresa_id: str, rule_id: int) -> Optional[AlarmRuleOut]:
    has_planta = await _table_has_column(pool, "alarm_rules", "planta_id")
    query = f"""
        SELECT
            id,
            empresa_id,
            {"planta_id," if has_planta else "NULL AS planta_id,"}
            tag,
            operator,
            threshold_value AS threshold,
            value_type,
            notify_email,
            cooldown_seconds,
            active,
            created_at,
            updated_at,
            last_triggered_at
        FROM alarm_rules
        WHERE empresa_id = $1
          AND id = $2
        """
    row = await pool.fetchrow(query, empresa_id, rule_id)
    if not row:
        return None
    return _record_to_rule(row)


async def create_rule(pool: Pool, empresa_id: str, payload: AlarmRuleCreate) -> AlarmRuleOut:
    if payload.operator not in ALLOWED_OPERATORS:
        raise ValueError("Operador no soportado")
    if payload.value_type not in ALLOWED_VALUE_TYPES:
        raise ValueError("Tipo de valor no soportado")
    now = _utcnow()
    has_planta = await _table_has_column(pool, "alarm_rules", "planta_id")
    if has_planta:
        row = await pool.fetchrow(
            """
            INSERT INTO alarm_rules (
                empresa_id,
                planta_id,
                tag,
                operator,
                threshold_value,
                value_type,
                notify_email,
                cooldown_seconds,
                active,
                created_at,
                updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10)
            RETURNING
                id,
                empresa_id,
                planta_id,
                tag,
                operator,
                threshold_value AS threshold,
                value_type,
                notify_email,
                cooldown_seconds,
                active,
                created_at,
                updated_at,
                last_triggered_at
            """,
            empresa_id,
            payload.planta_id,
            payload.tag,
            payload.operator,
            payload.threshold,
            payload.value_type,
            str(payload.notify_email),
            payload.cooldown_seconds,
            payload.active,
            now,
        )
    else:
        row = await pool.fetchrow(
            """
            INSERT INTO alarm_rules (
                empresa_id,
                tag,
                operator,
                threshold_value,
                value_type,
                notify_email,
                cooldown_seconds,
                active,
                created_at,
                updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $9)
            RETURNING
                id,
                empresa_id,
                tag,
                operator,
                threshold_value AS threshold,
                value_type,
                notify_email,
                cooldown_seconds,
                active,
                created_at,
                updated_at,
                last_triggered_at
            """,
            empresa_id,
            payload.tag,
            payload.operator,
            payload.threshold,
            payload.value_type,
            str(payload.notify_email),
            payload.cooldown_seconds,
            payload.active,
            now,
        )
    return _record_to_rule(row)


async def update_rule(
    pool: Pool,
    empresa_id: str,
    rule_id: int,
    payload: AlarmRuleUpdate,
) -> Optional[AlarmRuleOut]:
    has_planta = await _table_has_column(pool, "alarm_rules", "planta_id")
    assignments: List[str] = []
    values: List[object] = [empresa_id, rule_id]

    if payload.tag is not None:
        assignments.append(f"tag = ${len(values) + 1}")
        values.append(payload.tag)
    if payload.planta_id is not None and has_planta:
        assignments.append(f"planta_id = ${len(values) + 1}")
        values.append(payload.planta_id)
    if payload.operator is not None:
        if payload.operator not in ALLOWED_OPERATORS:
            raise ValueError("Operador no soportado")
        assignments.append(f"operator = ${len(values) + 1}")
        values.append(payload.operator)
    if payload.threshold is not None:
        assignments.append(f"threshold_value = ${len(values) + 1}")
        values.append(payload.threshold)
    if payload.value_type is not None:
        if payload.value_type not in ALLOWED_VALUE_TYPES:
            raise ValueError("Tipo de valor no soportado")
        assignments.append(f"value_type = ${len(values) + 1}")
        values.append(payload.value_type)
    if payload.notify_email is not None:
        assignments.append(f"notify_email = ${len(values) + 1}")
        values.append(str(payload.notify_email))
    if payload.cooldown_seconds is not None:
        assignments.append(f"cooldown_seconds = ${len(values) + 1}")
        values.append(payload.cooldown_seconds)
    if payload.active is not None:
        assignments.append(f"active = ${len(values) + 1}")
        values.append(payload.active)

    if not assignments:
        row = await get_rule(pool, empresa_id, rule_id)
        return row

    assignments.append(f"updated_at = ${len(values) + 1}")
    values.append(_utcnow())

    query = f"""
        UPDATE alarm_rules
        SET {', '.join(assignments)}
        WHERE empresa_id = $1
          AND id = $2
        RETURNING
            id,
            empresa_id,
            tag,
            operator,
            threshold_value AS threshold,
            value_type,
            notify_email,
            cooldown_seconds,
            active,
            created_at,
            updated_at,
            last_triggered_at
    """
    row = await pool.fetchrow(query, *values)
    if not row:
        return None
    return _record_to_rule(row)


async def delete_rule(pool: Pool, empresa_id: str, rule_id: int) -> bool:
    result = await pool.execute(
        """
        DELETE FROM alarm_rules
        WHERE empresa_id = $1
          AND id = $2
        """,
        empresa_id,
        rule_id,
    )
    return result.endswith("1")


async def list_events(
    pool: Pool,
    empresa_id: str,
    limit: int = 100,
    tag: Optional[str] = None,
) -> List[AlarmEventOut]:
    has_planta = await _table_has_column(pool, "alarm_events", "planta_id")
    clauses = ["empresa_id = $1"]
    values: List[object] = [empresa_id]

    if tag:
        clauses.append(f"tag = ${len(values) + 1}")
        values.append(tag)

    values.append(limit)

    query = f"""
        SELECT
            id,
            rule_id,
            empresa_id,
            {"planta_id," if has_planta else "NULL AS planta_id,"}
            tag,
            observed_value,
            operator,
            threshold_value,
            email_sent,
            email_error,
            triggered_at,
            notified_at
        FROM alarm_events
        WHERE {' AND '.join(clauses)}
        ORDER BY triggered_at DESC
        LIMIT ${len(values)}
    """

    rows = await pool.fetch(query, *values)
    return [_record_to_event(row) for row in rows]


async def insert_event(
    pool: Pool,
    *,
    rule_id: int,
    empresa_id: str,
    planta_id: Optional[str] = None,
    tag: str,
    observed_value: float,
    operator: AlarmOperator,
    threshold_value: float,
    email_sent: bool,
    email_error: Optional[str] = None,
    notified_at: Optional[datetime] = None,
) -> AlarmEventOut:
    has_planta = await _table_has_column(pool, "alarm_events", "planta_id")
    if has_planta:
        query = """
            INSERT INTO alarm_events (
                rule_id,
                empresa_id,
                planta_id,
                tag,
                observed_value,
                operator,
                threshold_value,
                email_sent,
                email_error,
                triggered_at,
                notified_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING
                id,
                rule_id,
                empresa_id,
                planta_id,
                tag,
                observed_value,
                operator,
                threshold_value,
                email_sent,
                email_error,
                triggered_at,
                notified_at
        """
        values = (
            rule_id,
            empresa_id,
            planta_id or DEFAULT_PLANTA_ID,
            tag,
            observed_value,
            operator,
            threshold_value,
            email_sent,
            email_error,
            _utcnow(),
            notified_at,
        )
    else:
        query = """
            INSERT INTO alarm_events (
                rule_id,
                empresa_id,
                tag,
                observed_value,
                operator,
                threshold_value,
                email_sent,
                email_error,
                triggered_at,
                notified_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING
                id,
                rule_id,
                empresa_id,
                tag,
                observed_value,
                operator,
                threshold_value,
                email_sent,
                email_error,
                triggered_at,
                notified_at
        """
        values = (
            rule_id,
            empresa_id,
            tag,
            observed_value,
            operator,
            threshold_value,
            email_sent,
            email_error,
            _utcnow(),
            notified_at,
        )

    row = await pool.fetchrow(query, *values)
    return _record_to_event(row)


async def update_rule_last_triggered(
    pool: Pool,
    rule_id: int,
    triggered_at: datetime,
) -> None:
    await pool.execute(
        """
        UPDATE alarm_rules
        SET last_triggered_at = $2,
            updated_at = $2
        WHERE id = $1
        """,
        rule_id,
        triggered_at,
    )


async def load_active_rules_for_worker(pool: Pool) -> List[asyncpg.Record]:
    has_planta = await _table_has_column(pool, "alarm_rules", "planta_id")
    if has_planta:
        query = """
            SELECT
                id,
                empresa_id,
                planta_id,
                tag,
                operator,
                threshold_value,
                value_type,
                notify_email,
                cooldown_seconds,
                active,
                last_triggered_at
            FROM alarm_rules
            WHERE active = TRUE
        """
    else:
        query = """
            SELECT
                id,
                empresa_id,
                NULL AS planta_id,
                tag,
                operator,
                threshold_value,
                value_type,
                notify_email,
                cooldown_seconds,
                active,
                last_triggered_at
            FROM alarm_rules
            WHERE active = TRUE
        """
    rows: List[asyncpg.Record] = await pool.fetch(query)
    return rows
