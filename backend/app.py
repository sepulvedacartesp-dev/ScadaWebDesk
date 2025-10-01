import os
import json
import ssl
import threading
import logging
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials

import paho.mqtt.client as mqtt

load_dotenv()

logger = logging.getLogger("bridge")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[BRIDGE] %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

FIREBASE_APP_NAME = "bridge-app"
firebase_app = None
# ---- Config ----
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "").strip()
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")

MQTT_HOST = os.getenv("HIVEMQ_HOST", "").strip()
MQTT_PORT = int(os.getenv("HIVEMQ_PORT", "8883"))
MQTT_USERNAME = os.getenv("HIVEMQ_USERNAME", "").strip()
MQTT_PASSWORD = os.getenv("HIVEMQ_PASSWORD", "").strip()
MQTT_TLS = os.getenv("MQTT_TLS", "1").strip() == "1"
MQTT_TLS_INSECURE = os.getenv("MQTT_TLS_INSECURE", "0").strip() == "1"
MQTT_CA_CERT_PATH = os.getenv("MQTT_CA_CERT_PATH", "").strip()
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "webbridge-backend")

TOPIC_BASE = os.getenv("TOPIC_BASE", "scada/customers").strip()
PUBLIC_ALLOWED_PREFIXES = [p.strip() for p in os.getenv("PUBLIC_ALLOWED_PREFIXES", "").split(",") if p.strip()]

FIREBASE_SERVICE_ACCOUNT = os.getenv("FIREBASE_SERVICE_ACCOUNT", "").strip()

if not FIREBASE_PROJECT_ID:
    raise RuntimeError("FIREBASE_PROJECT_ID is required")
if not MQTT_HOST:
    raise RuntimeError("HIVEMQ_HOST is required")

# ---- Firebase Admin init ----
if not firebase_admin._apps:
    try:
        if FIREBASE_SERVICE_ACCOUNT:
            cred = credentials.Certificate(json.loads(FIREBASE_SERVICE_ACCOUNT))
            firebase_app = firebase_admin.initialize_app(cred, name=FIREBASE_APP_NAME)
            logger.info("FB initialized with service account")
        else:
            firebase_app = firebase_admin.initialize_app(options={"projectId": FIREBASE_PROJECT_ID}, name=FIREBASE_APP_NAME)
            logger.info("FB initialized with projectId=%s", FIREBASE_PROJECT_ID)
    except Exception as e:
        logger.exception("FB init error: %s", e)
        raise
else:
    try:
        firebase_app = firebase_admin.get_app(FIREBASE_APP_NAME)
        logger.info("FB app reused name=%s", FIREBASE_APP_NAME)
    except ValueError:
        firebase_app = firebase_admin.get_app()
        logger.info("FB default app reused")

# ---- FastAPI app ----
app = FastAPI(title="MQTT Web Bridge", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if FRONTEND_ORIGIN == "*" else [FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- MQTT Client ----
mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID, clean_session=True)
mqtt_client.enable_logger()

if MQTT_TLS:
    if MQTT_CA_CERT_PATH:
        mqtt_client.tls_set(ca_certs=MQTT_CA_CERT_PATH, certfile=None, keyfile=None, tls_version=ssl.PROTOCOL_TLS)
    else:
        mqtt_client.tls_set(tls_version=ssl.PROTOCOL_TLS)
    mqtt_client.tls_insecure_set(MQTT_TLS_INSECURE)

if MQTT_USERNAME:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD if MQTT_PASSWORD else None)

_mqtt_connected = threading.Event()

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        _mqtt_connected.set()
        logger.info("MQTT connected")
        base = TOPIC_BASE if TOPIC_BASE.endswith("#") else (TOPIC_BASE.rstrip("/") + "/#")
        client.subscribe(base, qos=1)
        for p in PUBLIC_ALLOWED_PREFIXES:
            topic = p if p.endswith("#") else (p.rstrip("/") + "/#")
            client.subscribe(topic, qos=1)
    else:
        logger.error("MQTT connection failed rc=%s", rc)

def on_message(client, userdata, msg):
    data = {"topic": msg.topic, "payload": try_decode(msg.payload), "qos": msg.qos, "retain": msg.retain}
    ConnectionManager.broadcast(msg.topic, data)

def try_decode(b: bytes) -> Any:
    try:
        s = b.decode("utf-8")
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            return json.loads(s)
        return s
    except Exception:
        import base64
        return {"_binary_base64": base64.b64encode(b).decode("ascii")}

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
mqtt_client.loop_start()

# ---- WebSocket connection manager ----
class WSClient:
    def __init__(self, ws: WebSocket, uid: str, allowed_prefixes: List[str]):
        self.ws = ws
        self.uid = uid
        self.allowed_prefixes = [p.rstrip("/") + "/" for p in allowed_prefixes]

    def can_receive(self, topic: str) -> bool:
        t = topic.rstrip("/") + "/"
        return any(t.startswith(pref) for pref in self.allowed_prefixes)

