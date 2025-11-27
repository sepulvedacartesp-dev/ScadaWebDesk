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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reports.schemas import ReportDefinitionOut, ReportRunOut, ReportStatus
from reports import service as report_service

PALETTE = {
    "primary": colors.HexColor("#0d6efd"),
    "muted": colors.HexColor("#6c757d"),
    "accent": colors.HexColor("#198754"),
    "bg": colors.HexColor("#f7f9fb"),
}


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
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    subtitle = styles["Heading2"]
    h3 = styles["Heading3"]
    normal = styles["Normal"]
    normal.leading = 14

    total_points = sum(len(item.get("points") or []) for item in series)
    alarm_count = len(alarms)
    tags_count = len([item for item in series if item.get("tag")])

    elements: List[object] = []
    elements.append(Paragraph(f"<b>{definition.name}</b>", title_style))
    meta_text = (
        f"Empresa: {definition.empresa_id} | Planta: {definition.planta_id} | Frecuencia: {definition.frequency} | "
        f"Ventana: {run.window_start} a {run.window_end}"
    )
    elements.append(Paragraph(meta_text, normal))
    elements.append(Paragraph(f"Destinatarios: {', '.join(definition.recipients)}", normal))
    elements.append(Spacer(1, 0.3 * cm))

    summary_table = Table(
        [
            ["Tags", "Puntos", "Alarmas"],
            [str(tags_count), str(total_points), str(alarm_count)],
        ],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PALETTE["primary"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
            ]
        ),
    )
    elements.append(summary_table)
    elements.append(Spacer(1, 0.4 * cm))

    for item in series:
        tag = item.get("tag", "")
        stats = item.get("stats") or {}
        points = item.get("points") or []
        elements.append(Paragraph(f"Tag: <b>{tag}</b>", h3))
        stats_table = Table(
            [
                ["Min", "Max", "Promedio", "Último", "Muestras"],
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
                    ("BACKGROUND", (0, 0), (-1, 0), PALETTE["bg"]),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            ),
        )
        elements.append(stats_table)
        chart_bytes = _plot_series_chart(tag, points)
        flow = _image_flowable(chart_bytes) if chart_bytes else None
        if flow:
            elements.append(flow)
        else:
            condensed = _condense_points(points, 80)
            spark_data = " ".join(_sparkline(condensed))
            elements.append(Paragraph(f"Sparklines: {spark_data}", styles["Code"]))
        elements.append(Spacer(1, 0.2 * cm))

    elements.append(Spacer(1, 0.3 * cm))
    elements.append(Paragraph("Alarmas notificadas", subtitle))
    elements.append(Paragraph(f"Total en ventana: {alarm_count}", normal))

    alarm_chart = _plot_alarms_timeline(alarms)
    flow_alarm = _image_flowable(alarm_chart) if alarm_chart else None
    if flow_alarm:
        elements.append(flow_alarm)

    if alarms:
        table_data = [["Fecha", "Planta", "Tag", "Valor", "Umbral", "Operador", "Envío", "Error"]]
        for event in alarms:
            table_data.append(
                [
                    str(event.get("triggered_at")),
                    event.get("planta_id") or "--",
                    event.get("tag", "--"),
                    str(event.get("observed", "--")),
                    str(event.get("threshold", "--")),
                    str(event.get("operator", "--")),
                    "Enviado" if event.get("email_sent") else "No enviado",
                    event.get("email_error") or "",
                ]
            )
        alarm_table = Table(
            table_data,
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), PALETTE["primary"]),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                ]
            ),
        )
        elements.append(alarm_table)
    else:
        elements.append(Paragraph("Sin alarmas notificadas en la ventana seleccionada.", normal))

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


def _image_flowable(image_bytes: bytes, width: float = 14 * cm) -> Optional[Image]:
    if not image_bytes:
        return None
    try:
        img = Image(io.BytesIO(image_bytes))
        img._restrictSize(width, width * 0.6)
        return img
    except Exception:
        return None


def _plot_series_chart(tag: str, points: Sequence[dict]) -> Optional[bytes]:
    if not points:
        return None
    try:
        xs = [datetime.fromisoformat(p["timestamp"].replace("Z", "+00:00")) for p in points]
        ys = [p["value"] for p in points]
        plt.figure(figsize=(6, 2.2))
        plt.plot(xs, ys, color="#0d6efd", linewidth=1.5)
        plt.fill_between(xs, ys, color="#0d6efd", alpha=0.1)
        plt.title(tag, fontsize=10)
        plt.xlabel("Tiempo")
        plt.ylabel("Valor")
        plt.grid(True, linestyle="--", alpha=0.3)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=120)
        plt.close()
        return buf.getvalue()
    except Exception:
        plt.close()
        return None


def _plot_alarms_timeline(events: Sequence[dict]) -> Optional[bytes]:
    if not events:
        return None
    try:
        times = []
        values = []
        colors_map = []
        for ev in events:
            ts = ev.get("triggered_at")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            times.append(ts)
            values.append(ev.get("observed") or 0)
            colors_map.append("#198754" if ev.get("email_sent") else "#dc3545")
        plt.figure(figsize=(6, 2.0))
        plt.scatter(times, values, c=colors_map, alpha=0.8)
        plt.title("Alarmas notificadas", fontsize=10)
        plt.xlabel("Tiempo")
        plt.ylabel("Valor observado")
        plt.grid(True, linestyle="--", alpha=0.3)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=120)
        plt.close()
        return buf.getvalue()
    except Exception:
        plt.close()
        return None


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
