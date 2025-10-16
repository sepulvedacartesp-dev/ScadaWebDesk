import os
import json
import base64
import ssl
import threading
import asyncio
import logging
import re
import requests
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import List, Optional, Dict, Any, Set
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from firebase_admin import exceptions as firebase_exceptions
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
CONFIG_FILENAME_SUFFIX = "_Scada_Config.json"

DEFAULT_BROKER_KEY = "default"
AVAILABLE_BROKER_KEYS: Set[str] = set()
COMPANY_BROKER_MAP: Dict[str, str] = {}
COMPANY_BROKER_LOCK = threading.Lock()

def sanitize_company_id(raw: Optional[str]) -> str:
    if raw is None:
        raise ValueError("Empresa no definida")
    sanitized = re.sub(r'[^A-Za-z0-9_-]+', '_', str(raw).strip())
    sanitized = sanitized.strip('_').lower()
    if not sanitized:
        raise ValueError("Empresa no definida")
    return sanitized


def sanitize_broker_key(raw: Optional[str]) -> str:
    if raw is None:
        raise ValueError("Broker no definido")
    sanitized = re.sub(r'[^A-Za-z0-9_-]+', '_', str(raw).strip())
    sanitized = sanitized.strip('_')
    if not sanitized:
        raise ValueError("Broker no definido")
    return sanitized


def coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def coerce_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def coerce_str(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value).strip()


DEFAULT_COMPANY_ID = sanitize_company_id(os.getenv('DEFAULT_EMPRESA_ID', 'default') or 'default')

if CONFIG_ENV_PATH:
    CONFIG_BASE_PATH = Path(CONFIG_ENV_PATH).expanduser().resolve()
else:
    CONFIG_BASE_PATH = (BASE_DIR / '..' / 'scada_configs').resolve()

if CONFIG_BASE_PATH.suffix:
    CONFIG_STORAGE_DIR = CONFIG_BASE_PATH.parent
    LEGACY_SINGLE_CONFIG_PATH = CONFIG_BASE_PATH
else:
    CONFIG_STORAGE_DIR = CONFIG_BASE_PATH
    legacy_candidate = (BASE_DIR / '..' / 'scada_config.json').resolve()
    LEGACY_SINGLE_CONFIG_PATH = legacy_candidate if legacy_candidate.exists() else None

CONFIG_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

COMPANIES_PATH = CONFIG_STORAGE_DIR / 'companies.json'
COMPANIES_LOCK = threading.Lock()

def config_path_for_company(company_id: str) -> Path:
    sanitized = sanitize_company_id(company_id)
    target = CONFIG_STORAGE_DIR / f"{sanitized}{CONFIG_FILENAME_SUFFIX}"
    if target.exists():
        return target

    legacy_name = f"{sanitized}{CONFIG_FILENAME_SUFFIX}".lower()
    try:
        for candidate in CONFIG_STORAGE_DIR.glob(f"*{CONFIG_FILENAME_SUFFIX}"):
            if not candidate.is_file():
                continue
            if candidate.name.lower() != legacy_name:
                continue
            if candidate == target:
                return candidate
            try:
                candidate.rename(target)
                return target
            except OSError as exc:
                logger.warning("No se pudo renombrar %s a %s: %s", candidate, target, exc)
                return candidate
    except FileNotFoundError:
        CONFIG_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return target

def github_path_for_company(company_id: str, local_path: Path) -> str:
    sanitized = sanitize_company_id(company_id)
    if GITHUB_FILE_PATH:
        template = GITHUB_FILE_PATH
        if '{empresa}' in template and '{company}' not in template:
            template = template.replace('{empresa}', '{company}')
        if '{company}' in template:
            return template.format(company=sanitized)
        base_path = Path(template)
        if base_path.suffix:
            directory = base_path.parent
            if sanitized == DEFAULT_COMPANY_ID:
                target = base_path
            else:
                filename = f"{sanitized}{CONFIG_FILENAME_SUFFIX}"
                target = directory / filename if directory.parts else Path(filename)
        else:
            target = base_path / f"{sanitized}{CONFIG_FILENAME_SUFFIX}"
        return str(target).replace('\\', '/')
    try:
        relative = local_path.relative_to(CONFIG_STORAGE_DIR)
        rel_path = relative.as_posix()
        if rel_path:
            return rel_path
    except ValueError:
        pass
    return local_path.name


def current_utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def firebase_timestamp_to_iso(value: Optional[int]) -> Optional[str]:
    if value in (None, 0):
        return None
    try:
        return datetime.utcfromtimestamp(int(value) / 1000).replace(microsecond=0).isoformat() + "Z"
    except Exception:
        return None


