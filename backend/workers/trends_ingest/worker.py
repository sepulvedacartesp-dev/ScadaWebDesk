import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = CURRENT_DIR.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.append(str(BACKEND_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))

import asyncpg
import paho.mqtt.client as mqtt

try:
    from .alarm_monitor import AlarmEngine, TrendPoint
    from .emailer import EmailNotifier, EmailSettings
except ImportError:
    from alarm_monitor import AlarmEngine, TrendPoint  # type: ignore
    from emailer import EmailNotifier, EmailSettings  # type: ignore

logging.basicConfig(level=logging.INFO, format="[trend-worker] %(message)s")
logger = logging.getLogger("trend-worker")

DATABASE_URL = os.environ["DATABASE_URL"]
MQTT_TOPICS = [t.strip() for t in os.environ["MQTT_TOPICS"].split(",") if t.strip()]
DEFAULT_EMPRESA_ID = os.environ.get("DEFAULT_EMPRESA_ID", "default")
DEFAULT_PLANTA_ID = os.environ.get("DEFAULT_PLANTA_ID", "default")
TRENDS_SUPPORTS_PLANTA_ID: Optional[bool] = None


def ensure_table_sql() -> str:
    return """
    CREATE TABLE IF NOT EXISTS trends (
        id BIGSERIAL PRIMARY KEY,
        empresa_id TEXT NOT NULL,
        planta_id TEXT NOT NULL DEFAULT 'default',
        tag TEXT NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        valor DOUBLE PRECISION NOT NULL,
        ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    ALTER TABLE trends
        ADD COLUMN IF NOT EXISTS planta_id TEXT NOT NULL DEFAULT 'default';
    CREATE INDEX IF NOT EXISTS trends_empresa_planta_tag_ts_idx
        ON trends (empresa_id, planta_id, tag, timestamp DESC);
    """


def normalize_planta(value: Optional[str]) -> str:
    if not value:
        return DEFAULT_PLANTA_ID
    normalized = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(value))
    normalized = normalized.strip("_").lower()
    return normalized or DEFAULT_PLANTA_ID


async def create_pool() -> asyncpg.pool.Pool:
    logger.info("Conectando a PostgreSQL...")
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute(ensure_table_sql())
    global TRENDS_SUPPORTS_PLANTA_ID
    TRENDS_SUPPORTS_PLANTA_ID = await _table_has_column(pool, "trends", "planta_id")
    logger.info(
        "Tabla trends verificada (planta_id %s).",
        "habilitado" if TRENDS_SUPPORTS_PLANTA_ID else "no disponible",
    )
    return pool


def coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


ENABLE_ALARM_MONITOR = coerce_bool(os.environ.get("ENABLE_ALARM_MONITOR"), True)
ALARM_RULES_REFRESH_SECONDS = coerce_int(os.environ.get("ALARM_RULES_REFRESH_SECONDS"), 60)
ALARM_QUEUE_MAXSIZE = coerce_int(os.environ.get("ALARM_QUEUE_MAXSIZE"), 2048)
COLUMN_CHECK_QUERY = """
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = $1 AND column_name = $2
    LIMIT 1
"""


async def _table_has_column(pool: asyncpg.pool.Pool, table: str, column: str) -> bool:
    async with pool.acquire() as conn:
        exists = await conn.fetchval(COLUMN_CHECK_QUERY, table, column)
    return bool(exists)


def load_broker_profiles() -> Dict[str, Dict[str, Any]]:
    base = {
        "host": os.environ.get("MQTT_HOST"),
        "port": coerce_int(os.environ.get("MQTT_PORT"), 8883),
        "username": os.environ.get("MQTT_USERNAME"),
        "password": os.environ.get("MQTT_PASSWORD"),
        "tls": coerce_bool(os.environ.get("MQTT_TLS"), True),
        "tls_insecure": coerce_bool(os.environ.get("MQTT_TLS_INSECURE"), False),
        "ca_cert_path": os.environ.get("MQTT_CA_CERT_PATH") or None,
        "client_id": os.environ.get("MQTT_CLIENT_ID") or None,
        "keepalive": coerce_int(os.environ.get("MQTT_KEEPALIVE"), 60),
    }
    raw_profiles = os.environ.get("MQTT_BROKER_PROFILES")
    profiles: Dict[str, Dict[str, Any]] = {}
    if raw_profiles:
        try:
            data = json.loads(raw_profiles)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"MQTT_BROKER_PROFILES invalido: {exc}") from exc
        for key, overrides in data.items():
            if not isinstance(overrides, dict):
                overrides = {}
            cfg = base.copy()
            cfg["host"] = overrides.get("host", cfg["host"])
            cfg["port"] = coerce_int(overrides.get("port"), cfg["port"])
            cfg["username"] = overrides.get("username", cfg["username"])
            cfg["password"] = overrides.get("password", cfg["password"])
            cfg["tls"] = coerce_bool(overrides.get("tls"), cfg["tls"])
            cfg["tls_insecure"] = coerce_bool(overrides.get("tlsInsecure"), cfg["tls_insecure"])
            cfg["ca_cert_path"] = overrides.get("caCertPath", cfg["ca_cert_path"])
            cfg["client_id"] = overrides.get("clientId", cfg["client_id"])
            cfg["keepalive"] = coerce_int(overrides.get("keepalive"), cfg["keepalive"])
            if not cfg["host"]:
                logger.warning("Perfil '%s' ignorado: no define host.", key)
                continue
            profiles[key] = cfg
    if not profiles:
        if not base["host"]:
            raise RuntimeError("Debe definir MQTT_HOST o MQTT_BROKER_PROFILES con al menos un host.")
        profiles["default"] = base
    return profiles


