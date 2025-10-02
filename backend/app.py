import os
import json
import ssl
import threading
import asyncio
import logging
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from google.auth.exceptions import DefaultCredentialsError
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

import paho.mqtt.client as mqtt

load_dotenv()

logger = logging.getLogger("bridge")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[BRIDGE] %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_ENV_PATH = os.getenv('SCADA_CONFIG_PATH')
if CONFIG_ENV_PATH:
    CONFIG_PATH = Path(CONFIG_ENV_PATH).expanduser().resolve()
else:
    CONFIG_PATH = (BASE_DIR / '..' / 'scada_config.json').resolve()
ADMIN_EMAILS = [email.strip() for email in os.getenv('CONFIG_ADMIN_EMAILS', '').split(',') if email.strip()]
ADMIN_EMAILS_LOWER = {email.lower() for email in ADMIN_EMAILS}

GOOGLE_REQUEST = google_requests.Request()

FIREBASE_APP_NAME = "bridge-app"
firebase_app = None
event_loop: Optional[asyncio.AbstractEventLoop] = None
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

@app.on_event("startup")
async def capture_event_loop():
    global event_loop
    event_loop = asyncio.get_running_loop()
    logger.info("Event loop captured")

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

last_message_store: Dict[str, Dict[str, Any]] = {}
last_message_lock = threading.Lock()


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
    decoded_payload = try_decode(msg.payload)
    logger.info("MQTT inbound topic=%s qos=%s retain=%s", msg.topic, msg.qos, msg.retain)
    data = {"topic": msg.topic, "payload": decoded_payload, "qos": msg.qos, "retain": msg.retain}
    remember_message(data)
    ConnectionManager.broadcast(msg.topic, data)




def remember_message(data: Dict[str, Any]) -> None:
    topic = data.get("topic")
    if not topic:
        return
    entry = {"topic": topic,
             "payload": data.get("payload"),
             "retain": bool(data.get("retain")),
             "qos": int(data.get("qos", 0))}
    with last_message_lock:
        last_message_store[topic] = entry



def snapshot_for_prefixes(prefixes: List[str]) -> List[Dict[str, Any]]:
    normalized = [p.rstrip("/") + "/" for p in prefixes]
    with last_message_lock:
        return [dict(entry) for topic, entry in last_message_store.items()
                if any((topic.rstrip("/") + "/").startswith(pref) for pref in normalized)]

def try_decode(b: bytes) -> Any:
    try:
        s = b.decode("utf-8")
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            return json.loads(s)
        return s
    except Exception:
        import base64
        return {"_binary_base64": base64.b64encode(b).decode("ascii")}


def normalize_config(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {
            "mainTitle": "SCADA Web",
            "roles": {"admins": [], "operators": [], "viewers": []},
            "containers": []
        }
    result = dict(data)
    result.setdefault("mainTitle", "SCADA Web")
    roles = result.get("roles")
    if not isinstance(roles, dict):
        roles = {}
    normalized_roles: Dict[str, List[str]] = {}
    for key in ("admins", "operators", "viewers"):
        raw = roles.get(key, [])
        if isinstance(raw, list):
            normalized_roles[key] = [str(item).strip() for item in raw if str(item).strip()]
        elif isinstance(raw, str):
            normalized_roles[key] = [item.strip() for item in raw.split(",") if item.strip()]
        else:
            normalized_roles[key] = []
    result["roles"] = normalized_roles
    containers = result.get("containers")
    if not isinstance(containers, list):
        containers = []
    result["containers"] = containers
    return result


def load_scada_config() -> Dict[str, Any]:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        logger.warning("Config file %s not found, using defaults", CONFIG_PATH)
        data = {}
    except json.JSONDecodeError as exc:
        logger.error("Config JSON invalid: %s", exc)
        raise HTTPException(status_code=500, detail="Invalid configuration file")
    return normalize_config(data)


def save_scada_config(data: Dict[str, Any]) -> None:
    normalized = normalize_config(data)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as fh:
        json.dump(normalized, fh, ensure_ascii=False, indent=2)


def role_for_email(cfg: Dict[str, Any], email: Optional[str]) -> str:
    if not email:
        return "viewer"
    lower_email = email.lower()
    if lower_email in ADMIN_EMAILS_LOWER:
        return "admin"
    roles = cfg.get("roles", {})
    if lower_email in [str(item).lower() for item in roles.get("admins", [])]:
        return "admin"
    if lower_email in [str(item).lower() for item in roles.get("operators", [])]:
        return "operador"
    if lower_email in [str(item).lower() for item in roles.get("viewers", [])]:
        return "visualizacion"
    return "operador"


def ensure_admin(email: Optional[str], cfg: Optional[Dict[str, Any]] = None) -> None:
    if not email:
        raise HTTPException(status_code=403, detail="Usuario sin email en token")
    lower_email = email.lower()
    if lower_email in ADMIN_EMAILS_LOWER:
        return
    cfg = cfg or load_scada_config()
    roles = cfg.get("roles", {})
    admin_list = [str(item).lower() for item in roles.get("admins", [])]
    if lower_email in admin_list:
        return
    raise HTTPException(status_code=403, detail="Usuario no autorizado para modificar la configuración")


def validate_config_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="El cuerpo debe ser un objeto JSON")
    containers = data.get("containers")
    if containers is None or not isinstance(containers, list):
        raise HTTPException(status_code=400, detail="El campo containers debe ser una lista")
    for c_idx, container in enumerate(containers):
        if not isinstance(container, dict):
            raise HTTPException(status_code=400, detail=f"El contenedor {c_idx} debe ser un objeto")
        objects = container.get("objects", [])
        if not isinstance(objects, list):
            raise HTTPException(status_code=400, detail=f"El campo objects del contenedor {c_idx} debe ser una lista")
        for o_idx, obj in enumerate(objects):
            if not isinstance(obj, dict):
                raise HTTPException(status_code=400, detail=f"El objeto {o_idx} del contenedor {c_idx} debe ser un objeto")
            topic = obj.get("topic")
            if topic is not None and not isinstance(topic, str):
                raise HTTPException(status_code=400, detail=f"El topic del objeto {o_idx} del contenedor {c_idx} debe ser texto")
    return normalize_config(data)


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
        delivered = 0
        to_remove = []
        loop = event_loop
        for c in list(cls.clients):
            try:
                if not c.can_receive(topic):
                    continue
                if loop is None:
                    logger.warning("WS deliver skipped; no event loop topic=%s", topic)
                    continue
                future = asyncio.run_coroutine_threadsafe(c.ws.send_json(data), loop)
                try:
                    future.result(timeout=5)
                    delivered += 1
                    logger.info("WS deliver topic=%s uid=%s", topic, c.uid)
                except FutureTimeoutError:
                    logger.error("WS deliver timeout uid=%s topic=%s", c.uid, topic)
                    to_remove.append(c.ws)
                except Exception as exc:
                    logger.error("WS deliver failed uid=%s topic=%s: %s", c.uid, topic, exc, exc_info=exc)
                    to_remove.append(c.ws)
            except Exception as exc:
                logger.error("Broadcast loop error uid=%s topic=%s: %s", getattr(c, "uid", None), topic, exc, exc_info=exc)
                to_remove.append(c.ws)
        for ws in to_remove:
            cls.remove(ws)
        if delivered == 0:
            logger.info("WS no listeners for topic=%s", topic)