def normalize_company_entry(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    raw_id = entry.get("empresaId") or entry.get("empresa_id") or entry.get("id") or entry.get("slug")
    try:
        empresa_id = sanitize_company_id(raw_id) if raw_id is not None else None
    except ValueError:
        empresa_id = None
    if not empresa_id:
        return None
    name = str(entry.get("name") or entry.get("displayName") or empresa_id).strip() or empresa_id
    description = str(entry.get("description") or entry.get("notes") or "").strip()
    active_value = entry.get("active")
    active = bool(active_value) if active_value is not None else True
    created_at = str(entry.get("createdAt") or entry.get("created_at") or entry.get("created") or "")
    updated_at = str(entry.get("updatedAt") or entry.get("updated_at") or entry.get("updated") or "")
    now = current_utc_iso()
    if not created_at:
        created_at = now
    if not updated_at:
        updated_at = created_at
    broker_candidate = (
        entry.get("mqttBrokerKey")
        or entry.get("mqtt_broker_key")
        or entry.get("mqttBroker")
        or entry.get("brokerKey")
        or entry.get("broker")
    )
    broker_key = DEFAULT_BROKER_KEY
    if broker_candidate:
        try:
            broker_key = sanitize_broker_key(broker_candidate)
        except ValueError:
            logger.warning("Clave de broker invalida %s para empresa %s; usando default", broker_candidate, empresa_id)
            broker_key = DEFAULT_BROKER_KEY
    if AVAILABLE_BROKER_KEYS and broker_key not in AVAILABLE_BROKER_KEYS:
        logger.warning("Broker %s no configurado; usando default para empresa %s", broker_key, empresa_id)
        broker_key = DEFAULT_BROKER_KEY
    return {
        "empresaId": empresa_id,
        "name": name,
        "description": description,
        "active": active,
        "createdAt": created_at,
        "updatedAt": updated_at,
        "mqttBrokerKey": broker_key,
    }


def load_companies() -> List[Dict[str, Any]]:
    with COMPANIES_LOCK:
        try:
            with COMPANIES_PATH.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except FileNotFoundError:
            raw = None
        except json.JSONDecodeError as exc:
            logger.warning("companies.json invalido: %s", exc)
            raw = None
    if isinstance(raw, dict):
        items = raw.get("companies") or raw.get("tenants") or raw.get("items") or []
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    companies: Dict[str, Dict[str, Any]] = {}
    for entry in items:
        normalized = normalize_company_entry(entry)
        if not normalized:
            continue
        companies[normalized["empresaId"]] = normalized
    if DEFAULT_COMPANY_ID and DEFAULT_COMPANY_ID not in companies:
        now = current_utc_iso()
        companies[DEFAULT_COMPANY_ID] = {
            "empresaId": DEFAULT_COMPANY_ID,
            "name": DEFAULT_COMPANY_ID,
            "description": "",
            "active": True,
            "createdAt": now,
            "updatedAt": now,
            "mqttBrokerKey": DEFAULT_BROKER_KEY,
        }
    sorted_companies = sorted(
        companies.values(),
        key=lambda item: (item["empresaId"] != DEFAULT_COMPANY_ID, item["name"].lower(), item["empresaId"])
    )
    with COMPANY_BROKER_LOCK:
        COMPANY_BROKER_MAP.clear()
        for entry in sorted_companies:
            COMPANY_BROKER_MAP[entry["empresaId"]] = entry.get("mqttBrokerKey") or DEFAULT_BROKER_KEY
    return sorted_companies


def save_companies(companies: List[Dict[str, Any]]) -> None:
    sanitized: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for entry in companies:
        normalized = normalize_company_entry(entry)
        if not normalized:
            continue
        empresa_id = normalized["empresaId"]
        if empresa_id in seen:
            continue
        seen.add(empresa_id)
        sanitized.append(normalized)
    if DEFAULT_COMPANY_ID and DEFAULT_COMPANY_ID not in seen:
        now = current_utc_iso()
        sanitized.append({
            "empresaId": DEFAULT_COMPANY_ID,
            "name": DEFAULT_COMPANY_ID,
            "description": "",
            "active": True,
            "createdAt": now,
            "updatedAt": now,
            "mqttBrokerKey": DEFAULT_BROKER_KEY,
        })
    sanitized.sort(key=lambda item: (item["empresaId"] != DEFAULT_COMPANY_ID, item["name"].lower(), item["empresaId"]))
    payload = {"companies": sanitized, "updatedAt": current_utc_iso()}
    with COMPANIES_LOCK:
        COMPANIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with COMPANIES_PATH.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    with COMPANY_BROKER_LOCK:
        COMPANY_BROKER_MAP.clear()
        for entry in sanitized:
            COMPANY_BROKER_MAP[entry["empresaId"]] = entry.get("mqttBrokerKey") or DEFAULT_BROKER_KEY


def find_company(companies: List[Dict[str, Any]], empresa_id: str) -> Optional[Dict[str, Any]]:
    try:
        sanitized = sanitize_company_id(empresa_id)
    except ValueError:
        return None
    for entry in companies:
        if entry.get("empresaId") == sanitized:
            return entry
    return None


def broker_key_for_company(company_id: str) -> str:
    try:
        sanitized = sanitize_company_id(company_id)
    except ValueError:
        return DEFAULT_BROKER_KEY
    with COMPANY_BROKER_LOCK:
        cached = COMPANY_BROKER_MAP.get(sanitized)
    if cached and cached in AVAILABLE_BROKER_KEYS:
        return cached
    load_companies()
    with COMPANY_BROKER_LOCK:
        cached = COMPANY_BROKER_MAP.get(sanitized)
    if cached and cached in AVAILABLE_BROKER_KEYS:
        return cached
    return DEFAULT_BROKER_KEY


def is_master_admin(decoded: Optional[Dict[str, Any]]) -> bool:
    if not decoded:
        return False
    for key in MASTER_ADMIN_FLAG_KEYS:
        value = decoded.get(key)
        if isinstance(value, bool) and value:
            return True
    for key in ("tenantRole", "role", "scadaRole", "empresaRole"):
        value = decoded.get(key)
        if isinstance(value, str) and value.strip().lower() in MASTER_ADMIN_ROLE_NAMES:
            return True
    email = decoded.get("email")
    if email and email.lower() in MASTER_ADMIN_EMAILS_LOWER:
        return True
    return False


def ensure_master_admin(decoded: Optional[Dict[str, Any]]) -> None:
    if not is_master_admin(decoded):
        raise HTTPException(status_code=403, detail="Solo administradores maestros")

ADMIN_EMAILS = [email.strip() for email in os.getenv('CONFIG_ADMIN_EMAILS', '').split(',') if email.strip()]
ADMIN_EMAILS_LOWER = {email.lower() for email in ADMIN_EMAILS}

MASTER_ADMIN_EMAILS = [email.strip() for email in os.getenv('MASTER_ADMIN_EMAILS', '').split(',') if email.strip()]
MASTER_ADMIN_EMAILS_LOWER = {email.lower() for email in MASTER_ADMIN_EMAILS}
MASTER_ADMIN_ROLE_NAMES = {role.strip().lower() for role in os.getenv('MASTER_ADMIN_ROLE_NAMES', 'master,root').split(',') if role.strip()}
MASTER_ADMIN_FLAG_KEYS = tuple(key.strip() for key in os.getenv('MASTER_ADMIN_FLAG_KEYS', 'isMasterAdmin,masterAdmin,superAdmin,isSuperUser').split(',') if key.strip()) or ('isMasterAdmin', 'masterAdmin', 'superAdmin', 'isSuperUser')

GITHUB_SYNC_ENABLED = os.getenv("GITHUB_SYNC_ENABLED", "0").strip() == "1"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "").strip()
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip()
GITHUB_FILE_PATH = os.getenv("GITHUB_FILE_PATH", "scada_configs/{company}_Scada_Config.json").strip().lstrip("/")
GITHUB_API_URL = os.getenv("GITHUB_API_URL", "https://api.github.com").strip().rstrip("/")
GITHUB_API_VERSION = os.getenv("GITHUB_API_VERSION", "2022-11-28").strip()
GITHUB_HTTP_TIMEOUT = float(os.getenv("GITHUB_HTTP_TIMEOUT", "20"))
GITHUB_COMMITTER_NAME = os.getenv("GITHUB_COMMITTER_NAME", "SCADA Bot").strip() or "SCADA Bot"
GITHUB_COMMITTER_EMAIL = os.getenv("GITHUB_COMMITTER_EMAIL", "scada-bot@example.com").strip() or "scada-bot@example.com"
GITHUB_COMMIT_MESSAGE = os.getenv("GITHUB_COMMIT_MESSAGE", "Actualiza scada_config.json desde SCADA Web").strip() or "Actualiza scada_config.json desde SCADA Web"
GITHUB_AUTHOR_NAME = os.getenv("GITHUB_AUTHOR_NAME", "").strip()
EMPRESA_CLAIM_KEYS = ("empresaId", "empresa_id", "empresa", "companyId", "company_id", "company", "tenantId", "tenant_id", "tenant")
GOOGLE_REQUEST = google_requests.Request()
ROLE_KEY_MAP = {
    "admin": "admins",
    "operador": "operators",
    "visualizacion": "viewers",
}
ALLOWED_USER_ROLES = tuple(ROLE_KEY_MAP.keys())


class GithubSyncError(Exception):
    """Raised when GitHub synchronisation fails."""
    pass


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
MQTT_KEEPALIVE = int(os.getenv("MQTT_KEEPALIVE", "30"))
MQTT_BROKER_PROFILES_RAW = os.getenv("MQTT_BROKER_PROFILES", "").strip()

TOPIC_BASE = os.getenv("TOPIC_BASE", "scada/customers").strip()
PUBLIC_ALLOWED_PREFIXES = [p.strip() for p in os.getenv("PUBLIC_ALLOWED_PREFIXES", "").split(",") if p.strip()]

FIREBASE_SERVICE_ACCOUNT = os.getenv("FIREBASE_SERVICE_ACCOUNT", "").strip()
FIREBASE_WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY", "").strip()
FIREBASE_EMAIL_CONTINUE_URL = os.getenv("FIREBASE_EMAIL_CONTINUE_URL", "").strip()
FIREBASE_AUTH_TIMEOUT = float(os.getenv("FIREBASE_AUTH_TIMEOUT", "10"))
IDENTITY_TOOLKIT_URL = "https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode"

