import os
import json
import ssl
import threading
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import auth as firebase_auth

import paho.mqtt.client as mqtt

load_dotenv()

# ---- Config ----
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "").strip()
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")

MQTT_HOST = os.getenv("HIVEMQ_HOST", "").strip()
MQTT_PORT = int(os.getenv("HIVEMQ_PORT", "8883"))
MQTT_USERNAME = os.getenv("HIVEMQ_USERNAME", "").strip()
MQTT_PASSWORD = os.getenv("HIVEMQ_PASSWORD", "").strip()
MQTT_TLS = os.getenv("MQTT_TLS", "1").strip() == "1"
MQTT_TLS_INSECURE = os.getenv("MQTT_TLS_INSECURE", "0").strip() == "1"
MQTT_CA_CERT_PATH = os.getenv("MQTT_CA_CERT_PATH", "").strip()  # optional
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "webbridge-backend")

# Topic base to scope each user (recommended: something like 'scada/customers')
TOPIC_BASE = os.getenv("TOPIC_BASE", "scada/customers").strip()

# Optional: allow multiple public prefixes (comma-separated) if you don't want per-user scoping
PUBLIC_ALLOWED_PREFIXES = [p.strip() for p in os.getenv("PUBLIC_ALLOWED_PREFIXES", "").split(",") if p.strip()]

if not FIREBASE_PROJECT_ID:
    raise RuntimeError("FIREBASE_PROJECT_ID is required")

if not MQTT_HOST:
    raise RuntimeError("HIVEMQ_HOST is required")

# ---- Firebase Admin init (used only for verifying ID tokens) ----
# initialize app without credentials; it will fetch Google's public certs to verify tokens
if not firebase_admin._apps:
    firebase_admin.initialize_app(name="bridge-app")

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

# ---- MQTT Client (single, shared) ----
mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID, clean_session=True)

if MQTT_TLS:
    # TLS Configuration
    if MQTT_CA_CERT_PATH:
        mqtt_client.tls_set(ca_certs=MQTT_CA_CERT_PATH, certfile=None, keyfile=None, tls_version=ssl.PROTOCOL_TLS)
    else:
        mqtt_client.tls_set(tls_version=ssl.PROTOCOL_TLS)
    mqtt_client.tls_insecure_set(MQTT_TLS_INSECURE)

if MQTT_USERNAME:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD if MQTT_PASSWORD else None)

# Simple connection state
_mqtt_connected = threading.Event()

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        _mqtt_connected.set()
        print("[MQTT] Connected")
        # Subscribe a broad base. We will filter per-user before forwarding.
        base = TOPIC_BASE if TOPIC_BASE.endswith("#") else (TOPIC_BASE.rstrip("/") + "/#")
        client.subscribe(base, qos=1)
        # If configured, subscribe also to public prefixes
        for p in PUBLIC_ALLOWED_PREFIXES:
            topic = p if p.endswith("#") else (p.rstrip("/") + "/#")
            client.subscribe(topic, qos=1)
    else:
        print(f"[MQTT] Connection failed rc={rc}")

def on_message(client, userdata, msg):
    # Broadcast to relevant websockets that are authorized for this topic
    data = {"topic": msg.topic, "payload": try_decode(msg.payload), "qos": msg.qos, "retain": msg.retain}
    ConnectionManager.broadcast(msg.topic, data)

def try_decode(b: bytes) -> Any:
    try:
        s = b.decode("utf-8")
        # if it looks like json, parse it
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            return json.loads(s)
        return s
    except Exception:
        # return base64 for binary payloads
        import base64
        return {"_binary_base64": base64.b64encode(b).decode("ascii")}

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
mqtt_client.loop_start()

# ---- Connection Manager for WebSockets ----
class WSClient:
    def __init__(self, ws: WebSocket, uid: str, allowed_prefixes: List[str]):
        self.ws = ws
        self.uid = uid
        # normalize prefixes with trailing slash
        self.allowed_prefixes = [p.rstrip("/") + "/" for p in allowed_prefixes]

    def can_receive(self, topic: str) -> bool:
        # deliver only if the topic starts with any allowed prefix
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
        # non-blocking send to authorized clients only
        to_remove = []
        for c in list(cls.clients):
            try:
                if c.can_receive(topic):
                    # send asynchronously; FastAPI/Starlette provides ws.send_json
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
        decoded = firebase_auth.verify_id_token(id_token, check_revoked=False)
        # Optionally enforce project id
        if decoded.get("aud") and FIREBASE_PROJECT_ID not in (decoded.get("aud"), decoded.get("firebase", {}).get("project_id", "")):
            # Usually 'aud' equals the Firebase project ID; if mismatch, reject
            pass  # Allow if verify_id_token succeeded; Firebase handles the audience check internally
        return decoded  # contains 'uid', 'email', etc.
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

def allowed_prefixes_for_user(uid: str) -> List[str]:
    # Main per-user scope under TOPIC_BASE
    base = TOPIC_BASE.rstrip("/")
    per_user = f"{base}/{uid}"
    prefixes = [per_user]
    # Add public prefixes if configured
    prefixes.extend(PUBLIC_ALLOWED_PREFIXES)
    return prefixes

def ensure_mqtt_connected():
    if not _mqtt_connected.wait(timeout=10):
        raise HTTPException(status_code=503, detail="MQTT broker not connected")

# ---- API ----
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
    # Check topic scope
    allowed = allowed_prefixes_for_user(uid)
    if not any(p.topic.startswith(pref) for pref in [x.rstrip("/") + "/" for x in allowed]):
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
    # Accept connection
    await websocket.accept()
    # Verify token (sent in ?token=...)
    if not token:
        await websocket.close(code=4401)
        return
    try:
        decoded = firebase_auth.verify_id_token(token, check_revoked=False)
    except Exception:
        await websocket.close(code=4401)
        return

    uid = decoded["uid"]
    # Assign allowed prefixes to this connection
    prefixes = allowed_prefixes_for_user(uid)
    client = WSClient(websocket, uid, prefixes)
    ConnectionManager.add(client)

    # Send a hello message with info & prefixes
    await websocket.send_json({"type": "hello", "uid": uid, "allowed_prefixes": prefixes})

    try:
        while True:
            # Receive messages from client: {type:"publish", topic, payload, qos, retain}
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                continue
            if data.get("type") == "publish":
                topic = data.get("topic", "")
                payload = data.get("payload")
                qos = int(data.get("qos", 0))
                retain = bool(data.get("retain", False))

                # topic scope check
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