# ---- Helpers ----

def _ensure_uid(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not payload:
        raise ValueError("Empty token payload")
    uid = payload.get("uid") or payload.get("user_id") or payload.get("sub")
    if not uid:
        raise ValueError("Token missing uid")
    payload["uid"] = uid
    return payload


def decode_firebase_token(id_token_str: str) -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    decoded: Optional[Dict[str, Any]] = None
    if firebase_app is not None:
        try:
            decoded = firebase_auth.verify_id_token(id_token_str, check_revoked=False, app=firebase_app)
            return _ensure_uid(decoded)
        except DefaultCredentialsError as exc:
            last_error = exc
            logger.warning("Firebase Admin requires ADC; falling back to google-auth verify: %s", exc)
        except Exception as exc:
            last_error = exc
            logger.warning("Firebase Admin verify failed: %s", exc)
    try:
        decoded = google_id_token.verify_firebase_token(id_token_str, GOOGLE_REQUEST, audience=FIREBASE_PROJECT_ID)
        if not decoded:
            raise ValueError("Decoded token empty")
        return _ensure_uid(decoded)
    except Exception as exc:
        if last_error is None:
            last_error = exc
        raise last_error


def verify_bearer_token(authorization: Optional[str]) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    id_token = authorization.split(" ", 1)[1].strip()
    try:
        decoded = decode_firebase_token(id_token)
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



@app.get("/config")
def get_config_endpoint(authorization: Optional[str] = Header(None)):
    decoded = verify_bearer_token(authorization)
    cfg = load_scada_config()
    email = decoded.get("email")
    role = role_for_email(cfg, email)
    return {"config": cfg, "role": role}


@app.put("/config")
def update_config_endpoint(config: Dict[str, Any] = Body(...), authorization: Optional[str] = Header(None)):
    decoded = verify_bearer_token(authorization)
    email = decoded.get("email")
    current_cfg = load_scada_config()
    ensure_admin(email, current_cfg)
    normalized = validate_config_payload(config)
    try:
        save_scada_config(normalized)
    except Exception as exc:
        logger.exception("Error writing configuration: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudo guardar la configuración") from exc
    role = role_for_email(normalized, email)
    logger.info("Config updated by %s", email)
    return {"ok": True, "config": normalized, "role": role}

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
        decoded = decode_firebase_token(token)
        logger.info("WS token OK uid=%s", decoded.get("uid"))
    except Exception as e:
        logger.warning("WS token invalid: %s", e)
        await websocket.close(code=4401)
        return

    uid = decoded["uid"]
    prefixes = allowed_prefixes_for_user(uid)
    client = WSClient(websocket, uid, prefixes)
    ConnectionManager.add(client)

    initial_snapshot = snapshot_for_prefixes(prefixes)
    await websocket.send_json({"type": "hello", "uid": uid, "allowed_prefixes": prefixes, "last_values": initial_snapshot})

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