if not FIREBASE_PROJECT_ID:
    raise RuntimeError("FIREBASE_PROJECT_ID is required")
if not (MQTT_HOST or MQTT_BROKER_PROFILES_RAW):
    raise RuntimeError("HIVEMQ_HOST is required (o configure MQTT_BROKER_PROFILES)")


@dataclass
class BrokerProfile:
    key: str
    host: str
    port: int
    username: str
    password: str
    tls: bool
    tls_insecure: bool
    ca_cert_path: Optional[str]
    client_id: Optional[str]
    keepalive: int

    def client_identifier(self, base_client_id: str) -> str:
        if self.client_id:
            return self.client_id
        if self.key == DEFAULT_BROKER_KEY:
            return base_client_id
        return f"{base_client_id}-{self.key}"


class BrokerManager:
    def __init__(self, base_profile: Dict[str, Any], raw_profiles: str, topic_base: str,
                 public_prefixes: List[str], default_client_id: str):
        self.base_profile = dict(base_profile)
        self.raw_profiles = raw_profiles
        self.topic_base = topic_base
        self.public_prefixes = list(public_prefixes)
        self.default_client_id = default_client_id
        self.profiles: Dict[str, BrokerProfile] = {}
        self.clients: Dict[str, mqtt.Client] = {}
        self.connected_events: Dict[str, threading.Event] = {}
        self._parse_profiles()
        self._init_clients()

    def _parse_profiles(self) -> None:
        definitions: Dict[str, Dict[str, Any]] = {}
        if self.raw_profiles:
            try:
                raw_data = json.loads(self.raw_profiles)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"MQTT_BROKER_PROFILES JSON invalido: {exc}") from exc
            if not isinstance(raw_data, dict):
                raise RuntimeError("MQTT_BROKER_PROFILES debe ser un objeto JSON {\"brokerKey\": {}}")
            for raw_key, raw_conf in raw_data.items():
                try:
                    key = sanitize_broker_key(raw_key)
                except ValueError as exc:
                    raise RuntimeError(f"Clave de broker invalida '{raw_key}': {exc}") from exc
                if not isinstance(raw_conf, dict):
                    raise RuntimeError(f"La configuracion del broker '{raw_key}' debe ser un objeto JSON")
                merged = dict(self.base_profile)
                merged.update(raw_conf)
                definitions[key] = merged
        base_default = dict(self.base_profile)
        if DEFAULT_BROKER_KEY in definitions:
            merged_default = dict(base_default)
            merged_default.update(definitions[DEFAULT_BROKER_KEY])
            definitions[DEFAULT_BROKER_KEY] = merged_default
        else:
            definitions[DEFAULT_BROKER_KEY] = base_default
        parsed: Dict[str, BrokerProfile] = {}
        for key, payload in definitions.items():
            host = coerce_str(payload.get("host"), "")
            if not host:
                raise RuntimeError(f"El perfil de broker '{key}' requiere el campo 'host'")
            port = coerce_int(payload.get("port"), self.base_profile.get("port") or MQTT_PORT or 8883)
            username = coerce_str(payload.get("username"), self.base_profile.get("username", ""))
            password = coerce_str(payload.get("password"), self.base_profile.get("password", ""))
            tls = coerce_bool(payload.get("tls"), coerce_bool(self.base_profile.get("tls"), MQTT_TLS))
            tls_insecure = coerce_bool(payload.get("tlsInsecure"), coerce_bool(self.base_profile.get("tlsInsecure"), MQTT_TLS_INSECURE))
            ca_cert_path = coerce_str(payload.get("caCertPath"), self.base_profile.get("caCertPath", ""))
            client_id = payload.get("clientId")
            if client_id is not None:
                client_id = coerce_str(client_id, "")
                if not client_id:
                    client_id = None
            keepalive = coerce_int(payload.get("keepalive"), self.base_profile.get("keepalive") or MQTT_KEEPALIVE)
            keepalive = keepalive if keepalive > 0 else MQTT_KEEPALIVE
            parsed[key] = BrokerProfile(
                key=key,
                host=host,
                port=port,
                username=username,
                password=password,
                tls=tls,
                tls_insecure=tls_insecure,
                ca_cert_path=ca_cert_path or None,
                client_id=client_id,
                keepalive=keepalive,
            )
        if DEFAULT_BROKER_KEY not in parsed:
            raise RuntimeError("Debe existir al menos el perfil MQTT 'default'")
        self.profiles = parsed
        global AVAILABLE_BROKER_KEYS
        AVAILABLE_BROKER_KEYS = set(parsed.keys())

    def _init_clients(self) -> None:
        for key, profile in self.profiles.items():
            self._init_client(profile)

    def _init_client(self, profile: BrokerProfile) -> None:
        client_id = profile.client_identifier(self.default_client_id)
        client = mqtt.Client(client_id=client_id, clean_session=True)
        client.enable_logger()
        client.user_data_set({"broker_key": profile.key})
        if profile.tls:
            if profile.ca_cert_path:
                client.tls_set(ca_certs=profile.ca_cert_path, certfile=None, keyfile=None, tls_version=ssl.PROTOCOL_TLS)
            else:
                client.tls_set(tls_version=ssl.PROTOCOL_TLS)
            client.tls_insecure_set(profile.tls_insecure)
        if profile.username:
            client.username_pw_set(profile.username, profile.password or None)
        event = threading.Event()
        self.connected_events[profile.key] = event

        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                event.set()
                logger.info("MQTT connected broker=%s host=%s", profile.key, profile.host)
                base = self.topic_base if self.topic_base.endswith("#") else (self.topic_base.rstrip("/") + "/#")
                client.subscribe(base, qos=1)
                for p in self.public_prefixes:
                    topic = p if p.endswith("#") else (p.rstrip("/") + "/#")
                    client.subscribe(topic, qos=1)
            else:
                logger.error("MQTT connection failed rc=%s broker=%s", rc, profile.key)

        def on_disconnect(client, userdata, rc):
            if rc != 0:
                logger.warning("MQTT disconnected broker=%s rc=%s", profile.key, rc)
            else:
                logger.info("MQTT disconnected broker=%s", profile.key)
            event.clear()

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = self._make_on_message(profile.key)
        try:
            client.connect_async(profile.host, profile.port, keepalive=profile.keepalive)
        except Exception as exc:
            logger.exception("No se pudo iniciar conexion MQTT broker=%s: %s", profile.key, exc)
            raise
        client.loop_start()
        self.clients[profile.key] = client

    def _make_on_message(self, broker_key: str):
        def _handler(client, userdata, msg):
            decoded_payload = try_decode(msg.payload)
            logger.info("MQTT inbound broker=%s topic=%s qos=%s retain=%s", broker_key, msg.topic, msg.qos, msg.retain)
            data = {
                "topic": msg.topic,
                "payload": decoded_payload,
                "qos": msg.qos,
                "retain": msg.retain,
                "broker": broker_key,
            }
            remember_message(data)
            ConnectionManager.broadcast(msg.topic, data)
        return _handler

    def resolve_key(self, broker_key: Optional[str]) -> str:
        if broker_key and broker_key in self.profiles:
            return broker_key
        return DEFAULT_BROKER_KEY

    def ensure_connected(self, broker_key: Optional[str], timeout: float = 10.0) -> str:
        resolved = self.resolve_key(broker_key)
        event = self.connected_events.get(resolved)
        if event is None:
            raise HTTPException(status_code=500, detail=f"MQTT broker '{resolved}' no configurado")
        if not event.wait(timeout):
            raise HTTPException(status_code=503, detail=f"MQTT broker '{resolved}' no conectado")
        return resolved

    def publish(self, broker_key: Optional[str], topic: str, payload: Any, qos: int, retain: bool):
        resolved = self.ensure_connected(broker_key)
        client = self.clients.get(resolved)
        if client is None:
            raise HTTPException(status_code=500, detail=f"MQTT broker '{resolved}' no inicializado")
        result = client.publish(topic, payload=payload, qos=qos, retain=retain)
        return resolved, result

    def available_keys(self) -> List[str]:
        return list(self.profiles.keys())


