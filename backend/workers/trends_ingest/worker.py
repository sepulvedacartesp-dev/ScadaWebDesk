import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import asyncpg
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="[trend-worker] %(message)s")
logger = logging.getLogger("trend-worker")

DATABASE_URL = os.environ["DATABASE_URL"]
MQTT_TOPICS = [t.strip() for t in os.environ["MQTT_TOPICS"].split(",") if t.strip()]
DEFAULT_EMPRESA_ID = os.environ.get("DEFAULT_EMPRESA_ID", "default")


def ensure_table_sql() -> str:
    return """
    CREATE TABLE IF NOT EXISTS trends (
        id BIGSERIAL PRIMARY KEY,
        empresa_id TEXT NOT NULL,
        tag TEXT NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        valor DOUBLE PRECISION NOT NULL,
        ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS trends_empresa_tag_ts_idx
        ON trends (empresa_id, tag, timestamp DESC);
    """


async def create_pool() -> asyncpg.pool.Pool:
    logger.info("Conectando a PostgreSQL...")
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute(ensure_table_sql())
    logger.info("Tabla trends verificada.")
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


def parse_payload(raw_payload: bytes, topic: str) -> Dict[str, Any]:
    data = json.loads(raw_payload.decode("utf-8"))
    empresa_id = data.get("empresaId") or DEFAULT_EMPRESA_ID
    tag = data.get("tag")
    value = float(data.get("value"))
    timestamp_iso = data.get("timestamp")
    if not timestamp_iso:
        timestamp_iso = datetime.now(timezone.utc).isoformat()
    return {
        "empresa_id": empresa_id,
        "tag": tag,
        "value": value,
        "timestamp": datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00")),
    }


async def insert_point(pool: asyncpg.pool.Pool, point: Dict[str, Any]) -> None:
    async with pool.acquire() as conn:
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
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
