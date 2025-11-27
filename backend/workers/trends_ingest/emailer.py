from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, format_datetime
from typing import Optional, Tuple

import aiosmtplib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from alarms.schemas import AlarmOperator


OPERATOR_SYMBOLS = {
    "gte": ">=",
    "lte": "<=",
    "eq": "==",
}


@dataclass(slots=True)
class EmailSettings:
    host: str
    port: int
    username: str
    password: str
    from_address: str
    from_name: Optional[str] = None
    use_starttls: bool = True
    use_tls: bool = False
    timeout: float = 10.0
    subject_prefix: str = "[Alarma SCADA]"
    reply_to: Optional[str] = None
    tz_name: Optional[str] = None


class EmailNotifier:
    def __init__(self, settings: EmailSettings, logger):
        self._settings = settings
        self._logger = logger
        self._tz = self._resolve_timezone(settings.tz_name)

    def _resolve_timezone(self, tz_name: Optional[str]) -> timezone:
        name = (tz_name or os.environ.get("ALARM_EMAIL_TZ") or "America/Santiago").strip()
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            self._logger.warning("Zona horaria '%s' no valida; usando UTC.", name)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("No se pudo cargar zona horaria '%s': %s. Se usara UTC.", name, exc)
        return timezone.utc

    def _format_from(self) -> str:
        if self._settings.from_name:
            return formataddr((self._settings.from_name, self._settings.from_address))
        return self._settings.from_address

    def build_message(
        self,
        *,
        empresa_id: str,
        planta_id: Optional[str],
        tag: str,
        operator: AlarmOperator,
        threshold_value: float,
        observed_value: float,
        triggered_at: datetime,
    ) -> EmailMessage:
        symbol = OPERATOR_SYMBOLS.get(operator, operator)
        local_dt = triggered_at.astimezone(self._tz)
        tz_label = getattr(self._tz, "key", None) or getattr(self._tz, "zone", None) or "local"
        subject = (
            f"{self._settings.subject_prefix} "
            f"{empresa_id}/{planta_id or 'default'} - {tag} {symbol} {threshold_value:g}"
        )
        timestamp_display = format_datetime(local_dt)
        body_lines = [
            f"Se ha disparado una alarma para la empresa {empresa_id}.",
            f"Planta: {planta_id or 'default'}",
            "",
            f"Tag: {tag}",
            f"Comparador: {symbol}",
            f"Umbral configurado: {threshold_value}",
            f"Valor observado: {observed_value}",
            f"Fecha ({tz_label}): {timestamp_display}",
            "",
            "Este correo es generado automaticamente por el sistema SCADA SurNex.",
        ]
        msg = EmailMessage()
        msg["From"] = self._format_from()
        msg["Subject"] = subject
        msg["Date"] = format_datetime(local_dt)
        if self._settings.reply_to:
            msg["Reply-To"] = self._settings.reply_to
        msg.set_content("\n".join(body_lines))
        return msg

    async def send_alarm(
        self,
        *,
        empresa_id: str,
        planta_id: Optional[str],
        tag: str,
        operator: AlarmOperator,
        threshold_value: float,
        observed_value: float,
        triggered_at: datetime,
        recipient: str,
    ) -> Tuple[bool, Optional[str]]:
        try:
            message = self.build_message(
                empresa_id=empresa_id,
                planta_id=planta_id,
                tag=tag,
                operator=operator,
                threshold_value=threshold_value,
                observed_value=observed_value,
                triggered_at=triggered_at,
            )
            message["To"] = recipient
            await aiosmtplib.send(
                message,
                hostname=self._settings.host,
                port=self._settings.port,
                username=self._settings.username,
                password=self._settings.password,
                start_tls=self._settings.use_starttls,
                use_tls=self._settings.use_tls,
                timeout=self._settings.timeout,
            )
            return True, None
        except Exception as exc:  # noqa: BLE001
            self._logger.error("Fallo envio de correo a %s: %s", recipient, exc)
            return False, str(exc)