BASE_BROKER_PROFILE = {
    "host": MQTT_HOST,
    "port": MQTT_PORT,
    "username": MQTT_USERNAME,
    "password": MQTT_PASSWORD,
    "tls": MQTT_TLS,
    "tlsInsecure": MQTT_TLS_INSECURE,
    "caCertPath": MQTT_CA_CERT_PATH,
    "keepalive": MQTT_KEEPALIVE,
}

broker_manager = BrokerManager(
    base_profile=BASE_BROKER_PROFILE,
    raw_profiles=MQTT_BROKER_PROFILES_RAW,
    topic_base=TOPIC_BASE,
    public_prefixes=PUBLIC_ALLOWED_PREFIXES,
    default_client_id=MQTT_CLIENT_ID,
)

# Inicializa el mapa de brokers por empresa a partir del archivo local
load_companies()

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

# ---- MQTT last message cache ----
last_message_store: Dict[str, Dict[str, Any]] = {}
last_message_lock = threading.Lock()


def remember_message(data: Dict[str, Any]) -> None:
    topic = data.get("topic")
    if not topic:
        return
    entry = {
        "topic": topic,
        "payload": data.get("payload"),
        "retain": bool(data.get("retain")),
        "qos": int(data.get("qos", 0))
    }
    broker_key = data.get("broker")
    if broker_key:
        entry["broker"] = broker_key
    with last_message_lock:
        last_message_store[topic] = entry



def snapshot_for_prefixes(prefixes: List[str], broker_key: Optional[str] = None) -> List[Dict[str, Any]]:
    normalized = [p.rstrip("/") + "/" for p in prefixes]
    with last_message_lock:
        results: List[Dict[str, Any]] = []
        for topic, entry in last_message_store.items():
            if broker_key and entry.get("broker") and entry.get("broker") != broker_key:
                continue
            if any((topic.rstrip("/") + "/").startswith(pref) for pref in normalized):
                results.append(dict(entry))
        return results

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
    empresa_candidate = result.get("empresaId") or result.get("empresa_id") or result.get("companyId") or result.get("company_id")
    if empresa_candidate:
        try:
            result["empresaId"] = sanitize_company_id(empresa_candidate)
        except ValueError:
            result["empresaId"] = DEFAULT_COMPANY_ID
    else:
        result["empresaId"] = DEFAULT_COMPANY_ID
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