def load_email_settings() -> Optional[EmailSettings]:
    host = (os.environ.get("ALARM_SMTP_HOST") or "").strip()
    username = (os.environ.get("ALARM_SMTP_USERNAME") or "").strip()
    password = (os.environ.get("ALARM_SMTP_PASSWORD") or "").strip()
    if not host or not username or not password:
        logger.info("Motor de alarmas deshabilitado: faltan credenciales SMTP.")
        return None

    from_address = (os.environ.get("ALARM_EMAIL_FROM") or "notificaciones@surnex.cl").strip()
    if "@" not in from_address:
        logger.warning("ALARM_EMAIL_FROM invalido (%s); se utilizara notificaciones@surnex.cl", from_address)
        from_address = "notificaciones@surnex.cl"

    settings = EmailSettings(
        host=host,
        port=coerce_int(os.environ.get("ALARM_SMTP_PORT"), 587),
        username=username,
        password=password,
        from_address=from_address,
        from_name=(os.environ.get("ALARM_EMAIL_FROM_NAME") or "").strip() or None,
        use_starttls=coerce_bool(os.environ.get("ALARM_SMTP_STARTTLS"), True),
        use_tls=coerce_bool(os.environ.get("ALARM_SMTP_USE_SSL"), False),
        timeout=coerce_float(os.environ.get("ALARM_SMTP_TIMEOUT"), 10.0),
        subject_prefix=(os.environ.get("ALARM_EMAIL_SUBJECT_PREFIX") or "[Alarma SCADA]").strip(),
        reply_to=(os.environ.get("ALARM_EMAIL_REPLY_TO") or "").strip() or None,
    )
    if settings.use_starttls and settings.use_tls:
        logger.warning("Configuracion SMTP indica STARTTLS y SSL simultaneamente; se prioriza STARTTLS.")
        settings.use_tls = False
    return settings


def parse_payload(raw_payload: bytes, topic: str) -> Dict[str, Any]:
    text = raw_payload.decode("utf-8").strip()

    empresa_id = DEFAULT_EMPRESA_ID
    planta_id = DEFAULT_PLANTA_ID
    tag = topic

    parts = topic.split("/")
    if len(parts) >= 5 and parts[0] == "scada" and parts[1] == "customers":
        # Nuevo formato: scada/customers/<empresa>/<planta>/trend/<tag...>
        empresa_id = parts[2] or DEFAULT_EMPRESA_ID
        planta_id = normalize_planta(parts[3] or DEFAULT_PLANTA_ID)
        if len(parts) >= 6 and parts[4] == "trend":
            tag = "/".join(parts[5:]) or topic
        else:
            tag = "/".join(parts[4:]) or topic
    elif len(parts) >= 4 and parts[0] == "scada" and parts[1] == "customers":
        # Formato legado: scada/customers/<empresa>/trend/<tag...>
        empresa_id = parts[2] or DEFAULT_EMPRESA_ID
        if len(parts) >= 5 and parts[3] == "trend":
            tag = "/".join(parts[4:]) or topic
        else:
            tag = "/".join(parts[3:]) or topic

    # Intenta parsear como JSON primero
    parsed: Any
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = text

    timestamp = datetime.now(timezone.utc)
    value: float

    if isinstance(parsed, dict):
        if parsed.get("empresaId"):
            empresa_id = str(parsed["empresaId"])
        if parsed.get("plantaId"):
            planta_id = normalize_planta(parsed["plantaId"])
        if parsed.get("tag"):
            tag = str(parsed["tag"])
        raw_value = parsed.get("value")
        if raw_value is None:
            raise ValueError("Payload JSON sin campo 'value'")
        timestamp_str = parsed.get("timestamp")
        if timestamp_str:
            timestamp = datetime.fromisoformat(str(timestamp_str).replace("Z", "+00:00"))
    else:
        raw_value = parsed

    if isinstance(raw_value, bool):
        value = 1.0 if raw_value else 0.0
    elif isinstance(raw_value, (int, float)):
        value = float(raw_value)
    else:
        if isinstance(raw_value, str):
            lowered = raw_value.lower()
            if lowered in {"true", "false"}:
                value = 1.0 if lowered == "true" else 0.0
            else:
                value = float(raw_value)
        else:
            raise ValueError(f"No se puede convertir el payload a numero: {raw_value}")

    return {
        "empresa_id": empresa_id or DEFAULT_EMPRESA_ID,
        "planta_id": planta_id or DEFAULT_PLANTA_ID,
        "tag": tag,
        "value": value,
        "timestamp": timestamp,
    }


