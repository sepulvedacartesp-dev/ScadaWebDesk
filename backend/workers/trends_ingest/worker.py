# backend/workers/trends_ingest/worker.py
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

import asyncpg
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="[trend-worker] %(message)s")
logger = logging.getLogger("trend-worker")

DATABASE_URL = os.environ["DATABASE_URL"]
MQTT_HOST = os.environ["MQTT_HOST"]
MQTT_PORT = int(os.environ.get("MQTT_PORT", "8883"))
MQTT_USERNAME = os.environ.get("MQTT_USERNAME")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")
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
    logger.info("Conectando a PostgreSQL…")
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute(ensure_table_sql())
    logger.info("Tabla trends verificada.")
    return pool


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

    def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            point = parse_payload(msg.payload, msg.topic)
        except Exception as exc:
            logger.error("No se pudo parsear payload: %s", exc)
            return
        asyncio.run_coroutine_threadsafe(insert_point(pool, point), loop)

    client = mqtt.Client()
    if MQTT_USERNAME or MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_message = on_message
    client.tls_set()  # usa TLS por defecto
    client.connect(MQTT_HOST, MQTT_PORT)
    for topic in MQTT_TOPICS:
        client.subscribe(topic)
        logger.info("Suscrito a %s", topic)

    logger.info("Iniciando loop MQTT…")
    client.loop_start()
    try:
        await asyncio.Event().wait()
    finally:
        client.loop_stop()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