def fetch_config_from_github(company_id: str, local_path: Path) -> Optional[Dict[str, Any]]:
    if not GITHUB_SYNC_ENABLED:
        return None
    if not GITHUB_TOKEN or not GITHUB_REPO:
        logger.warning("GitHub fetch omitido: falta GITHUB_TOKEN o GITHUB_REPO")
        return None
    api_base = GITHUB_API_URL or "https://api.github.com"
    remote_path = github_path_for_company(company_id, local_path)
    url = f"{api_base}/repos/{GITHUB_REPO}/contents/{remote_path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    if GITHUB_API_VERSION:
        headers["X-GitHub-Api-Version"] = GITHUB_API_VERSION
    params = {"ref": GITHUB_BRANCH} if GITHUB_BRANCH else None
    timeout = GITHUB_HTTP_TIMEOUT if GITHUB_HTTP_TIMEOUT > 0 else 20.0
    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
    except requests.RequestException as exc:
        logger.error("No se pudo obtener config %s desde GitHub: %s", remote_path, exc)
        return None
    if response.status_code == 404:
        logger.warning("Config %s no encontrada en GitHub", remote_path)
        return None
    if response.status_code != 200:
        logger.error("GitHub respondio %s al obtener %s: %s", response.status_code, remote_path, response.text)
        raise HTTPException(status_code=502, detail="Error al obtener configuracion desde GitHub")
    payload = response.json()
    encoded = payload.get("content")
    if not encoded:
        logger.error("Respuesta de GitHub sin contenido para %s", remote_path)
        raise HTTPException(status_code=502, detail="Contenido de GitHub invalido")
    encoding = payload.get("encoding", "base64")
    if encoding != "base64":
        logger.error("GitHub devolvio encoding %s para %s", encoding, remote_path)
        raise HTTPException(status_code=502, detail="Codificacion de GitHub no soportada")
    try:
        raw_bytes = base64.b64decode(encoded)
        text_payload = raw_bytes.decode("utf-8")
    except Exception as exc:
        logger.error("No se pudo decodificar contenido de GitHub para %s: %s", remote_path, exc)
        raise HTTPException(status_code=502, detail="Contenido de GitHub no decodificable")
    try:
        data = json.loads(text_payload)
    except json.JSONDecodeError as exc:
        logger.error("Config JSON invalido obtenido de GitHub para %s: %s", remote_path, exc)
        raise HTTPException(status_code=500, detail="Configuracion remota invalida")
    normalized = normalize_config(data if isinstance(data, dict) else {})
    normalized["empresaId"] = company_id
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with local_path.open("w", encoding="utf-8") as fh:
        json.dump(normalized, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    logger.info("Config %s cargada desde GitHub", remote_path)
    return normalized


def load_scada_config(company_id: str) -> Dict[str, Any]:
    try:
        sanitized = sanitize_company_id(company_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Empresa inválida: {exc}") from exc
    path = config_path_for_company(sanitized)
    legacy_path: Optional[Path] = None
    if sanitized == DEFAULT_COMPANY_ID and LEGACY_SINGLE_CONFIG_PATH is not None and LEGACY_SINGLE_CONFIG_PATH.exists():
        legacy_path = LEGACY_SINGLE_CONFIG_PATH
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        if legacy_path:
            logger.info("Migrating legacy config from %s to %s", legacy_path, path)
            try:
                with legacy_path.open("r", encoding="utf-8") as legacy_fh:
                    legacy_data = json.load(legacy_fh)
            except json.JSONDecodeError as exc:
                logger.error("Legacy config JSON invalid for %s: %s", legacy_path, exc)
                raise HTTPException(status_code=500, detail="Invalid configuration file")
            normalized = normalize_config(legacy_data)
            normalized["empresaId"] = sanitized
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as fh:
                json.dump(normalized, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            return normalized
        fetched = fetch_config_from_github(sanitized, path)
        if fetched is not None:
            return fetched
        logger.warning("Config file %s not found for empresa %s, using defaults", path, sanitized)
        data = {}
    except json.JSONDecodeError as exc:
        logger.error("Config JSON invalid for %s: %s", path, exc)
        raise HTTPException(status_code=500, detail="Invalid configuration file")
    normalized = normalize_config(data)
    normalized["empresaId"] = sanitized
    return normalized


def save_scada_config(data: Dict[str, Any], company_id: str, actor_email: Optional[str] = None) -> None:
    try:
        path = config_path_for_company(company_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Empresa inválida: {exc}") from exc
    payload = dict(data)
    payload["empresaId"] = company_id
    normalized = normalize_config(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(normalized, ensure_ascii=False, indent=2)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(serialized)
        fh.write("\n")
    sync_config_to_github(serialized, actor_email, company_id, path)

def build_commit_message(actor_email: Optional[str], company_id: str) -> str:
    base = GITHUB_COMMIT_MESSAGE or "Actualiza scada_config.json desde SCADA Web"
    suffix = f" [{company_id}]"
    if actor_email:
        return f"{base}{suffix} ({actor_email})"
    return f"{base}{suffix}"


def build_author_payload(actor_email: Optional[str]) -> Optional[Dict[str, str]]:
    if not actor_email:
        return None
    author_name = GITHUB_AUTHOR_NAME or actor_email.split("@", 1)[0] or "SCADA Editor"
    return {"name": author_name, "email": actor_email}


def sync_config_to_github(serialized: str, actor_email: Optional[str], company_id: str, local_path: Path) -> None:
    if not GITHUB_SYNC_ENABLED:
        return
    if not GITHUB_TOKEN or not GITHUB_REPO:
        raise GithubSyncError("GITHUB_TOKEN y GITHUB_REPO son obligatorios cuando GITHUB_SYNC_ENABLED=1")

    api_base = GITHUB_API_URL or "https://api.github.com"
    remote_path = github_path_for_company(company_id, local_path)
    url = f"{api_base}/repos/{GITHUB_REPO}/contents/{remote_path}"

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    if GITHUB_API_VERSION:
        headers["X-GitHub-Api-Version"] = GITHUB_API_VERSION

    params = {"ref": GITHUB_BRANCH} if GITHUB_BRANCH else None
    timeout = GITHUB_HTTP_TIMEOUT if GITHUB_HTTP_TIMEOUT > 0 else 20.0

    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise GithubSyncError(f"No se pudo consultar GitHub: {exc}") from exc

    sha = None
    if response.status_code == 200:
        payload = response.json()
        sha = payload.get("sha")
        existing_encoded = payload.get("content", "")
        try:
            existing_text = base64.b64decode(existing_encoded.encode("ascii")).decode("utf-8")
        except Exception:
            existing_text = None
        if existing_text is not None and existing_text.strip() == serialized.strip():
            logger.info("GitHub sync omitido: sin cambios detectados para %s", remote_path)
            return
    elif response.status_code != 404:
        raise GithubSyncError(f"GitHub respondio {response.status_code} al consultar el archivo: {response.text}")

    body = {
        "message": build_commit_message(actor_email, company_id),
        "content": base64.b64encode(serialized.encode("utf-8")).decode("ascii"),
    }
    if GITHUB_BRANCH:
        body["branch"] = GITHUB_BRANCH
    if sha:
        body["sha"] = sha

    author_payload = build_author_payload(actor_email)
    if author_payload:
        body["author"] = author_payload
    if GITHUB_COMMITTER_NAME and GITHUB_COMMITTER_EMAIL:
        body["committer"] = {"name": GITHUB_COMMITTER_NAME, "email": GITHUB_COMMITTER_EMAIL}

    try:
        put_resp = requests.put(url, headers=headers, json=body, timeout=timeout)
    except requests.RequestException as exc:
        raise GithubSyncError(f"No se pudo actualizar GitHub: {exc}") from exc

    if put_resp.status_code not in (200, 201):
        raise GithubSyncError(f"GitHub respondio {put_resp.status_code} al actualizar: {put_resp.text}")

    logger.info("GitHub sync completado para %s en rama %s", remote_path, GITHUB_BRANCH or "default")

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


def ensure_admin(email: Optional[str], company_id: str, cfg: Optional[Dict[str, Any]] = None) -> None:
    if not email:
        raise HTTPException(status_code=403, detail="Usuario sin email en token")
    lower_email = email.lower()
    if lower_email in ADMIN_EMAILS_LOWER:
        return
    cfg = cfg or load_scada_config(company_id)
    roles = cfg.get("roles", {})
    admin_list = [str(item).lower() for item in roles.get("admins", [])]
    if lower_email in admin_list:
        return
    raise HTTPException(status_code=403, detail="Usuario no autorizado para modificar la configuraciÃ³n")

def sanitize_user_role(value: Optional[str]) -> str:
    role = (value or "operador").strip().lower()
    if role not in ALLOWED_USER_ROLES:
        raise HTTPException(status_code=400, detail=f"Rol invalido: {value}")
    return role

def normalize_role_lists(cfg: Dict[str, Any]) -> Dict[str, List[str]]:
    roles = cfg.get("roles")
    if not isinstance(roles, dict):
        roles = {}
    normalized: Dict[str, List[str]] = {}
    for key in ROLE_KEY_MAP.values():
        raw_list = roles.get(key, [])
        if isinstance(raw_list, list):
            normalized[key] = [str(item).strip() for item in raw_list if str(item).strip()]
        elif isinstance(raw_list, str):
            normalized[key] = [segment.strip() for segment in raw_list.split(",") if segment.strip()]
        else:
            normalized[key] = []
    return normalized

def apply_role_to_config(company_id: str, email: str, role: str, actor_email: Optional[str]) -> None:
    cfg = load_scada_config(company_id)
    normalized = normalize_config(cfg)
    roles = normalize_role_lists(normalized)
    lower_email = email.lower()
    for key, values in roles.items():
        roles[key] = [item for item in values if item.lower() != lower_email]
    target_key = ROLE_KEY_MAP[role]
    roles[target_key].append(email.strip())
    roles[target_key] = sorted(dict.fromkeys(roles[target_key]), key=lambda item: item.lower())
    normalized["roles"] = roles
    normalized["empresaId"] = company_id
    save_scada_config(normalized, company_id, actor_email or "system")

def remove_user_from_config(company_id: str, email: Optional[str], actor_email: Optional[str]) -> None:
    if not email:
        return
    cfg = load_scada_config(company_id)
    normalized = normalize_config(cfg)
    roles = normalize_role_lists(normalized)
    lower_email = email.lower()
    changed = False
    for key, values in roles.items():
        filtered = [item for item in values if item.lower() != lower_email]
        if filtered != values:
            roles[key] = filtered
            changed = True
    if not changed:
        return
    normalized["roles"] = roles
    normalized["empresaId"] = company_id
    save_scada_config(normalized, company_id, actor_email or "system")

def ensure_company_admin(decoded: Dict[str, Any], target_company_id: str) -> str:
    try:
        sanitized = sanitize_company_id(target_company_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"empresaId invalido: {exc}") from exc
    if is_master_admin(decoded):
        return sanitized
    claimed = extract_company_id(decoded)
    if claimed != sanitized:
        raise HTTPException(status_code=403, detail="No puedes operar sobre otra empresa")
    ensure_admin(decoded.get("email"), sanitized)
    return sanitized

def company_id_from_claims(claims: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(claims, dict):
        return None
    for key in EMPRESA_CLAIM_KEYS:
        value = claims.get(key)
        if not value:
            continue
        try:
            return sanitize_company_id(value)
        except ValueError:
            continue
    return None

def merge_custom_claims(existing: Optional[Dict[str, Any]], company_id: str, role: Optional[str]) -> Dict[str, Any]:
    claims = dict(existing or {})
    for key in EMPRESA_CLAIM_KEYS:
        claims[key] = company_id
    if role:
        claims["scadaRole"] = role
        claims["role"] = role
        claims["tenantRole"] = role
        claims["empresaRole"] = role
    return claims

def build_action_code_settings(override_url: Optional[str] = None) -> Optional[firebase_auth.ActionCodeSettings]:
    url = override_url or FIREBASE_EMAIL_CONTINUE_URL
    if not url:
        return None
    return firebase_auth.ActionCodeSettings(url=url, handle_code_in_app=False)

def send_password_reset_email(email: str, continue_url: Optional[str]) -> bool:
    if not FIREBASE_WEB_API_KEY:
        return False
    payload: Dict[str, Any] = {
        "requestType": "PASSWORD_RESET",
        "email": email,
        "returnOobLink": False,
    }
    url = continue_url or FIREBASE_EMAIL_CONTINUE_URL
    if url:
        payload["continueUrl"] = url
    try:
        response = requests.post(
            f"{IDENTITY_TOOLKIT_URL}?key={FIREBASE_WEB_API_KEY}",
            json=payload,
            timeout=FIREBASE_AUTH_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("No se pudo enviar correo de recuperacion a %s: %s", email, exc)
        return False
    if response.status_code != 200:
        logger.warning("Firebase sendOobCode respondio %s para %s: %s", response.status_code, email, response.text)
        return False
    return True




def list_company_users(company_id: str) -> List[Dict[str, Any]]:
    try:
        page = firebase_auth.list_users()
    except firebase_exceptions.FirebaseError as exc:
        logger.exception("No se pudo listar usuarios: %s", exc)
        raise HTTPException(status_code=502, detail="No se pudo consultar usuarios") from exc
    cfg = load_scada_config(company_id)
    normalized = normalize_config(cfg)
    roles = normalize_role_lists(normalized)
    role_lookup: Dict[str, str] = {}
    for role_name, key in ROLE_KEY_MAP.items():
        for email in roles.get(key, []):
            lower = email.lower()
            if lower:
                role_lookup[lower] = role_name
    results: List[Dict[str, Any]] = []
    while page is not None:
        for user in page.users:
            email = user.email or ""
            custom_claims = user.custom_claims or {}
            claim_company = company_id_from_claims(custom_claims)
            tenant_id = getattr(user, "tenant_id", None)
            if not claim_company and tenant_id:
                try:
                    claim_company = sanitize_company_id(tenant_id)
                except ValueError:
                    claim_company = None
            matches_company = False
            if claim_company == company_id:
                matches_company = True
            elif not claim_company and email and email.lower() in role_lookup:
                matches_company = True
            if not matches_company:
                continue
            role = custom_claims.get("scadaRole") or custom_claims.get("tenantRole") or custom_claims.get("role")
            if not role and email:
                role = role_lookup.get(email.lower(), "operador")
            role = role or "operador"
            metadata = getattr(user, "user_metadata", None)
            created_at = firebase_timestamp_to_iso(getattr(metadata, "creation_timestamp", None)) if metadata else None
            last_login = firebase_timestamp_to_iso(getattr(metadata, "last_sign_in_timestamp", None)) if metadata else None
            results.append({
                "uid": user.uid,
                "email": email,
                "displayName": user.display_name or "",
                "empresaId": claim_company or company_id,
                "role": role,
                "emailVerified": bool(user.email_verified),
                "disabled": bool(user.disabled),
                "createdAt": created_at,
                "lastLoginAt": last_login,
                "isMasterAdmin": bool(custom_claims.get("isMasterAdmin") or custom_claims.get("masterAdmin") or custom_claims.get("superAdmin") or custom_claims.get("isSuperUser")),
            })
        page = page.get_next_page() if hasattr(page, "get_next_page") else None
    results.sort(key=lambda item: item.get("email", "").lower())
    return results

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


# ---- WebSocket connection manager ----
class WSClient:
    def __init__(self, ws: WebSocket, uid: str, company_id: str, allowed_prefixes: List[str], broker_key: str):
        self.ws = ws
        self.uid = uid
        self.company_id = company_id
        self.allowed_prefixes = [p.rstrip("/") + "/" for p in allowed_prefixes]
        self.broker_key = broker_key

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
                data_broker = data.get("broker")
                if data_broker and getattr(c, "broker_key", DEFAULT_BROKER_KEY) != data_broker:
                    continue
                if loop is None:
                    logger.warning("WS deliver skipped; no event loop topic=%s", topic)
                    continue
                future = asyncio.run_coroutine_threadsafe(c.ws.send_json(data), loop)
                try:
                    future.result(timeout=5)
                    delivered += 1
                    logger.info(
                        "WS deliver topic=%s uid=%s empresa=%s broker=%s",
                        topic,
                        c.uid,
                        getattr(c, "company_id", None),
                        getattr(c, "broker_key", DEFAULT_BROKER_KEY),
                    )
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


def extract_company_id(decoded: Dict[str, Any]) -> str:
    candidates: List[str] = []
    for key in EMPRESA_CLAIM_KEYS:
        value = decoded.get(key)
        if value:
            candidates.append(value)
    firebase_claims = decoded.get("firebase")
    if isinstance(firebase_claims, dict):
        tenant = firebase_claims.get("tenant")
        if tenant:
            candidates.append(tenant)
    custom_claims = decoded.get("claims")
    if isinstance(custom_claims, dict):
        for key in EMPRESA_CLAIM_KEYS:
            value = custom_claims.get(key)
            if value:
                candidates.append(value)
    for candidate in candidates:
        try:
            return sanitize_company_id(candidate)
        except ValueError:
            continue
    if DEFAULT_COMPANY_ID:
        logger.warning("Token sin empresa; usando DEFAULT_EMPRESA_ID=%s", DEFAULT_COMPANY_ID)
        return DEFAULT_COMPANY_ID
    raise HTTPException(status_code=403, detail="El usuario no tiene empresa asignada")
def allowed_prefixes_for_user(uid: str, company_id: Optional[str]) -> List[str]:
    base = TOPIC_BASE.rstrip("/")
    if company_id:
        scoped = f"{base}/{company_id}"
    else:
        scoped = f"{base}/{uid}"
    prefixes = [scoped]
    prefixes.extend(PUBLIC_ALLOWED_PREFIXES)
    return prefixes

def ensure_mqtt_connected(broker_key: Optional[str]):
    broker_manager.ensure_connected(broker_key)



@app.get("/config")
def get_config_endpoint(authorization: Optional[str] = Header(None), empresa_id: Optional[str] = Query(None)):
    decoded = verify_bearer_token(authorization)
    is_master = is_master_admin(decoded)
    if empresa_id:
        if not is_master:
            raise HTTPException(status_code=403, detail="Solo administradores maestros pueden consultar otras empresas")
        try:
            company_id = sanitize_company_id(empresa_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"empresaId invalido: {exc}") from exc
    else:
        company_id = extract_company_id(decoded)
    cfg = load_scada_config(company_id)
    cfg.setdefault("empresaId", company_id)
    email = decoded.get("email")
    role = "admin" if is_master else role_for_email(cfg, email)
    return {"config": cfg, "role": role, "empresaId": company_id, "isMaster": is_master}


@app.put("/config")
def update_config_endpoint(config: Dict[str, Any] = Body(...), authorization: Optional[str] = Header(None), empresa_id: Optional[str] = Query(None)):
    decoded = verify_bearer_token(authorization)
    email = decoded.get("email")
    is_master = is_master_admin(decoded)
    if empresa_id:
        if not is_master:
            raise HTTPException(status_code=403, detail="Solo administradores maestros pueden actualizar otras empresas")
        try:
            company_id = sanitize_company_id(empresa_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"empresaId invalido: {exc}") from exc
    else:
        company_id = extract_company_id(decoded)
    current_cfg = load_scada_config(company_id)
    if not is_master:
        ensure_admin(email, company_id, current_cfg)
    normalized = validate_config_payload(config)
    try:
        save_scada_config(normalized, company_id, email)
    except GithubSyncError as exc:
        logger.exception("GitHub sync failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"No se pudo sincronizar con GitHub: {exc}") from exc
    except Exception as exc:
        logger.exception("Error writing configuration: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudo guardar la configuracion") from exc
    role = "admin" if is_master else role_for_email(normalized, email)
    logger.info("Config updated by %s en empresa %s", email, company_id)
    return {"ok": True, "config": normalized, "role": role, "empresaId": company_id, "isMaster": is_master}


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


class TenantBase(BaseModel):
    name: str
    description: Optional[str] = None
    active: Optional[bool] = True
    mqttBrokerKey: Optional[str] = None


class TenantCreate(TenantBase):
    empresaId: str
    cloneFrom: Optional[str] = None


class TenantUpdate(TenantBase):
    active: Optional[bool] = None


class UserCreate(BaseModel):
    email: EmailStr
    empresaId: Optional[str] = None
    role: Optional[str] = "operador"
    sendInvite: bool = True


class UserResetRequest(BaseModel):
    sendEmail: bool = True
    continueUrl: Optional[str] = None


@app.get("/tenants")
def list_tenants_endpoint(authorization: Optional[str] = Header(None)):
    decoded = verify_bearer_token(authorization)
    ensure_master_admin(decoded)
    companies = load_companies()
    return {"companies": companies, "count": len(companies)}


@app.get("/tenants/{empresa_id}")
def get_tenant_endpoint(empresa_id: str, authorization: Optional[str] = Header(None)):
    decoded = verify_bearer_token(authorization)
    ensure_master_admin(decoded)
    company = find_company(load_companies(), empresa_id)
    if not company:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return {"company": company}


@app.post("/tenants", status_code=201)
def create_tenant_endpoint(payload: TenantCreate, authorization: Optional[str] = Header(None)):
    decoded = verify_bearer_token(authorization)
    ensure_master_admin(decoded)
    actor_email = decoded.get("email")
    try:
        empresa_id = sanitize_company_id(payload.empresaId)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"empresaId invalido: {exc}") from exc
    companies = load_companies()
    if any(entry.get("empresaId") == empresa_id for entry in companies):
        raise HTTPException(status_code=409, detail="La empresa ya existe")
    clone_from = None
    if payload.cloneFrom:
        try:
            clone_from = sanitize_company_id(payload.cloneFrom)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"cloneFrom invalido: {exc}") from exc
        if not any(entry.get("empresaId") == clone_from for entry in companies):
            raise HTTPException(status_code=404, detail=f"Empresa origen {clone_from} no existe")
    if payload.mqttBrokerKey:
        try:
            broker_key = sanitize_broker_key(payload.mqttBrokerKey)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"mqttBrokerKey invalido: {exc}") from exc
    else:
        broker_key = DEFAULT_BROKER_KEY
    if broker_key not in broker_manager.available_keys():
        raise HTTPException(status_code=400, detail=f"mqttBrokerKey {broker_key} no esta configurado en el backend")
    if clone_from:
        base_config = load_scada_config(clone_from)
    else:
        base_config = load_scada_config(DEFAULT_COMPANY_ID) if DEFAULT_COMPANY_ID else normalize_config({})
    base_data = json.loads(json.dumps(base_config)) if base_config else {}
    now = current_utc_iso()
    entry = normalize_company_entry({
        "empresaId": empresa_id,
        "name": payload.name.strip() if payload.name else empresa_id,
        "description": payload.description.strip() if payload.description else "",
        "active": bool(payload.active) if payload.active is not None else True,
        "createdAt": now,
        "updatedAt": now,
        "mqttBrokerKey": broker_key,
    })
    if not entry:
        raise HTTPException(status_code=400, detail="Datos de empresa invalidos")
    try:
        save_scada_config(base_data or {}, empresa_id, actor_email)
    except GithubSyncError as exc:
        logger.exception("No se pudo sincronizar configuracion nueva: %s", exc)
        raise HTTPException(status_code=502, detail=f"No se pudo sincronizar con GitHub: {exc}") from exc
    except Exception as exc:
        logger.exception("No se pudo crear configuracion base para %s: %s", empresa_id, exc)
        raise HTTPException(status_code=500, detail="No se pudo crear la configuracion inicial") from exc
    companies.append(entry)
    save_companies(companies)
    logger.info("Empresa creada %s por %s clone_from=%s", empresa_id, actor_email, clone_from)
    return {"company": entry}


@app.put("/tenants/{empresa_id}")
def update_tenant_endpoint(empresa_id: str, payload: TenantUpdate, authorization: Optional[str] = Header(None)):
    decoded = verify_bearer_token(authorization)
    ensure_master_admin(decoded)
    try:
        target_id = sanitize_company_id(empresa_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"empresaId invalido: {exc}") from exc
    companies = load_companies()
    for entry in companies:
        if entry.get("empresaId") == target_id:
            if payload.name is not None:
                entry["name"] = payload.name.strip() or target_id
            if payload.description is not None:
                entry["description"] = payload.description.strip()
            if payload.active is not None and target_id != DEFAULT_COMPANY_ID:
                entry["active"] = bool(payload.active)
            if payload.mqttBrokerKey is not None:
                if payload.mqttBrokerKey:
                    try:
                        new_broker = sanitize_broker_key(payload.mqttBrokerKey)
                    except ValueError as exc:
                        raise HTTPException(status_code=400, detail=f"mqttBrokerKey invalido: {exc}") from exc
                else:
                    new_broker = DEFAULT_BROKER_KEY
                if new_broker not in broker_manager.available_keys():
                    raise HTTPException(status_code=400, detail=f"mqttBrokerKey {new_broker} no esta configurado")
                entry["mqttBrokerKey"] = new_broker
            entry["updatedAt"] = current_utc_iso()
            save_companies(companies)
            updated = find_company(load_companies(), target_id) or entry
            return {"company": updated}
    raise HTTPException(status_code=404, detail="Empresa no encontrada")


@app.get("/users")
def list_users_endpoint(authorization: Optional[str] = Header(None), empresa_id: Optional[str] = Query(None)):
    decoded = verify_bearer_token(authorization)
    target = empresa_id or extract_company_id(decoded)
    company_id = ensure_company_admin(decoded, target)
    users = list_company_users(company_id)
    return {"empresaId": company_id, "users": users}


@app.post("/users", status_code=201)
def create_user_endpoint(payload: UserCreate, authorization: Optional[str] = Header(None)):
    decoded = verify_bearer_token(authorization)
    actor_email = decoded.get("email")
    target = payload.empresaId or extract_company_id(decoded)
    if not target:
        raise HTTPException(status_code=400, detail="empresaId requerido")
    company_id = ensure_company_admin(decoded, target)
    role = sanitize_user_role(payload.role)
    email = payload.email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email requerido")
    try:
        user_record = firebase_auth.create_user(email=email)
    except firebase_exceptions.FirebaseError as exc:
        if getattr(exc, "code", "") == "email-already-exists":
            raise HTTPException(status_code=409, detail="El correo ya esta registrado") from exc
        logger.exception("No se pudo crear usuario %s: %s", email, exc)
        raise HTTPException(status_code=502, detail="No se pudo crear el usuario") from exc
    claims = merge_custom_claims({}, company_id, role)
    try:
        firebase_auth.set_custom_user_claims(user_record.uid, claims)
    except firebase_exceptions.FirebaseError as exc:
        logger.exception("No se pudo asignar claims para %s: %s", email, exc)
        try:
            firebase_auth.delete_user(user_record.uid)
        except Exception:
            logger.exception("No se pudo revertir usuario creado %s", email)
        raise HTTPException(status_code=502, detail="No se pudo asignar claims al usuario") from exc
    try:
        apply_role_to_config(company_id, email, role, actor_email)
    except Exception as exc:
        logger.exception("No se pudo actualizar roles para %s: %s", email, exc)
        try:
            firebase_auth.delete_user(user_record.uid)
        except Exception:
            logger.exception("No se pudo revertir usuario tras fallo de configuracion %s", email)
        raise HTTPException(status_code=500, detail="No se pudo actualizar la configuracion de la empresa") from exc
    metadata = getattr(user_record, "user_metadata", None)
    created_at = firebase_timestamp_to_iso(getattr(metadata, "creation_timestamp", None)) if metadata else None
    last_login = firebase_timestamp_to_iso(getattr(metadata, "last_sign_in_timestamp", None)) if metadata else None
    action_settings = build_action_code_settings()
    reset_link = None
    try:
        reset_link = firebase_auth.generate_password_reset_link(email, action_settings)
    except firebase_exceptions.FirebaseError as exc:
        logger.warning("No se pudo generar link de recuperacion para %s: %s", email, exc)
    invite_sent = False
    if payload.sendInvite and reset_link:
        invite_sent = send_password_reset_email(email, None)
    logger.info("Usuario %s creado en empresa %s por %s role=%s", email, company_id, actor_email, role)
    return {
        "user": {
            "uid": user_record.uid,
            "email": email,
            "empresaId": company_id,
            "role": role,
            "emailVerified": bool(user_record.email_verified),
            "disabled": bool(user_record.disabled),
            "createdAt": created_at,
            "lastLoginAt": last_login,
        },
        "resetLink": reset_link,
        "inviteSent": invite_sent,
    }


@app.delete("/users/{uid}")
def delete_user_endpoint(uid: str, authorization: Optional[str] = Header(None), empresa_id: Optional[str] = Query(None)):
    decoded = verify_bearer_token(authorization)
    actor_email = decoded.get("email")
    try:
        user_record = firebase_auth.get_user(uid)
    except firebase_exceptions.FirebaseError as exc:
        if getattr(exc, "code", "") == "user-not-found":
            raise HTTPException(status_code=404, detail="Usuario no encontrado") from exc
        logger.exception("No se pudo obtener usuario %s: %s", uid, exc)
        raise HTTPException(status_code=502, detail="No se pudo consultar el usuario") from exc
    target_company = empresa_id or company_id_from_claims(user_record.custom_claims or {})
    if not target_company:
        raise HTTPException(status_code=400, detail="empresaId requerido")
    company_id = ensure_company_admin(decoded, target_company)
    if not is_master_admin(decoded):
        claims = user_record.custom_claims or {}
        if claims.get("isMasterAdmin") or claims.get("masterAdmin"):
            raise HTTPException(status_code=403, detail="No puedes eliminar un administrador maestro")
    try:
        firebase_auth.delete_user(uid)
    except firebase_exceptions.FirebaseError as exc:
        logger.exception("No se pudo eliminar usuario %s: %s", uid, exc)
        raise HTTPException(status_code=502, detail="No se pudo eliminar el usuario") from exc
    try:
        remove_user_from_config(company_id, user_record.email, actor_email)
    except Exception as exc:
        logger.warning("No se pudo limpiar roles para %s: %s", user_record.email, exc)
    logger.info("Usuario %s eliminado en empresa %s por %s", uid, company_id, actor_email)
    return {"ok": True, "empresaId": company_id}


@app.post("/users/{uid}/reset-link")
def reset_user_password(uid: str, payload: UserResetRequest, authorization: Optional[str] = Header(None), empresa_id: Optional[str] = Query(None)):
    decoded = verify_bearer_token(authorization)
    actor_email = decoded.get("email")
    try:
        user_record = firebase_auth.get_user(uid)
    except firebase_exceptions.FirebaseError as exc:
        if getattr(exc, "code", "") == "user-not-found":
            raise HTTPException(status_code=404, detail="Usuario no encontrado") from exc
        logger.exception("No se pudo obtener usuario %s: %s", uid, exc)
        raise HTTPException(status_code=502, detail="No se pudo consultar el usuario") from exc
    if not user_record.email:
        raise HTTPException(status_code=400, detail="El usuario no tiene email registrado")
    target_company = empresa_id or company_id_from_claims(user_record.custom_claims or {})
    if not target_company:
        raise HTTPException(status_code=400, detail="empresaId requerido")
    company_id = ensure_company_admin(decoded, target_company)
    action_settings = build_action_code_settings(payload.continueUrl)
    try:
        reset_link = firebase_auth.generate_password_reset_link(user_record.email, action_settings)
    except firebase_exceptions.FirebaseError as exc:
        logger.exception("No se pudo generar enlace de reinicio para %s: %s", user_record.email, exc)
        raise HTTPException(status_code=502, detail="No se pudo generar el enlace de restablecimiento") from exc
    email_sent = False
    if payload.sendEmail:
        email_sent = send_password_reset_email(user_record.email, payload.continueUrl)
    logger.info("Reset link generado para %s por %s en empresa %s", user_record.email, actor_email, company_id)
    return {"resetLink": reset_link, "emailSent": email_sent, "empresaId": company_id}


@app.post("/publish")
def publish(p: PublishIn, authorization: Optional[str] = Header(None)):
    decoded = verify_bearer_token(authorization)
    uid = decoded["uid"]
    company_id = extract_company_id(decoded)
    broker_key = broker_key_for_company(company_id)
    allowed = [x.rstrip("/") + "/" for x in allowed_prefixes_for_user(uid, company_id)]
    if not any(p.topic.startswith(pref) for pref in allowed):
        raise HTTPException(status_code=403, detail=f"Topic not allowed for user {uid} en empresa {company_id}")
    ensure_mqtt_connected(broker_key)
    payload = p.payload
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload, separators=(",", ":"))
    elif not isinstance(payload, str):
        payload = str(payload)
    resolved_key, res = broker_manager.publish(broker_key, p.topic, payload=payload, qos=p.qos, retain=p.retain)
    if res.rc != mqtt.MQTT_ERR_SUCCESS:
        raise HTTPException(status_code=500, detail=f"MQTT publish error rc={res.rc}")
    return {"ok": True, "broker": resolved_key}

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
    company_id = extract_company_id(decoded)
    broker_key = broker_key_for_company(company_id)
    prefixes = allowed_prefixes_for_user(uid, company_id)
    try:
        ensure_mqtt_connected(broker_key)
    except HTTPException as exc:
        await websocket.send_json({"type": "error", "error": exc.detail or "MQTT broker not connected"})
        await websocket.close(code=1013)
        return
    client = WSClient(websocket, uid, company_id, prefixes, broker_key)
    ConnectionManager.add(client)

    initial_snapshot = snapshot_for_prefixes(prefixes, broker_key)
    await websocket.send_json({
        "type": "hello",
        "uid": uid,
        "empresaId": company_id,
        "allowed_prefixes": prefixes,
        "broker": broker_key,
        "last_values": initial_snapshot
    })

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

                ensure_mqtt_connected(client.broker_key)
                pub_payload = payload
                if isinstance(pub_payload, (dict, list)):
                    pub_payload = json.dumps(pub_payload, separators=(",", ":"))
                elif not isinstance(pub_payload, str):
                    pub_payload = str(pub_payload)

                resolved_key, res = broker_manager.publish(client.broker_key, topic, payload=pub_payload, qos=qos, retain=retain)
                if res.rc != mqtt.MQTT_ERR_SUCCESS:
                    await websocket.send_json({"type": "error", "error": f"MQTT publish rc={res.rc}"})
                else:
                    await websocket.send_json({"type": "ack", "topic": topic, "broker": resolved_key})
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























