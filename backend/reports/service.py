from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import asyncpg
from asyncpg.pool import Pool

from .schemas import (
    ReportCreatePayload,
    ReportDefinitionOut,
    ReportRunOut,
    ReportRunRequest,
    ReportStatus,
    ReportUpdatePayload,
)

DEFAULT_PLANTA_ID = "default"
MAX_REPORTS_PER_PLANT = 2
ALLOWED_STATUSES: Set[ReportStatus] = {"idle", "queued", "running", "success", "failed", "skipped"}
DEFAULT_MAX_POINTS = 400


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time_of_day(value: Optional[str]) -> Optional[time]:
    if not value:
        return None
    parts = str(value).split(":")
    if len(parts) < 2:
        raise ValueError("timeOfDay invalido; usa HH:MM")
    hours = int(parts[0])
    minutes = int(parts[1])
    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
        raise ValueError("timeOfDay debe estar entre 00:00 y 23:59")
    return time(hour=hours, minute=minutes)


def _time_to_label(value: Optional[time]) -> Optional[str]:
    if value is None:
        return None
    return value.strftime("%H:%M")


def _record_to_definition(record: asyncpg.Record) -> ReportDefinitionOut:
    data = dict(record)
    data["planta_id"] = data.get("planta_id") or DEFAULT_PLANTA_ID
    data["time_of_day"] = _time_to_label(data.get("time_of_day"))
    data["recipients"] = data.get("recipients") or []
    data["tags"] = data.get("tags") or []
    return ReportDefinitionOut.model_validate(data)


def _record_to_run(record: asyncpg.Record) -> ReportRunOut:
    data = dict(record)
    data["planta_id"] = data.get("planta_id") or DEFAULT_PLANTA_ID
    data["emails_sent"] = data.get("emails_sent") or []
    return ReportRunOut.model_validate(data)


async def _used_slots(pool: Pool, empresa_id: str, planta_id: str, exclude_report_id: Optional[int] = None) -> Set[int]:
    query = """
        SELECT slot
        FROM report_definitions
        WHERE empresa_id = $1
          AND planta_id = $2
          {exclude_clause}
    """
    exclude_clause = ""
    params: List[object] = [empresa_id, planta_id]
    if exclude_report_id is not None:
        exclude_clause = "AND id <> $3"
        params.append(exclude_report_id)
    query = query.format(exclude_clause=exclude_clause)
    rows = await pool.fetch(query, *params)
    return {int(row["slot"]) for row in rows if row and row.get("slot") is not None}


async def _resolve_slot(
    pool: Pool, empresa_id: str, planta_id: str, requested_slot: Optional[int], exclude_report_id: Optional[int] = None
) -> int:
    used = await _used_slots(pool, empresa_id, planta_id, exclude_report_id=exclude_report_id)
    if len(used) >= MAX_REPORTS_PER_PLANT:
        raise ValueError("Solo se permiten 2 reportes por planta")
    if requested_slot is not None:
        if requested_slot not in {1, 2}:
            raise ValueError("slot debe ser 1 o 2")
        if requested_slot in used:
            raise ValueError("El slot seleccionado ya esta en uso en esta planta")
        return requested_slot
    for candidate in range(1, MAX_REPORTS_PER_PLANT + 1):
        if candidate not in used:
            return candidate
    raise ValueError("No hay slots disponibles para esta planta")


async def list_definitions(pool: Pool, empresa_id: str, plantas: Optional[Sequence[str]] = None) -> List[ReportDefinitionOut]:
    base_query = """
        SELECT
            id,
            empresa_id,
            planta_id,
            name,
            frequency,
            day_of_week,
            day_of_month,
            time_of_day,
            timezone,
            include_alarms,
            send_email,
            format,
            recipients,
            tags,
            slot,
            active,
            last_run_at,
            next_run_at,
            last_status,
            last_error,
            created_at,
            updated_at
        FROM report_definitions
        WHERE empresa_id = $1
        {planta_clause}
        ORDER BY planta_id ASC, slot ASC, id ASC
    """
    params: List[object] = [empresa_id]
    if plantas:
        base_query = base_query.format(planta_clause="AND planta_id = ANY($2)")
        params.append(list(plantas))
    else:
        base_query = base_query.format(planta_clause="")
    rows = await pool.fetch(base_query, *params)
    return [_record_to_definition(row) for row in rows]


