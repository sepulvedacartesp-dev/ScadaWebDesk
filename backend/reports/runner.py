from __future__ import annotations

import asyncio
import io
import math
import os
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import List, Optional, Sequence, Tuple

import aiosmtplib
import asyncpg
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from reports.schemas import ReportDefinitionOut, ReportRunOut, ReportStatus
from reports import service as report_service


def _tz_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _load_definition(pool: asyncpg.pool.Pool, empresa_id: str, report_id: int) -> ReportDefinitionOut:
    definition = await report_service.get_definition(pool, empresa_id, report_id)
    if not definition:
        raise ValueError("Reporte no encontrado")
    return definition


def _build_pdf(
    definition: ReportDefinitionOut,
    run: ReportRunOut,
    series: Sequence[dict],
    alarms: Sequence[dict],
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        title=f"Reporte {definition.name}",
        author="SCADA SurNex",
    )
    styles = getSampleStyleSheet()
    elements: List[object] = []
    elements.append(Paragraph(f"<b>{definition.name}</b>", styles["Title"]))
    elements.append(
        Paragraph(
            f"Empresa: {definition.empresa_id} | Planta: {definition.planta_id} | Frecuencia: {definition.frequency}",
            styles["Normal"],
        )
    )
    elements.append(
        Paragraph(
            f"Ventana: {run.window_start} a {run.window_end} | Destinatarios: {', '.join(definition.recipients)}",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 0.3 * cm))

    for item in series:
        tag = item.get("tag", "")
        stats = item.get("stats") or {}
        points = item.get("points") or []
        elements.append(Paragraph(f"<b>Tag:</b> {tag}", styles["Heading3"]))
        stats_table = Table(
            [
                ["Min", "Max", "Promedio", "Ultimo", "Muestras"],
                [
                    f"{stats.get('min') if stats else '--'}",
                    f"{stats.get('max') if stats else '--'}",
                    f"{stats.get('avg') if stats else '--'}",
                    f"{stats.get('latest') if stats else '--'}",
                    f"{len(points)}",
                ],
            ],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            ),
        )
        elements.append(stats_table)
        if points:
            condensed = _condense_points(points, 80)
            spark_data = " ".join(_sparkline(condensed))
            elements.append(Paragraph(f"Sparklines: {spark_data}", styles["Code"]))
        elements.append(Spacer(1, 0.2 * cm))

    elements.append(Spacer(1, 0.3 * cm))
    elements.append(Paragraph("<b>Alarmas notificadas</b>", styles["Heading2"]))
    if alarms:
        elements.append(Paragraph(f"Total en ventana: {len(alarms)}", styles["Normal"]))
        table_data = [["Tag", "Umbral", "Valor", "Operador", "Correo", "Fecha", "Estado correo"]]
        for event in alarms:
            table_data.append(
                [
                    event.get("tag", "--"),
                    str(event.get("threshold", "--")),
                    str(event.get("observed", "--")),
                    str(event.get("operator", "--")),
                    "Enviado" if event.get("email_sent") else "No enviado",
                    str(event.get("triggered_at")),
                    event.get("email_error") or "",
                ]
            )
        alarm_table = Table(
            table_data,
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            ),
        )
        elements.append(alarm_table)
    else:
        elements.append(Paragraph("Sin alarmas notificadas en la ventana seleccionada.", styles["Normal"]))

    doc.build(elements)
    return buffer.getvalue()


def _sparkline(values: Sequence[float]) -> List[str]:
    ticks = " .:-=+*#%"
    if not values:
        return []
    lo, hi = min(values), max(values)
    if math.isclose(lo, hi):
        return [ticks[0]] * len(values)
    span = hi - lo
    result: List[str] = []
    for v in values:
        idx = int((v - lo) / span * (len(ticks) - 1))
        result.append(ticks[idx])
    return result