class ConnectionManager:
    clients: List[WSClient] = []
    lock = threading.Lock()

    @classmethod
    def add(cls, c: WSClient):
        with cls.lock:
            cls.clients.append(c)

    @classmethod
    def remove(cls, ws: WebSocket):
        with cls.lock:
            cls.clients = [c for c in cls.clients if c.ws is not ws]

    @classmethod
    def broadcast(cls, topic: str, data: dict):
        to_remove = []
        for c in list(cls.clients):
            try:
                if c.can_receive(topic):
                    import anyio
                    anyio.from_thread.run(c.ws.send_json, data)
            except Exception:
                to_remove.append(c.ws)
        for ws in to_remove:
            cls.remove(ws)

# ---- Helpers ----
def verify_bearer_token(authorization: Optional[str]) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    id_token = authorization.split(" ", 1)[1].strip()
    try:
        decoded = firebase_auth.verify_id_token(id_token, check_revoked=False, app=firebase_app)
        return decoded
    except Exception as e:
        logger.warning("HTTP token invalid: %s", e)
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

def allowed_prefixes_for_user(uid: str) -> List[str]:
    base = TOPIC_BASE.rstrip("/")
    per_user = f"{base}/{uid}"
    prefixes = [per_user]
    prefixes.extend(PUBLIC_ALLOWED_PREFIXES)
    return prefixes

def ensure_mqtt_connected():
    if not _mqtt_connected.wait(timeout=10):
        raise HTTPException(status_code=503, detail="MQTT broker not connected")

# ---- API ----
@app.get("/")
def root():
    return {"service": "mqtt-web-bridge", "health": "ok"}

@app.get("/health")
def health():
    return {"status": "ok"}

class PublishIn(BaseModel):
    topic: str
    payload: Any
    qos: int = 0
    retain: bool = False

@app.post("/publish")
def publish(p: PublishIn, authorization: Optional[str] = Header(None)):
    decoded = verify_bearer_token(authorization)
    uid = decoded["uid"]
    allowed = [x.rstrip("/") + "/" for x in allowed_prefixes_for_user(uid)]
    if not any(p.topic.startswith(pref) for pref in allowed):
        raise HTTPException(status_code=403, detail=f"Topic not allowed for user {uid}")
    ensure_mqtt_connected()
    payload = p.payload
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload, separators=(",", ":"))
    elif not isinstance(payload, str):
        payload = str(payload)
    res = mqtt_client.publish(p.topic, payload=payload, qos=p.qos, retain=p.retain)
    if res.rc != mqtt.MQTT_ERR_SUCCESS:
        raise HTTPException(status_code=500, detail=f"MQTT publish error rc={res.rc}")
    return {"ok": True}

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, token: Optional[str] = Query(default=None)):
    await websocket.accept()
    origin = websocket.headers.get("origin")
    logger.info("WS accepted origin=%s", origin)

    if not token:
        await websocket.close(code=4401)
        return
    try:
        decoded = firebase_auth.verify_id_token(token, check_revoked=False, app=firebase_app)
        logger.info("WS token OK uid=%s", decoded.get("uid"))
    except Exception as e:
        logger.warning("WS token invalid: %s", e)
        await websocket.close(code=4401)
        return

    uid = decoded["uid"]
    prefixes = allowed_prefixes_for_user(uid)
    client = WSClient(websocket, uid, prefixes)
    ConnectionManager.add(client)

    await websocket.send_json({"type": "hello", "uid": uid, "allowed_prefixes": prefixes})

    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                continue
            if data.get("type") == "publish":
                topic = data.get("topic", "")
                payload = data.get("payload")
                qos = int(data.get("qos", 0))
                retain = bool(data.get("retain", False))

                if not any(topic.startswith(pref.rstrip('/') + '/') for pref in prefixes):
                    await websocket.send_json({"type": "error", "error": "Topic not allowed"})
                    continue

                ensure_mqtt_connected()
                pub_payload = payload
                if isinstance(pub_payload, (dict, list)):
                    pub_payload = json.dumps(pub_payload, separators=(",", ":"))
                elif not isinstance(pub_payload, str):
                    pub_payload = str(pub_payload)

                res = mqtt_client.publish(topic, payload=pub_payload, qos=qos, retain=retain)
                if res.rc != mqtt.MQTT_ERR_SUCCESS:
                    await websocket.send_json({"type": "error", "error": f"MQTT publish rc={res.rc}"})
                else:
                    await websocket.send_json({"type": "ack", "topic": topic})
            else:
                await websocket.send_json({"type": "error", "error": "Unknown message type"})
    except WebSocketDisconnect:
        ConnectionManager.remove(websocket)
    except Exception:
        ConnectionManager.remove(websocket)
        try:
            await websocket.close()
        except Exception:
            pass