async def get_definition(pool: Pool, empresa_id: str, report_id: int) -> Optional[ReportDefinitionOut]:
    query = """
        SELECT
            id,
            empresa_id,
            planta_id,
            name,
            frequency,
            day_of_week,
            day_of_month,
            time_of_day,
            timezone,
            include_alarms,
            send_email,
            format,
            recipients,
            tags,
            slot,
            active,
            last_run_at,
            next_run_at,
            last_status,
            last_error,
            created_at,
            updated_at
        FROM report_definitions
        WHERE empresa_id = $1
          AND id = $2
    """
    row = await pool.fetchrow(query, empresa_id, report_id)
    if not row:
        return None
    return _record_to_definition(row)


async def create_definition(pool: Pool, empresa_id: str, payload: ReportCreatePayload) -> ReportDefinitionOut:
    slot = await _resolve_slot(pool, empresa_id, payload.planta_id, payload.slot)
    now = _now_utc()
    time_of_day = _parse_time_of_day(payload.time_of_day) if payload.time_of_day else None
    query = """
        INSERT INTO report_definitions (
            empresa_id,
            planta_id,
            name,
            frequency,
            day_of_week,
            day_of_month,
            time_of_day,
            timezone,
            include_alarms,
            send_email,
            format,
            recipients,
            tags,
            slot,
            active,
            last_status,
            created_at,
            updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
        )
        RETURNING *
    """
    row = await pool.fetchrow(
        query,
        empresa_id,
        payload.planta_id,
        payload.name,
        payload.frequency,
        payload.day_of_week,
        payload.day_of_month,
        time_of_day,
        payload.timezone,
        payload.include_alarms,
        payload.send_email,
        "pdf",
        payload.recipients,
        payload.tags,
        slot,
        payload.active,
        "idle",
        now,
        now,
    )
    return _record_to_definition(row)


async def update_definition(pool: Pool, empresa_id: str, report_id: int, payload: ReportUpdatePayload) -> Optional[ReportDefinitionOut]:
    current = await get_definition(pool, empresa_id, report_id)
    if not current:
        return None
    target_planta = payload.planta_id or current.planta_id
    target_slot = payload.slot if payload.slot is not None else current.slot
    slot = await _resolve_slot(pool, empresa_id, target_planta, target_slot, exclude_report_id=report_id)

    fields = []
    values: List[object] = []

    def add(field: str, value):
        values.append(value)
        fields.append(f"{field} = ${len(values)}")

    if payload.name is not None:
        add("name", payload.name)
    if payload.frequency is not None:
        add("frequency", payload.frequency)
    if payload.day_of_week is not None or (payload.frequency == "weekly" and current.day_of_week is None):
        add("day_of_week", payload.day_of_week)
    if payload.day_of_month is not None or (payload.frequency == "monthly" and current.day_of_month is None):
        add("day_of_month", payload.day_of_month)
    if payload.time_of_day is not None:
        add("time_of_day", _parse_time_of_day(payload.time_of_day))
    if payload.timezone is not None:
        add("timezone", payload.timezone)
    if payload.include_alarms is not None:
        add("include_alarms", payload.include_alarms)
    if payload.send_email is not None:
        add("send_email", payload.send_email)
    if payload.recipients is not None:
        add("recipients", payload.recipients)
    if payload.tags is not None:
        add("tags", payload.tags)
    if target_planta != current.planta_id:
        add("planta_id", target_planta)
    if slot != current.slot:
        add("slot", slot)
    if payload.active is not None:
        add("active", payload.active)

    add("updated_at", _now_utc())

    if not fields:
        return current

    set_clause = ", ".join(fields)
    query = f"""
        UPDATE report_definitions
        SET {set_clause}
        WHERE empresa_id = ${len(values) + 1}
          AND id = ${len(values) + 2}
        RETURNING *
    """
    values.extend([empresa_id, report_id])
    row = await pool.fetchrow(query, *values)
    if not row:
        return None
    return _record_to_definition(row)


async def delete_definition(pool: Pool, empresa_id: str, report_id: int) -> bool:
    query = """
        DELETE FROM report_definitions
        WHERE empresa_id = $1
          AND id = $2
    """
    result = await pool.execute(query, empresa_id, report_id)
    return result and result.lower().startswith("delete")


def _resolve_timezone(tz_name: Optional[str]) -> timezone:
    if not tz_name:
        return timezone.utc
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return timezone.utc