async def insert_point(pool: asyncpg.pool.Pool, point: Dict[str, Any]) -> None:
    global TRENDS_SUPPORTS_PLANTA_ID
    async with pool.acquire() as conn:
        try:
            if TRENDS_SUPPORTS_PLANTA_ID:
                await conn.execute(
                    """
                    INSERT INTO trends (empresa_id, planta_id, tag, timestamp, valor)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    point["empresa_id"],
                    point["planta_id"],
                    point["tag"],
                    point["timestamp"],
                    point["value"],
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO trends (empresa_id, tag, timestamp, valor)
                    VALUES ($1, $2, $3, $4)
                    """,
                    point["empresa_id"],
                    point["tag"],
                    point["timestamp"],
                    point["value"],
                )
        except asyncpg.UndefinedColumnError:
            # Si la tabla no tiene planta_id, reintentar en modo compatibilidad
            TRENDS_SUPPORTS_PLANTA_ID = False
            await conn.execute(
                """
                INSERT INTO trends (empresa_id, tag, timestamp, valor)
                VALUES ($1, $2, $3, $4)
                """,
                point["empresa_id"],
                point["tag"],
                point["timestamp"],
                point["value"],
            )


async def main() -> None:
    loop = asyncio.get_running_loop()
    pool = await create_pool()
    alarm_engine: Optional[AlarmEngine] = None
    try:
        if ENABLE_ALARM_MONITOR:
            email_settings = load_email_settings()
            if email_settings:
                notifier = EmailNotifier(email_settings, logger)
                alarm_engine = AlarmEngine(
                    pool,
                    notifier,
                    refresh_seconds=ALARM_RULES_REFRESH_SECONDS,
                    queue_maxsize=ALARM_QUEUE_MAXSIZE,
                    logger=logger,
                    loop=loop,
                )
                await alarm_engine.start()
            else:
                logger.info("Motor de alarmas no iniciado: configuracion SMTP incompleta.")
        else:
            logger.info("Motor de alarmas deshabilitado por configuracion.")

        broker_profiles = load_broker_profiles()
        logger.info("Iniciando ingesta para %d perfiles de broker.", len(broker_profiles))

        clients: List[mqtt.Client] = []

        def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
            try:
                point = parse_payload(msg.payload, msg.topic)
            except Exception as exc:  # noqa: BLE001
                logger.error("No se pudo parsear payload (%s): %s", msg.topic, exc)
                return
            asyncio.run_coroutine_threadsafe(insert_point(pool, point), loop)
            if alarm_engine:
                trend_point = TrendPoint(
                    empresa_id=point["empresa_id"],
                    planta_id=point["planta_id"],
                    tag=point["tag"],
                    value=point["value"],
                    timestamp=point["timestamp"],
                )
                alarm_engine.submit_point(trend_point)

        try:
            for key, cfg in broker_profiles.items():
                client = mqtt.Client(client_id=cfg.get("client_id"))
                client.user_data_set({"broker": key})
                if cfg.get("username") or cfg.get("password"):
                    client.username_pw_set(cfg.get("username"), cfg.get("password"))
                if cfg.get("tls"):
                    if cfg.get("ca_cert_path"):
                        client.tls_set(ca_certs=cfg.get("ca_cert_path"))
                    else:
                        client.tls_set()
                    client.tls_insecure_set(bool(cfg.get("tls_insecure")))
                client.on_message = on_message
                client.connect(cfg["host"], cfg["port"], cfg.get("keepalive") or 60)
                for topic in MQTT_TOPICS:
                    client.subscribe(topic)
                    logger.info("Broker %s suscrito a %s", key, topic)
                client.loop_start()
                clients.append(client)
                logger.info("Broker %s conectado en %s:%s", key, cfg["host"], cfg["port"])
        except Exception:  # noqa: BLE001
            for client in clients:
                try:
                    client.loop_stop()
                    client.disconnect()
                except Exception:
                    pass
            raise

        logger.info("Worker de tendencias activo (brokers: %s)", ", ".join(broker_profiles.keys()))
        try:
            await asyncio.Event().wait()
        finally:
            for client in clients:
                try:
                    client.loop_stop()
                    client.disconnect()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("No se pudo cerrar un cliente MQTT: %s", exc)
    finally:
        if alarm_engine:
            await alarm_engine.stop()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