def _condense_points(points: Sequence[dict], target: int) -> List[float]:
    if not points:
        return []
    if len(points) <= target:
        return [p.get("value") for p in points]
    step = max(1, len(points) // target)
    condensed = []
    for i in range(0, len(points), step):
        batch = points[i : i + step]
        avg = sum(p.get("value", 0) for p in batch) / len(batch)
        condensed.append(avg)
    return condensed


def _load_email_settings() -> Optional[dict]:
    def pick(*keys: str) -> str:
        for key in keys:
            val = os.environ.get(key)
            if val and str(val).strip():
                return str(val).strip()
        return ""

    host = pick("ALARM_SMTP_HOST", "SMTP_HOST", "MAIL_HOST")
    username = pick("ALARM_SMTP_USERNAME", "ALARM_SMTP_USER", "SMTP_USERNAME", "SMTP_USER", "MAIL_USER")
    password = pick("ALARM_SMTP_PASSWORD", "ALARM_SMTP_PASS", "SMTP_PASSWORD", "MAIL_PASSWORD")
    if not host or not username or not password:
        return None
    return {
        "host": host,
        "port": int(os.environ.get("ALARM_SMTP_PORT") or os.environ.get("SMTP_PORT") or 587),
        "username": username,
        "password": password,
        "from_address": (os.environ.get("ALARM_EMAIL_FROM") or os.environ.get("SMTP_FROM") or "notificaciones@surnex.cl").strip(),
        "from_name": (os.environ.get("ALARM_EMAIL_FROM_NAME") or os.environ.get("SMTP_FROM_NAME") or "").strip() or None,
        "use_starttls": (os.environ.get("ALARM_SMTP_STARTTLS") or os.environ.get("SMTP_STARTTLS") or "1").lower() not in {"0", "false", "no"},
        "use_tls": (os.environ.get("ALARM_SMTP_USE_SSL") or os.environ.get("SMTP_USE_SSL") or "0").lower() in {"1", "true", "yes"},
        "timeout": float(os.environ.get("ALARM_SMTP_TIMEOUT") or os.environ.get("SMTP_TIMEOUT") or 10.0),
        "subject_prefix": (os.environ.get("ALARM_EMAIL_SUBJECT_PREFIX") or "[Reporte SCADA]").strip(),
        "reply_to": (os.environ.get("ALARM_EMAIL_REPLY_TO") or os.environ.get("SMTP_REPLY_TO") or "").strip() or None,
        "tz_name": (os.environ.get("ALARM_EMAIL_TZ") or "").strip() or None,
    }


async def _send_report_email(
    smtp_settings: dict,
    definition: ReportDefinitionOut,
    pdf_bytes: bytes,
    run: ReportRunOut,
) -> List[str]:
    sent: List[str] = []
    subject = f"[Reporte SCADA] {definition.empresa_id}/{definition.planta_id} - {definition.name}"
    body_lines = [
        f"Se adjunta el reporte generado para {definition.name}.",
        f"Ventana: {run.window_start} a {run.window_end}",
        "",
        "Este correo fue generado automaticamente.",
    ]
    for recipient in definition.recipients:
        msg = EmailMessage()
        from_name = smtp_settings.get("from_name")
        sender = smtp_settings["from_address"]
        msg["From"] = f"{from_name} <{sender}>" if from_name else sender
        msg["To"] = recipient
        msg["Subject"] = subject
        if smtp_settings.get("reply_to"):
            msg["Reply-To"] = smtp_settings["reply_to"]
        msg.set_content("\n".join(body_lines))
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=f"{definition.name}.pdf")
        try:
            await aiosmtplib.send(
                msg,
                hostname=smtp_settings["host"],
                port=smtp_settings["port"],
                username=smtp_settings["username"],
                password=smtp_settings["password"],
                start_tls=smtp_settings.get("use_starttls", True),
                use_tls=smtp_settings.get("use_tls", False),
                timeout=smtp_settings.get("timeout", 10.0),
            )
            sent.append(recipient)
        except Exception:
            continue
    return sent


async def execute_run(
    pool: asyncpg.pool.Pool,
    *,
    run: ReportRunOut,
    definition: ReportDefinitionOut,
) -> Tuple[ReportStatus, Optional[bytes], List[str], Optional[str]]:
    now = datetime.now(timezone.utc)
    start = _tz_aware(run.window_start or now)
    end = _tz_aware(run.window_end or now)
    series = await report_service.fetch_trend_series(
        pool,
        empresa_id=definition.empresa_id,
        planta_id=definition.planta_id,
        tags=definition.tags,
        start=start,
        end=end,
    )
    alarms: List[dict] = []
    if definition.include_alarms:
        alarms = await report_service.fetch_alarm_events(
            pool,
            empresa_id=definition.empresa_id,
            planta_id=definition.planta_id,
            start=start,
            end=end,
            tags=definition.tags or None,
        )
    pdf_bytes = _build_pdf(definition, run, series, alarms)
    emails_sent: List[str] = []
    error = None
    if run.send_email:
        settings = _load_email_settings()
        if not settings:
            error = "SMTP no configurado (usa ALARM_SMTP_* o SMTP_* en el servicio web)"
        else:
            try:
                emails_sent = await _send_report_email(settings, definition, pdf_bytes, run)
                if not emails_sent:
                    error = "No se pudo enviar correo (sin destinatarios aceptados)"
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
    status: ReportStatus = "success" if error is None else "failed"
    return status, pdf_bytes, emails_sent, error


async def process_run(pool: asyncpg.pool.Pool, run_id: int) -> Optional[ReportRunOut]:
    run = await report_service.fetch_run(pool, run_id)
    if not run:
        return None
    definition = await _load_definition(pool, run.empresa_id, run.report_id)
    try:
        status, pdf_bytes, sent, mail_error = await execute_run(pool, run=run, definition=definition)
        if mail_error:
            status = "failed"
        return await report_service.update_run_status(
            pool,
            run_id,
            status,
            error=mail_error,
            pdf_bytes=pdf_bytes,
            emails_sent=sent,
        )
    except Exception as exc:  # noqa: BLE001
        return await report_service.update_run_status(pool, run_id, "failed", error=str(exc))


async def process_run_background(pool: asyncpg.pool.Pool, run_id: int) -> None:
    try:
        await process_run(pool, run_id)
    except Exception:
        # no-op, ya se loguea en update_run_status
        pass


def spawn_background(pool: asyncpg.pool.Pool, run_id: int) -> None:
    loop = asyncio.get_event_loop()
    loop.create_task(process_run_background(pool, run_id))