def _previous_day_window(now_local: datetime) -> Tuple[datetime, datetime]:
    start_local = (now_local - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return start_local, end_local


def _previous_week_window(now_local: datetime) -> Tuple[datetime, datetime]:
    weekday = now_local.weekday()  # 0=Monday
    start_of_week = now_local - timedelta(days=weekday + 7)
    start_local = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=7)
    return start_local, end_local


def _previous_month_window(now_local: datetime) -> Tuple[datetime, datetime]:
    first_this_month = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_last_day = first_this_month - timedelta(days=1)
    start_local = last_month_last_day.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_local = first_this_month
    return start_local, end_local


def compute_default_window(definition: ReportDefinitionOut, reference_utc: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    ref = reference_utc or _now_utc()
    tz = _resolve_timezone(definition.timezone) if getattr(definition, "timezone", None) else timezone.utc
    local_now = ref.astimezone(tz)
    if definition.frequency == "monthly":
        start_local, end_local = _previous_month_window(local_now)
    elif definition.frequency == "weekly":
        start_local, end_local = _previous_week_window(local_now)
    else:
        start_local, end_local = _previous_day_window(local_now)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


async def create_run(
    pool: Pool,
    empresa_id: str,
    report_id: int,
    definition: Optional[ReportDefinitionOut],
    request: Optional[ReportRunRequest],
    triggered_by: Optional[str],
) -> ReportRunOut:
    if definition is None:
        current = await get_definition(pool, empresa_id, report_id)
        if current is None:
            raise ValueError("Reporte no encontrado")
        definition = current
    window_start: Optional[datetime] = request.window_start if request else None
    window_end: Optional[datetime] = request.window_end if request else None
    if window_start and window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)
    if window_end and window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=timezone.utc)
    if not window_start or not window_end:
        window_start, window_end = compute_default_window(definition)

    query = """
        INSERT INTO report_runs (
            report_id,
            empresa_id,
            planta_id,
            status,
            window_start,
            window_end,
            started_at,
            send_email,
            emails_sent,
            triggered_by
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10
        )
        RETURNING *
    """
    row = await pool.fetchrow(
        query,
        report_id,
        empresa_id,
        definition.planta_id,
        "queued",
        window_start,
        window_end,
        _now_utc(),
        request.send_email if request is not None else True,
        [] if request is None or request.send_email else [],
        triggered_by,
    )
    try:
        await pool.execute(
            """
            UPDATE report_definitions
            SET last_status = $1,
                last_run_at = $2,
                updated_at = $2
            WHERE empresa_id = $3
              AND id = $4
            """,
            "queued",
            row["started_at"],
            empresa_id,
            report_id,
        )
    except Exception:
        # No bloquear la creacion del run por fallos en este update
        pass
    return _record_to_run(row)


async def list_runs(pool: Pool, empresa_id: str, report_id: int, limit: int = 20) -> List[ReportRunOut]:
    query = """
        SELECT
            id,
            report_id,
            empresa_id,
            planta_id,
            status,
            window_start,
            window_end,
            started_at,
            completed_at,
            error,
            send_email,
            emails_sent,
            pdf_size_bytes,
            pdf_mime,
            triggered_by
        FROM report_runs
        WHERE empresa_id = $1
          AND report_id = $2
        ORDER BY started_at DESC, id DESC
        LIMIT $3
    """
    rows = await pool.fetch(query, empresa_id, report_id, max(1, min(limit, 200)))
    return [_record_to_run(row) for row in rows]


async def update_run_status(
    pool: Pool,
    run_id: int,
    status: ReportStatus,
    *,
    error: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
    emails_sent: Optional[List[str]] = None,
) -> Optional[ReportRunOut]:
    if status not in ALLOWED_STATUSES:
        raise ValueError("Estado de reporte no soportado")
    set_fields = ["status = $1", "completed_at = $2"]
    values: List[object] = [status, _now_utc()]
    if error is not None:
        set_fields.append("error = $3")
        values.append(error)
    if emails_sent is not None:
        set_fields.append("emails_sent = ${}".format(len(values) + 1))
        values.append(emails_sent)
    if pdf_bytes is not None:
        set_fields.append("pdf_blob = ${}".format(len(values) + 1))
        values.append(pdf_bytes)
        set_fields.append("pdf_size_bytes = ${}".format(len(values) + 1))
        values.append(len(pdf_bytes))
    set_clause = ", ".join(set_fields)
    query = f"""
        UPDATE report_runs
        SET {set_clause}
        WHERE id = ${len(values) + 1}
        RETURNING *
    """
    values.append(run_id)
    row = await pool.fetchrow(query, *values)
    if not row:
        return None
    return _record_to_run(row)


async def fetch_run(pool: Pool, run_id: int) -> Optional[ReportRunOut]:
    query = """
        SELECT
            id,
            report_id,
            empresa_id,
            planta_id,
            status,
            window_start,
            window_end,
            started_at,
            completed_at,
            error,
            send_email,
            emails_sent,
            pdf_size_bytes,
            pdf_mime,
            triggered_by
        FROM report_runs
        WHERE id = $1
    """
    row = await pool.fetchrow(query, run_id)
    if not row:
        return None
    return _record_to_run(row)


async def fetch_trend_series(
    pool: Pool,
    *,
    empresa_id: str,
    planta_id: str,
    tags: Sequence[str],
    start: datetime,
    end: datetime,
    max_points: int = DEFAULT_MAX_POINTS,
) -> List[Dict[str, Any]]:
    if not tags:
        return []
    total_seconds = max(1, int((end - start).total_seconds()))
    bucket = max(1, int(total_seconds / max(1, min(max_points, 1000))))
    results: List[Dict[str, Any]] = []
    async with pool.acquire() as conn:
        for tag in tags:
            stats_query = """
                SELECT
                    COUNT(*) OVER () AS count,
                    MIN(valor) OVER () AS min_value,
                    MAX(valor) OVER () AS max_value,
                    AVG(valor) OVER () AS avg_value,
                    FIRST_VALUE(valor) OVER (ORDER BY timestamp DESC) AS latest_value,
                    FIRST_VALUE(timestamp) OVER (ORDER BY timestamp DESC) AS latest_timestamp
                FROM trends
                WHERE empresa_id = $1
                  AND planta_id = $2
                  AND tag = $3
                  AND timestamp BETWEEN $4 AND $5
                ORDER BY timestamp DESC
                LIMIT 1
            """
            stats_row = await conn.fetchrow(stats_query, empresa_id, planta_id, tag, start, end)
            if stats_row is None or not stats_row["count"]:
                results.append({"tag": tag, "points": [], "stats": None})
                continue
            data_query = """
                SELECT to_timestamp(floor(extract(epoch FROM timestamp)/$6)*$6) AS bucket,
                       AVG(valor) AS value
                FROM trends
                WHERE empresa_id = $1
                  AND planta_id = $2
                  AND tag = $3
                  AND timestamp BETWEEN $4 AND $5
                GROUP BY bucket
                ORDER BY bucket ASC
                LIMIT $7
            """
            rows = await conn.fetch(
                data_query,
                empresa_id,
                planta_id,
                tag,
                start,
                end,
                bucket,
                max_points,
            )
            points = [{"timestamp": row["bucket"], "value": float(row["value"])} for row in rows]
            stats = {
                "latest": float(stats_row["latest_value"]) if stats_row["latest_value"] is not None else None,
                "min": float(stats_row["min_value"]) if stats_row["min_value"] is not None else None,
                "max": float(stats_row["max_value"]) if stats_row["max_value"] is not None else None,
                "avg": float(stats_row["avg_value"]) if stats_row["avg_value"] is not None else None,
                "latestTimestamp": stats_row["latest_timestamp"],
                "count": int(stats_row["count"]),
            }
            results.append({"tag": tag, "points": points, "stats": stats})
    return results


async def fetch_alarm_events(
    pool: Pool,
    *,
    empresa_id: str,
    planta_id: str,
    start: datetime,
    end: datetime,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    query = """
        SELECT
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
        FROM alarm_events
        WHERE empresa_id = $1
          AND planta_id = $2
          AND triggered_at BETWEEN $3 AND $4
        ORDER BY triggered_at DESC
        LIMIT $5
    """
    rows = await pool.fetch(query, empresa_id, planta_id, start, end, max(1, min(limit, 500)))
    events: List[Dict[str, Any]] = []
    for row in rows:
        events.append(
            {
                "id": row["id"],
                "rule_id": row["rule_id"],
                "tag": row["tag"],
                "observed": row["observed_value"],
                "operator": row["operator"],
                "threshold": row["threshold_value"],
                "email_sent": row["email_sent"],
                "email_error": row["email_error"],
                "triggered_at": row["triggered_at"],
                "notified_at": row["notified_at"],
            }
        )
    return events
