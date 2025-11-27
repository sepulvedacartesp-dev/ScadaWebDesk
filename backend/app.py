import os
import io
import json
import base64
import ssl
import threading
import asyncio
import logging
import re
import uuid
import copy
import requests
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import List, Optional, Dict, Any, Set, Tuple
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header, Query, Body, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from PIL import Image, UnidentifiedImageError

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from firebase_admin import exceptions as firebase_exceptions
from google.auth.exceptions import DefaultCredentialsError
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

import paho.mqtt.client as mqtt
import asyncpg

from quotes import db as quote_db
from quotes import service as quote_service
from quotes.enums import QuoteStatus

# Normaliza identificadores de planta para consultas/DB
def normalize_plant_id(value: Optional[str]) -> str:
    if not value:
        return DEFAULT_PLANTA_ID
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value)).strip().strip("_")
    return normalized.lower() or DEFAULT_PLANTA_ID
from quotes.exceptions import (
    CatalogError,
    ClientExistsError,
    InvalidStatusTransition,
    QuoteError,
    QuoteNotFoundError,
)
from quotes.schemas import (
    CatalogCategoryOut,
    CatalogItemUpsert,
    CatalogResponse,
    CatalogUpsertPayload,
    ClientCreatePayload,
    ClientListResponse,
    ClientSummary,
    Pagination,
    QuoteCreatePayload,
    QuoteDetail,
    QuoteListResponse,
    QuoteListFilters,
    QuoteStatusChange,
    QuoteUpdatePayload,
)

from alarms import service as alarm_service
from alarms.schemas import AlarmRuleCreate, AlarmRuleOut, AlarmRuleUpdate, AlarmEventOut
from reports import service as report_service
from reports import runner as report_runner
from reports.schemas import (
    ReportCreatePayload,
    ReportDefinitionOut,
    ReportRunOut,
    ReportRunRequest,
    ReportUpdatePayload,
)

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


def sanitize_plant_id(raw: Optional[str]) -> str:
    if raw is None:
        raise ValueError("Planta no definida")
    sanitized = re.sub(r'[^A-Za-z0-9_-]+', '_', str(raw).strip())
    sanitized = sanitized.strip('_').lower()
    if not sanitized:
        raise ValueError("Planta no definida")
    return sanitized


def sanitize_serial_code(raw: Optional[str]) -> str:
    if raw is None:
        raise ValueError("Codigo de serie no definido")
    sanitized = re.sub(r'[^A-Za-z0-9_-]+', '_', str(raw).strip())
    sanitized = sanitized.strip('_')
    if not sanitized:
        raise ValueError("Codigo de serie no definido")
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

LOGO_STORAGE_DIR = (BASE_DIR / '..' / 'logoclientes').resolve()
LOGO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_LOGO_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/pjpeg"}
MAX_LOGO_SIZE_BYTES = int(os.getenv("MAX_LOGO_SIZE_BYTES", "2097152"))

COMPANIES_PATH = CONFIG_STORAGE_DIR / 'companies.json'
COMPANIES_LOCK = threading.Lock()

TREND_HTML_PATH = (BASE_DIR / '..' / 'trend.html').resolve()

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

def logo_path_for_company(company_id: str) -> Path:
    sanitized = sanitize_company_id(company_id)
    return LOGO_STORAGE_DIR / f"{sanitized}.jpg"

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


def parse_iso8601(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Fecha inválida: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def isoformat_utc(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    target = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return target.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_trend_pool() -> asyncpg.pool.Pool:
    if trend_db_pool is None:
        raise HTTPException(status_code=503, detail="Servicio de tendencias no disponible")
    return trend_db_pool


def require_quote_pool() -> asyncpg.pool.Pool:
    try:
        return quote_db.get_pool()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Servicio de cotizaciones no disponible") from exc


# ---- Session helpers (WebSocket) ----
async def ensure_session_table(pool: asyncpg.pool.Pool) -> None:
    global session_table_ready
    if session_table_ready:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {SESSION_TABLE_NAME} (
                    session_id UUID PRIMARY KEY,
                    empresa_id TEXT NOT NULL,
                    uid TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    last_seen TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE INDEX IF NOT EXISTS {SESSION_TABLE_NAME}_empresa_idx ON {SESSION_TABLE_NAME}(empresa_id);
                """
            )
        session_table_ready = True
    except Exception as exc:
        logger.warning("No se pudo asegurar la tabla de sesiones %s: %s", SESSION_TABLE_NAME, exc)


async def cleanup_expired_sessions(pool: asyncpg.pool.Pool) -> int:
    if SESSION_TTL_SECONDS <= 0:
        return 0
    await ensure_session_table(pool)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=SESSION_TTL_SECONDS)
    try:
        async with pool.acquire() as conn:
            result = await conn.execute(f"DELETE FROM {SESSION_TABLE_NAME} WHERE last_seen < $1", cutoff)
    except Exception as exc:
        logger.warning("No se pudo limpiar sesiones vencidas: %s", exc)
        return 0
    try:
        return int(result.split(" ")[-1])
    except Exception:
        return 0


async def claim_session_slot(pool: asyncpg.pool.Pool, session_id: str, empresa_id: str, uid: str) -> Tuple[bool, Optional[str]]:
    await ensure_session_table(pool)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=SESSION_TTL_SECONDS) if SESSION_TTL_SECONDS > 0 else None
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                if cutoff:
                    await conn.execute(f"DELETE FROM {SESSION_TABLE_NAME} WHERE last_seen < $1", cutoff)
                if MAX_ACTIVE_SESSIONS_PER_COMPANY > 0:
                    count = await conn.fetchval(
                        f"SELECT COUNT(*) FROM {SESSION_TABLE_NAME} WHERE empresa_id=$1",
                        empresa_id,
                    )
                    if count >= MAX_ACTIVE_SESSIONS_PER_COMPANY:
                        return False, "Limite de usuarios activos superado"
                await conn.execute(
                    f"""
                    INSERT INTO {SESSION_TABLE_NAME} (session_id, empresa_id, uid, created_at, last_seen)
                    VALUES ($1, $2, $3, now(), now())
                    """,
                    session_id,
                    empresa_id,
                    uid,
                )
    except Exception as exc:
        logger.warning("No se pudo reclamar cupo de sesion para %s/%s: %s", empresa_id, uid, exc)
        return False, "No se pudo registrar la sesion"
    return True, None


async def touch_session(pool: asyncpg.pool.Pool, session_id: str) -> None:
    if SESSION_TTL_SECONDS <= 0:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {SESSION_TABLE_NAME} SET last_seen = now() WHERE session_id = $1",
                session_id,
            )
    except Exception as exc:
        logger.debug("No se pudo refrescar la sesion %s: %s", session_id, exc)


async def drop_session(pool: asyncpg.pool.Pool, session_id: str) -> None:
    try:
        async with pool.acquire() as conn:
            await conn.execute(f"DELETE FROM {SESSION_TABLE_NAME} WHERE session_id = $1", session_id)
    except Exception as exc:
        logger.debug("No se pudo eliminar la sesion %s: %s", session_id, exc)


def ensure_quote_admin_access(decoded: Dict[str, Any]) -> str:
    email = decoded.get("email")
    if not email:
        raise HTTPException(status_code=403, detail="El usuario no tiene correo asignado")
    if is_master_admin(decoded):
        return email
    if email.lower() not in ADMIN_EMAILS_LOWER:
        raise HTTPException(status_code=403, detail="No tienes permisos para administrar cotizaciones")
    return email


def resolve_quote_company(decoded: Dict[str, Any], requested_empresa: Optional[str]) -> str:
    if requested_empresa:
        if not is_master_admin(decoded):
            raise HTTPException(status_code=403, detail="Solo administradores maestros pueden consultar otras empresas")
        try:
            return sanitize_company_id(requested_empresa)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"empresaId invalido: {exc}") from exc
    return extract_company_id(decoded)


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
trend_db_pool: Optional[asyncpg.pool.Pool] = None
session_cleanup_task: Optional[asyncio.Task] = None
session_table_ready = False
# ---- Config ----
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "").strip()
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*").strip()


def parse_allowed_origins(raw: str) -> List[str]:
    if not raw:
        return ["*"]
    parts = [item.strip() for item in raw.split(",") if item.strip()]
    return parts or ["*"]


ALLOWED_CORS_ORIGINS = parse_allowed_origins(FRONTEND_ORIGIN)
ALLOW_CREDENTIALS = "*" not in ALLOWED_CORS_ORIGINS
if not ALLOW_CREDENTIALS:
    logger.warning("CORS credentials disabled because '*' is present in FRONTEND_ORIGIN")

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

# ---- Session tracking (WebSocket) ----
SESSION_TABLE_NAME_RAW = os.getenv("SESSION_TABLE_NAME", "active_sessions").strip() or "active_sessions"
SESSION_TABLE_NAME = re.sub(r"[^A-Za-z0-9_]+", "", SESSION_TABLE_NAME_RAW) or "active_sessions"
SESSION_TTL_SECONDS = coerce_int(os.getenv("SESSION_TTL_SECONDS"), 300)  # 0 desactiva expiracion por TTL
SESSION_CLEANUP_INTERVAL_SECONDS = coerce_int(os.getenv("SESSION_CLEANUP_INTERVAL_SECONDS"), 120)  # 0 desactiva tarea programada
MAX_ACTIVE_SESSIONS_PER_COMPANY = coerce_int(os.getenv("MAX_ACTIVE_SESSIONS_PER_COMPANY"), 0)  # 0 = ilimitado

TOPIC_BASE = os.getenv("TOPIC_BASE", "scada/customers").strip()
PUBLIC_ALLOWED_PREFIXES = [p.strip() for p in os.getenv("PUBLIC_ALLOWED_PREFIXES", "").split(",") if p.strip()]

FIREBASE_SERVICE_ACCOUNT = os.getenv("FIREBASE_SERVICE_ACCOUNT", "").strip()
FIREBASE_WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY", "").strip()
FIREBASE_EMAIL_CONTINUE_URL = os.getenv("FIREBASE_EMAIL_CONTINUE_URL", "").strip()
FIREBASE_AUTH_TIMEOUT = float(os.getenv("FIREBASE_AUTH_TIMEOUT", "10"))
IDENTITY_TOOLKIT_URL = "https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
TRENDS_FETCH_LIMIT = coerce_int(os.getenv("TRENDS_FETCH_LIMIT", "5000"), 5000)
DEFAULT_TRENDS_RANGE_HOURS = coerce_int(os.getenv("DEFAULT_TRENDS_RANGE_HOURS", "24"), 24)
DIAS_RETENCION_HISTORICO = coerce_int(os.getenv("DIAS_RETENCION_HISTORICO", "30"), 30)
QUOTE_DB_MIN_POOL_SIZE = max(1, coerce_int(os.getenv("QUOTE_DB_MIN_POOL_SIZE", "1"), 1))
QUOTE_DB_MAX_POOL_SIZE = max(QUOTE_DB_MIN_POOL_SIZE, coerce_int(os.getenv("QUOTE_DB_MAX_POOL_SIZE", "5"), 5))
QUOTE_DB_TIMEOUT = max(1, coerce_int(os.getenv("QUOTE_DB_TIMEOUT", "10"), 10))

TRENDS_RESOLUTION_SECONDS: Dict[str, Optional[int]] = {
    "raw": None,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "1d": 24 * 60 * 60,
}

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


@app.on_event("startup")
async def init_trend_database_pool():
    global trend_db_pool
    if not DATABASE_URL:
        logger.warning("DATABASE_URL no definido. Endpoints de tendencias permanecerán deshabilitados.")
        trend_db_pool = None
        return
    try:
        trend_db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5, timeout=10)
        logger.info("Pool de base de datos para tendencias inicializado.")
    except Exception as exc:
        trend_db_pool = None
        logger.error("No se pudo inicializar el pool de tendencias: %s", exc)


@app.on_event("startup")
async def init_quote_database_pool():
    if not DATABASE_URL:
        logger.warning("DATABASE_URL no definido. Endpoints de cotizador permanecer�n deshabilitados.")
        await quote_db.close_pool()
        return
    try:
        pool = await quote_db.init_pool(
            DATABASE_URL,
            min_size=QUOTE_DB_MIN_POOL_SIZE,
            max_size=QUOTE_DB_MAX_POOL_SIZE,
            timeout=QUOTE_DB_TIMEOUT,
        )
        if pool is not None:
            logger.info("Pool de base de datos para cotizador inicializado.")
    except Exception as exc:
        await quote_db.close_pool()
        logger.error("No se pudo inicializar el pool de cotizador: %s", exc)

@app.on_event("startup")
async def start_session_cleanup_task():
    global session_cleanup_task
    if SESSION_CLEANUP_INTERVAL_SECONDS <= 0 or SESSION_TTL_SECONDS <= 0:
        return

    async def _run_cleanup():
        while True:
            try:
                pool = trend_db_pool
                if pool is not None:
                    await ensure_session_table(pool)
                    deleted = await cleanup_expired_sessions(pool)
                    if deleted:
                        logger.info("Sesiones expiradas eliminadas: %d", deleted)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error en tarea de limpieza de sesiones: %s", exc)
            await asyncio.sleep(SESSION_CLEANUP_INTERVAL_SECONDS)

    session_cleanup_task = asyncio.create_task(_run_cleanup())


@app.on_event("shutdown")
async def shutdown_trend_database_pool():
    global trend_db_pool
    pool = trend_db_pool
    if pool is None:
        return
    try:
        await pool.close()
        logger.info("Pool de base de datos para tendencias cerrado.")
    finally:
        trend_db_pool = None


@app.on_event("shutdown")
async def shutdown_quote_database_pool():
    await quote_db.close_pool()
    logger.info("Pool de base de datos para cotizador cerrado.")

@app.on_event("shutdown")
async def stop_session_cleanup_task():
    global session_cleanup_task
    task = session_cleanup_task
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.debug("Error al detener tarea de limpieza de sesiones: %s", exc)
    finally:
        session_cleanup_task = None

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_CORS_ORIGINS,
    allow_credentials=ALLOW_CREDENTIALS,
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


def default_plants_for_company(company_id: str) -> List[Dict[str, Any]]:
    serial = sanitize_serial_code(company_id)
    return [{
        "id": "general",
        "name": "Planta General",
        "serialCode": serial,
        "description": "",
        "active": True,
        "isDefault": True,
    }]


def normalize_plants(raw_plants: Any, company_id: str) -> List[Dict[str, Any]]:
    if not isinstance(raw_plants, list):
        raw_plants = []
    normalized: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    seen_serials: Set[str] = set()
    for idx, entry in enumerate(raw_plants):
        if not isinstance(entry, dict):
            continue
        name = coerce_str(entry.get("name"), "")
        raw_id = entry.get("id") or entry.get("plantId") or name or f"plant_{idx + 1}"
        try:
            plant_id = sanitize_plant_id(raw_id)
        except ValueError:
            plant_id = sanitize_plant_id(f"plant_{idx + 1}")
        raw_serial = entry.get("serialCode") or entry.get("serial") or entry.get("serie") or plant_id
        try:
            serial_code = sanitize_serial_code(raw_serial)
        except ValueError:
            serial_code = sanitize_serial_code(plant_id)
        if plant_id in seen_ids:
            raise ValueError(f"Plant ID duplicado: {plant_id}")
        if serial_code in seen_serials:
            raise ValueError(f"serialCode duplicado: {serial_code}")
        seen_ids.add(plant_id)
        seen_serials.add(serial_code)
        normalized_entry = dict(entry)
        normalized_entry["id"] = plant_id
        normalized_entry["name"] = name or plant_id
        normalized_entry["serialCode"] = serial_code
        normalized_entry["description"] = coerce_str(entry.get("description"), "")
        normalized_entry["active"] = coerce_bool(entry.get("active"), True)
        normalized.append(normalized_entry)
    if not normalized:
        return default_plants_for_company(company_id)
    return normalized


def normalize_plant_assignments(raw_assignments: Any, plants: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    if not isinstance(raw_assignments, dict):
        raw_assignments = {}
    valid_ids = {plant["id"] for plant in plants}
    normalized: Dict[str, List[str]] = {}
    for email, raw_ids in raw_assignments.items():
        if not email:
            continue
        email_key = str(email).strip().lower()
        if not email_key:
            continue
        candidates: List[str]
        if isinstance(raw_ids, str):
            candidates = [raw_ids]
        elif isinstance(raw_ids, list):
            candidates = [str(item).strip() for item in raw_ids]
        else:
            continue
        filtered: List[str] = []
        for candidate in candidates:
            if not candidate:
                continue
            candidate_id = candidate.lower()
            if candidate_id in valid_ids:
                filtered.append(candidate_id)
        if filtered:
            normalized[email_key] = sorted(dict.fromkeys(filtered))
    return normalized


def normalize_container_plants(raw_containers: Any, plants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    containers = raw_containers if isinstance(raw_containers, list) else []
    def as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "on", "si", "general"}
        return bool(value)
    if not plants:
        normalized: List[Dict[str, Any]] = []
        for container in containers:
            if not isinstance(container, dict):
                continue
            normalized_container = dict(container)
            normalized_container["isGeneral"] = as_bool(container.get("isGeneral") or container.get("general"))
            normalized.append(normalized_container)
        return normalized
    valid_ids = [plant["id"] for plant in plants]
    default_id = valid_ids[0]
    normalized: List[Dict[str, Any]] = []
    for container in containers:
        if not isinstance(container, dict):
            continue
        normalized_container = dict(container)
        raw_id = container.get("plantId") or container.get("plant") or default_id
        plant_id = str(raw_id).strip().lower() if isinstance(raw_id, str) else str(raw_id or default_id).strip().lower()
        if plant_id not in valid_ids:
            plant_id = default_id
        normalized_container["plantId"] = plant_id
        normalized_container["isGeneral"] = as_bool(container.get("isGeneral") or container.get("general"))
        normalized.append(normalized_container)
    return normalized


def plant_lookup(plants: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {plant["id"]: plant for plant in plants}


def resolve_user_plant_ids(
    cfg: Dict[str, Any],
    email: Optional[str],
    role: Optional[str],
    is_master: bool,
) -> List[str]:
    plants = cfg.get("plants") or []
    if not plants:
        return []
    lookup = plant_lookup(plants)
    if is_master or role == "admin":
        return list(lookup.keys())
    assignments = cfg.get("plantAssignments") or {}
    if not isinstance(assignments, dict) or not assignments:
        return list(lookup.keys())
    if not email:
        return []
    email_key = email.lower()
    if not email_key:
        return []
    assigned = assignments.get(email_key)
    if assigned:
        return [plant_id for plant_id in assigned if plant_id in lookup]
    return []


def normalize_requested_plant_ids(
    requested: Optional[List[str]],
    plants: List[Dict[str, Any]],
) -> Optional[List[str]]:
    if requested is None:
        return None
    if not isinstance(requested, list):
        requested = [requested]
    lookup = plant_lookup(plants)
    normalized: List[str] = []
    for item in requested:
        if item is None:
            continue
        candidate = str(item).strip().lower()
        if not candidate or candidate not in lookup:
            continue
        normalized.append(candidate)
    return sorted(dict.fromkeys(normalized))


def normalize_config(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {
            "mainTitle": "SCADA Web",
            "roles": {"admins": [], "operators": [], "viewers": []},
            "containers": [],
            "plants": default_plants_for_company(DEFAULT_COMPANY_ID),
            "plantAssignments": {},
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
    plants = normalize_plants(result.get("plants"), result["empresaId"])
    result["plants"] = plants
    result["plantAssignments"] = normalize_plant_assignments(result.get("plantAssignments"), plants)
    result["containers"] = normalize_container_plants(result.get("containers"), plants)
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

def apply_role_to_config(
    company_id: str,
    email: str,
    role: str,
    actor_email: Optional[str],
    plant_ids: Optional[List[str]] = None,
) -> None:
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
    normalized_plants = normalized.get("plants", [])
    assignment_map = normalized.get("plantAssignments", {})
    if not isinstance(assignment_map, dict):
        assignment_map = {}
    normalized_selection = normalize_requested_plant_ids(plant_ids, normalized_plants)
    if normalized_selection is not None:
        if normalized_selection:
            assignment_map[lower_email] = normalized_selection
        elif lower_email in assignment_map:
            assignment_map.pop(lower_email, None)
    normalized["plantAssignments"] = assignment_map
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
    assignments = normalized.get("plantAssignments") or {}
    if isinstance(assignments, dict):
        assignments.pop(lower_email, None)
        normalized["plantAssignments"] = assignments
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



def users_from_roles_snapshot(
    company_id: str,
    roles: Dict[str, List[str]],
    cfg: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    snapshot: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    cfg = cfg or {}
    plants = cfg.get("plants") or []
    lookup = plant_lookup(plants) if plants else {}
    assignments = cfg.get("plantAssignments") if isinstance(cfg.get("plantAssignments"), dict) else {}
    for role_name, key in ROLE_KEY_MAP.items():
        for email in roles.get(key, []):
            stripped = str(email).strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if lower in seen:
                continue
            seen.add(lower)
            if lookup:
                if assignments:
                    assigned = assignments.get(lower, [])
                    plant_ids = [pid for pid in assigned if pid in lookup]
                else:
                    plant_ids = list(lookup.keys())
            else:
                plant_ids = []
            plant_serials = [lookup[pid]["serialCode"] for pid in plant_ids if pid in lookup]
            plant_names = [lookup[pid]["name"] for pid in plant_ids if pid in lookup]
            snapshot.append({
                "uid": None,
                "email": stripped,
                "displayName": "",
                "empresaId": company_id,
                "role": role_name,
                "emailVerified": False,
                "disabled": False,
                "createdAt": None,
                "lastLoginAt": None,
                "isMasterAdmin": False,
                "plantIds": plant_ids,
                "plantSerials": plant_serials,
                "plantNames": plant_names,
                "source": "roles",
            })
    snapshot.sort(key=lambda item: item["email"].lower())
    return snapshot






def list_company_users(company_id: str) -> List[Dict[str, Any]]:
    cfg = load_scada_config(company_id)
    normalized = normalize_config(cfg)
    roles = normalize_role_lists(normalized)
    try:
        page = firebase_auth.list_users(app=firebase_app)
    except firebase_exceptions.FirebaseError as exc:
        logger.warning("No se pudo listar usuarios desde Firebase: %s", exc)
        return users_from_roles_snapshot(company_id, roles, normalized)
    except Exception as exc:
        logger.exception("Fallo inesperado al listar usuarios para %s: %s", company_id, exc)
        return users_from_roles_snapshot(company_id, roles, normalized)
    role_lookup: Dict[str, str] = {}
    lookup_plants = plant_lookup(normalized.get("plants", []) or [])
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
            plant_ids = resolve_user_plant_ids(normalized, email, role, False)
            plant_serials = [lookup_plants[pid]["serialCode"] for pid in plant_ids if pid in lookup_plants]
            plant_names = [lookup_plants[pid]["name"] for pid in plant_ids if pid in lookup_plants]
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
                "plantIds": plant_ids,
                "plantSerials": plant_serials,
                "plantNames": plant_names,
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
    general_per_plant: Dict[str, int] = {}
    for c_idx, container in enumerate(containers):
        if not isinstance(container, dict):
            raise HTTPException(status_code=400, detail=f"El contenedor {c_idx} debe ser un objeto")
        raw_plant = container.get("plantId") or container.get("plant") or ""
        plant_id = str(raw_plant).strip().lower() if raw_plant is not None else ""
        raw_general = container.get("isGeneral") or container.get("general")
        if isinstance(raw_general, str):
            is_general = raw_general.strip().lower() in {"true", "1", "yes", "on", "si", "general"}
        else:
            is_general = bool(raw_general)
        if is_general:
            if plant_id in general_per_plant:
                raise HTTPException(
                    status_code=400,
                    detail=f"La planta {plant_id or '(sin id)'} solo admite un contenedor general.",
                )
            general_per_plant[plant_id] = c_idx
        objects = container.get("objects", [])
        if not isinstance(objects, list):
            raise HTTPException(status_code=400, detail=f"El campo objects del contenedor {c_idx} debe ser una lista")
        for o_idx, obj in enumerate(objects):
            if not isinstance(obj, dict):
                raise HTTPException(status_code=400, detail=f"El objeto {o_idx} del contenedor {c_idx} debe ser un objeto")
            topic = obj.get("topic")
            if topic is not None and not isinstance(topic, str):
                raise HTTPException(status_code=400, detail=f"El topic del objeto {o_idx} del contenedor {c_idx} debe ser texto")
    try:
        return normalize_config(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


def resolve_company_access(decoded: Dict[str, Any], requested_empresa: Optional[str]) -> str:
    if requested_empresa:
        try:
            requested = sanitize_company_id(requested_empresa)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"empresaId invalido: {exc}") from exc
        if is_master_admin(decoded):
            return requested
        current = extract_company_id(decoded)
        if requested == current:
            return requested
        raise HTTPException(status_code=403, detail="Usuario no autorizado para la empresa solicitada")
    return extract_company_id(decoded)
def allowed_prefixes_for_user(
    uid: str,
    company_id: Optional[str],
    decoded: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> List[str]:
    base = TOPIC_BASE.rstrip("/")
    if not company_id:
        combined = [f"{base}/{uid}"]
        combined.extend(PUBLIC_ALLOWED_PREFIXES)
        return combined
    config = cfg or load_scada_config(company_id)
    email = decoded.get("email") if decoded else None
    is_master = is_master_admin(decoded) if decoded else False
    role = "admin" if is_master else role_for_email(config, email)
    allowed_ids = resolve_user_plant_ids(config, email, role, is_master)
    scoped_prefixes: List[str] = []
    if is_master or role == "admin":
        scoped_prefixes.append(f"{base}/{company_id}")
    else:
        lookup = plant_lookup(config.get("plants", []) or [])
        for plant_id in allowed_ids:
            plant = lookup.get(plant_id)
            if not plant:
                continue
            serial = plant.get("serialCode")
            if not serial:
                continue
            scoped_prefixes.append(f"{base}/{company_id}/{serial}")
    if not scoped_prefixes and not (is_master or role == "admin"):
        return []
    combined = list(scoped_prefixes)
    combined.extend(PUBLIC_ALLOWED_PREFIXES)
    return combined

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
    lower_email = email.lower() if isinstance(email, str) else None
    can_access_cotizador = bool(lower_email and lower_email in ADMIN_EMAILS_LOWER)
    allowed_plant_ids = resolve_user_plant_ids(cfg, email, role, is_master)
    allowed_set = set(allowed_plant_ids)
    if is_master or role == "admin":
        visible_cfg = cfg
    else:
        visible_cfg = copy.deepcopy(cfg)
        visible_cfg["containers"] = [
            container for container in visible_cfg.get("containers", []) if container.get("plantId") in allowed_set
        ]
        visible_cfg["plants"] = [plant for plant in visible_cfg.get("plants", []) if plant.get("id") in allowed_set]
        visible_cfg["plantAssignments"] = {}
    accessible_plants = [plant for plant in cfg.get("plants", []) if plant.get("id") in allowed_set] if allowed_set else []
    return {
        "config": visible_cfg,
        "role": role,
        "empresaId": company_id,
        "isMaster": is_master,
        "canAccessCotizador": can_access_cotizador,
        "accessiblePlants": allowed_plant_ids,
        "plants": accessible_plants,
    }


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


# ---- Alarm management ----


def ensure_alarm_admin(decoded_token: Dict[str, Any], empresa_id: str) -> Dict[str, Any]:
    email = decoded_token.get("email")
    if is_master_admin(decoded_token):
        return load_scada_config(empresa_id)
    cfg = load_scada_config(empresa_id)
    ensure_admin(email, empresa_id, cfg)
    return cfg


def ensure_report_admin(decoded_token: Dict[str, Any], empresa_id: str) -> Dict[str, Any]:
    return ensure_alarm_admin(decoded_token, empresa_id)


def ensure_planta_exists(cfg: Dict[str, Any], planta_id: str) -> str:
    lookup = plant_lookup(cfg.get("plants", []) or [])
    normalized = normalize_plant_id(planta_id)
    if normalized not in lookup:
        raise HTTPException(status_code=400, detail="Planta no encontrada en la configuracion")
    return normalized


@app.get("/api/alarms/rules", response_model=List[AlarmRuleOut])
async def list_alarm_rules_endpoint(
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
):
    decoded = verify_bearer_token(authorization)
    company_id = resolve_company_access(decoded, empresa_id)
    ensure_alarm_admin(decoded, company_id)
    pool = require_trend_pool()
    rules = await alarm_service.list_rules(pool, company_id)
    return rules


@app.post("/api/alarms/rules", response_model=AlarmRuleOut)
async def create_alarm_rule_endpoint(
    payload: AlarmRuleCreate,
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
):
    decoded = verify_bearer_token(authorization)
    company_id = resolve_company_access(decoded, empresa_id)
    ensure_alarm_admin(decoded, company_id)
    pool = require_trend_pool()
    try:
        rule = await alarm_service.create_rule(pool, company_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except asyncpg.PostgresError as exc:
        logger.exception("No se pudo crear la regla de alarma: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudo crear la regla de alarma") from exc
    return rule


@app.put("/api/alarms/rules/{rule_id}", response_model=AlarmRuleOut)
async def update_alarm_rule_endpoint(
    rule_id: int,
    payload: AlarmRuleUpdate,
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
):
    decoded = verify_bearer_token(authorization)
    company_id = resolve_company_access(decoded, empresa_id)
    ensure_alarm_admin(decoded, company_id)
    pool = require_trend_pool()
    try:
        rule = await alarm_service.update_rule(pool, company_id, rule_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except asyncpg.PostgresError as exc:
        logger.exception("No se pudo actualizar la regla de alarma %s: %s", rule_id, exc)
        raise HTTPException(status_code=500, detail="No se pudo actualizar la regla de alarma") from exc
    if rule is None:
        raise HTTPException(status_code=404, detail="Regla no encontrada")
    return rule


@app.delete("/api/alarms/rules/{rule_id}")
async def delete_alarm_rule_endpoint(
    rule_id: int,
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
):
    decoded = verify_bearer_token(authorization)
    company_id = resolve_company_access(decoded, empresa_id)
    ensure_alarm_admin(decoded, company_id)
    pool = require_trend_pool()
    try:
        deleted = await alarm_service.delete_rule(pool, company_id, rule_id)
    except asyncpg.PostgresError as exc:
        logger.exception("No se pudo eliminar la regla de alarma %s: %s", rule_id, exc)
        raise HTTPException(status_code=500, detail="No se pudo eliminar la regla de alarma") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Regla no encontrada")
    return {"ok": True}


@app.get("/api/alarms/events", response_model=List[AlarmEventOut])
async def list_alarm_events_endpoint(
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    tag: Optional[str] = Query(None),
):
    decoded = verify_bearer_token(authorization)
    company_id = resolve_company_access(decoded, empresa_id)
    ensure_alarm_admin(decoded, company_id)
    pool = require_trend_pool()
    events = await alarm_service.list_events(pool, company_id, limit=limit, tag=tag)
    return events


# ---- Report management ----


@app.get("/api/reports", response_model=List[ReportDefinitionOut])
async def list_reports_endpoint(
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
    planta_id: Optional[str] = Query(None, alias="plantaId"),
):
    decoded = verify_bearer_token(authorization)
    company_id = resolve_company_access(decoded, empresa_id)
    cfg = ensure_report_admin(decoded, company_id)
    filter_plants = None
    if planta_id:
        normalized = ensure_planta_exists(cfg, planta_id)
        filter_plants = [normalized]
    pool = require_trend_pool()
    try:
        return await report_service.list_definitions(pool, company_id, filter_plants)
    except Exception as exc:
        logger.exception("No se pudieron listar los reportes: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudieron listar los reportes") from exc


@app.post("/api/reports", response_model=ReportDefinitionOut, status_code=201)
async def create_report_endpoint(
    payload: ReportCreatePayload,
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
):
    decoded = verify_bearer_token(authorization)
    company_id = resolve_company_access(decoded, empresa_id)
    cfg = ensure_report_admin(decoded, company_id)
    normalized_planta = ensure_planta_exists(cfg, payload.planta_id)
    payload = payload.model_copy(update={"planta_id": normalized_planta})
    pool = require_trend_pool()
    try:
        return await report_service.create_definition(pool, company_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=400, detail="Solo se permiten 2 reportes por planta") from exc
    except asyncpg.PostgresError as exc:
        logger.exception("No se pudo crear el reporte: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudo crear el reporte") from exc


@app.put("/api/reports/{report_id}", response_model=ReportDefinitionOut)
async def update_report_endpoint(
    report_id: int,
    payload: ReportUpdatePayload,
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
):
    decoded = verify_bearer_token(authorization)
    company_id = resolve_company_access(decoded, empresa_id)
    cfg = ensure_report_admin(decoded, company_id)
    if payload.planta_id:
        normalized_planta = ensure_planta_exists(cfg, payload.planta_id)
        payload = payload.model_copy(update={"planta_id": normalized_planta})
    pool = require_trend_pool()
    try:
        updated = await report_service.update_definition(pool, company_id, report_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except asyncpg.PostgresError as exc:
        logger.exception("No se pudo actualizar el reporte %s: %s", report_id, exc)
        raise HTTPException(status_code=500, detail="No se pudo actualizar el reporte") from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return updated


@app.delete("/api/reports/{report_id}")
async def delete_report_endpoint(
    report_id: int,
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
):
    decoded = verify_bearer_token(authorization)
    company_id = resolve_company_access(decoded, empresa_id)
    ensure_report_admin(decoded, company_id)
    pool = require_trend_pool()
    try:
        deleted = await report_service.delete_definition(pool, company_id, report_id)
    except asyncpg.PostgresError as exc:
        logger.exception("No se pudo eliminar el reporte %s: %s", report_id, exc)
        raise HTTPException(status_code=500, detail="No se pudo eliminar el reporte") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return {"ok": True}


@app.get("/api/reports/{report_id}/runs", response_model=List[ReportRunOut])
async def list_report_runs_endpoint(
    report_id: int,
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200),
):
    decoded = verify_bearer_token(authorization)
    company_id = resolve_company_access(decoded, empresa_id)
    ensure_report_admin(decoded, company_id)
    pool = require_trend_pool()
    definition = await report_service.get_definition(pool, company_id, report_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    try:
        return await report_service.list_runs(pool, company_id, report_id, limit=limit)
    except asyncpg.PostgresError as exc:
        logger.exception("No se pudieron listar las ejecuciones del reporte %s: %s", report_id, exc)
        raise HTTPException(status_code=500, detail="No se pudieron listar las ejecuciones") from exc


@app.post("/api/reports/{report_id}/runs", response_model=ReportRunOut, status_code=201)
async def trigger_report_run_endpoint(
    report_id: int,
    request: Optional[ReportRunRequest] = Body(None),
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
):
    decoded = verify_bearer_token(authorization)
    company_id = resolve_company_access(decoded, empresa_id)
    ensure_report_admin(decoded, company_id)
    pool = require_trend_pool()
    definition = await report_service.get_definition(pool, company_id, report_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    try:
        run = await report_service.create_run(pool, company_id, report_id, definition, request, decoded.get("email"))
        report_runner.spawn_background(pool, run.id)
        return run
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except asyncpg.PostgresError as exc:
        logger.exception("No se pudo agendar la ejecucion del reporte %s: %s", report_id, exc)
        raise HTTPException(status_code=500, detail="No se pudo agendar la ejecucion") from exc


@app.post("/logos")
async def upload_logo_endpoint(
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Form(None),
    logo: UploadFile = File(...),
):
    decoded = verify_bearer_token(authorization)
    email = decoded.get("email")
    is_master = is_master_admin(decoded)
    if empresa_id:
        if not is_master:
            raise HTTPException(status_code=403, detail="Solo administradores maestros pueden actualizar logos de otras empresas")
        try:
            company_id = sanitize_company_id(empresa_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"empresaId invalido: {exc}") from exc
    else:
        company_id = extract_company_id(decoded)
    if not is_master:
        ensure_admin(email, company_id)
    contents = await logo.read()
    if not contents:
        raise HTTPException(status_code=400, detail="El archivo esta vacio")
    if len(contents) > MAX_LOGO_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"El logo supera el limite de {MAX_LOGO_SIZE_BYTES // 1024} KB")
    content_type = (logo.content_type or "").lower()
    if content_type not in ALLOWED_LOGO_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Solo se permiten imagenes JPEG (.jpg)")
    try:
        with Image.open(io.BytesIO(contents)) as img:
            img.verify()
            format_name = (img.format or "").upper()
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="El archivo debe ser un JPEG valido")
    except Exception as exc:
        logger.warning("Error validando logo para %s: %s", company_id, exc)
        raise HTTPException(status_code=400, detail="No se pudo validar el logo cargado") from exc
    if format_name not in {"JPEG", "JPG"}:
        raise HTTPException(status_code=400, detail="El archivo debe ser un JPEG valido")
    path = logo_path_for_company(company_id)
    try:
        with path.open("wb") as fh:
            fh.write(contents)
    except Exception as exc:
        logger.exception("No se pudo guardar logo para %s: %s", company_id, exc)
        raise HTTPException(status_code=500, detail="No se pudo guardar el logo") from exc
    logger.info("Logo actualizado por %s para empresa %s (%d bytes)", email, company_id, len(contents))
    return {"ok": True, "empresaId": company_id, "updatedAt": current_utc_iso()}


@app.get("/logos/{empresa_id}.jpg")
def get_logo_endpoint(empresa_id: str):
    try:
        company_id = sanitize_company_id(empresa_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"empresaId invalido: {exc}") from exc
    path = logo_path_for_company(company_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Logo no encontrado")
    headers = {"Cache-Control": "public, max-age=3600"}
    return FileResponse(path, media_type="image/jpeg", filename=f"{company_id}.jpg", headers=headers)


# ---- Cotizador API ----

@app.post("/api/quotes", response_model=QuoteDetail)
async def create_quote_endpoint(
    payload: QuoteCreatePayload,
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
):
    decoded = verify_bearer_token(authorization)
    email = ensure_quote_admin_access(decoded)
    company_id = resolve_quote_company(decoded, empresa_id)
    require_quote_pool()
    try:
        return await quote_service.create_quote(
            payload,
            empresa_id=company_id,
            actor_email=email,
            actor_uid=decoded.get("uid"),
        )
    except QuoteError as exc:
        logger.warning("Error creando cotizacion: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo inesperado al crear cotizacion: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudo crear la cotizacion") from exc


@app.get("/api/quotes", response_model=QuoteListResponse)
async def list_quotes_endpoint(
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
    estados: Optional[List[QuoteStatus]] = Query(None),
    search: Optional[str] = Query(None),
    cliente_rut: Optional[str] = Query(None, alias="clienteRut"),
    prepared_by: Optional[str] = Query(None, alias="preparedBy"),
    quote_number: Optional[str] = Query(None),
    created_from: Optional[str] = Query(None, alias="createdFrom"),
    created_to: Optional[str] = Query(None, alias="createdTo"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    decoded = verify_bearer_token(authorization)
    ensure_quote_admin_access(decoded)
    company_id = resolve_quote_company(decoded, empresa_id)
    require_quote_pool()
    filters = QuoteListFilters(
        estados=estados,
        search=search,
        cliente_rut=cliente_rut,
        prepared_by=prepared_by,
        quote_number=quote_number,
        created_from=parse_iso8601(created_from),
        created_to=parse_iso8601(created_to),
    )
    pagination = Pagination(page=page, page_size=page_size)
    try:
        return await quote_service.list_quotes_service(filters, pagination, empresa_id=company_id)
    except Exception as exc:
        logger.exception("Fallo inesperado al listar cotizaciones: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudieron listar las cotizaciones") from exc


@app.get("/api/quotes/{quote_id}", response_model=QuoteDetail)
async def get_quote_endpoint(
    quote_id: str,
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
):
    decoded = verify_bearer_token(authorization)
    ensure_quote_admin_access(decoded)
    company_id = resolve_quote_company(decoded, empresa_id)
    require_quote_pool()
    try:
        quote_uuid = uuid.UUID(quote_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="quoteId invalido")
    try:
        return await quote_service.get_quote_detail(quote_uuid, empresa_id=company_id)
    except QuoteNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo inesperado al obtener cotizacion %s: %s", quote_id, exc)
        raise HTTPException(status_code=500, detail="No se pudo obtener la cotizacion") from exc


@app.put("/api/quotes/{quote_id}", response_model=QuoteDetail)
async def update_quote_endpoint(
    quote_id: str,
    payload: QuoteUpdatePayload,
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
):
    decoded = verify_bearer_token(authorization)
    email = ensure_quote_admin_access(decoded)
    company_id = resolve_quote_company(decoded, empresa_id)
    require_quote_pool()
    try:
        quote_uuid = uuid.UUID(quote_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="quoteId invalido")
    try:
        return await quote_service.update_quote(
            quote_uuid,
            payload,
            empresa_id=company_id,
            actor_email=email,
            actor_uid=decoded.get("uid"),
        )
    except QuoteNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QuoteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo inesperado al actualizar cotizacion %s: %s", quote_id, exc)
        raise HTTPException(status_code=500, detail="No se pudo actualizar la cotizacion") from exc


@app.patch("/api/quotes/{quote_id}/status", response_model=QuoteDetail)
async def change_quote_status_endpoint(
    quote_id: str,
    payload: QuoteStatusChange,
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
):
    decoded = verify_bearer_token(authorization)
    email = ensure_quote_admin_access(decoded)
    company_id = resolve_quote_company(decoded, empresa_id)
    require_quote_pool()
    try:
        quote_uuid = uuid.UUID(quote_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="quoteId invalido")
    try:
        return await quote_service.change_quote_status(
            quote_uuid,
            payload.estado,
            empresa_id=company_id,
            actor_email=email,
            actor_uid=decoded.get("uid"),
            descripcion=payload.descripcion,
        )
    except QuoteNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo inesperado al cambiar estado de cotizacion %s: %s", quote_id, exc)
        raise HTTPException(status_code=500, detail="No se pudo actualizar el estado de la cotizacion") from exc


@app.post("/api/quotes/{quote_id}/events/pdf")
async def log_quote_pdf_event(
    quote_id: str,
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
):
    decoded = verify_bearer_token(authorization)
    email = ensure_quote_admin_access(decoded)
    company_id = resolve_quote_company(decoded, empresa_id)
    require_quote_pool()
    try:
        quote_uuid = uuid.UUID(quote_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="quoteId invalido")
    try:
        await quote_service.log_pdf_download(
            quote_uuid,
            empresa_id=company_id,
            actor_email=email,
            actor_uid=decoded.get("uid"),
        )
        return {"ok": True}
    except Exception as exc:
        logger.exception("Fallo registrando descarga de PDF %s: %s", quote_id, exc)
        raise HTTPException(status_code=500, detail="No se pudo registrar la descarga de PDF") from exc


@app.get("/api/quote-catalog", response_model=CatalogResponse)
async def get_quote_catalog_endpoint(
    authorization: Optional[str] = Header(None),
    include_inactive: bool = Query(False),
):
    decoded = verify_bearer_token(authorization)
    ensure_quote_admin_access(decoded)
    require_quote_pool()
    effective_include = include_inactive if is_master_admin(decoded) else False
    try:
        catalog = await quote_service.get_catalog_service(include_inactive=effective_include)
        return {"items": catalog}
    except Exception as exc:
        logger.exception("Fallo inesperado al obtener catalogo de cotizador: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudo obtener el catalogo de cotizaciones") from exc


@app.put("/api/quote-catalog", response_model=CatalogCategoryOut)
async def upsert_quote_catalog_endpoint(
    payload: CatalogUpsertPayload,
    authorization: Optional[str] = Header(None),
):
    decoded = verify_bearer_token(authorization)
    if not is_master_admin(decoded):
        raise HTTPException(status_code=403, detail="Solo administradores maestros pueden actualizar el catalogo")
    ensure_quote_admin_access(decoded)
    require_quote_pool()
    try:
        catalog_uuid = uuid.UUID(payload.catalog_id) if payload.catalog_id else None
    except ValueError:
        raise HTTPException(status_code=400, detail="catalogId invalido")
    try:
        category = await quote_service.upsert_catalog_service(
            slug=payload.slug,
            nombre=payload.nombre,
            descripcion=payload.descripcion,
            activo=payload.activo,
            items=payload.items,
            catalog_id=catalog_uuid,
        )
        return category
    except CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo inesperado al actualizar catalogo del cotizador: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudo actualizar el catalogo") from exc


@app.delete("/api/quote-catalog/items/{item_id}")
async def delete_quote_catalog_item_endpoint(
    item_id: str,
    authorization: Optional[str] = Header(None),
):
    decoded = verify_bearer_token(authorization)
    if not is_master_admin(decoded):
        raise HTTPException(status_code=403, detail="Solo administradores maestros pueden eliminar items del catalogo")
    ensure_quote_admin_access(decoded)
    require_quote_pool()
    try:
        item_uuid = uuid.UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="itemId invalido")
    try:
        await quote_service.delete_catalog_item_service(item_uuid)
        return {"ok": True}
    except Exception as exc:
        logger.exception("Fallo inesperado al eliminar item del catalogo %s: %s", item_id, exc)
        raise HTTPException(status_code=500, detail="No se pudo eliminar el item del catalogo") from exc


@app.get("/api/clients", response_model=ClientListResponse)
async def list_clients_endpoint(
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
):
    decoded = verify_bearer_token(authorization)
    ensure_quote_admin_access(decoded)
    company_id = resolve_quote_company(decoded, empresa_id)
    require_quote_pool()
    try:
        clients = await quote_service.list_clients_service(company_id, query=q, limit=limit)
        return {"empresaId": company_id, "results": clients}
    except Exception as exc:
        logger.exception("Fallo inesperado al listar clientes del cotizador: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudieron listar los clientes") from exc


@app.post("/api/clients", response_model=ClientSummary)
async def create_client_endpoint(
    payload: ClientCreatePayload,
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
):
    decoded = verify_bearer_token(authorization)
    ensure_quote_admin_access(decoded)
    company_id = resolve_quote_company(decoded, empresa_id)
    require_quote_pool()
    try:
        client = await quote_service.create_client_service(company_id, payload)
        return client
    except ClientExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Fallo inesperado al crear cliente del cotizador: %s", exc)
        raise HTTPException(status_code=500, detail="No se pudo crear el cliente") from exc


@app.get("/trend")
def get_trend_page():
    if not TREND_HTML_PATH.exists():
        raise HTTPException(status_code=404, detail="trend.html no disponible")
    return FileResponse(TREND_HTML_PATH, media_type="text/html")


@app.get("/api/tendencias/tags")
async def list_trend_tags(
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
    planta_id: Optional[str] = Query(None, alias="plantaId"),
    limit: int = Query(200, ge=1, le=1000),
):
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

    config = load_scada_config(company_id)
    email = decoded.get("email") if decoded else None
    role = "admin" if is_master else role_for_email(config, email)
    allowed_plants = [normalize_plant_id(pid) for pid in resolve_user_plant_ids(config, email, role, is_master)]
    plants_list = config.get("plants") or []
    # Normaliza planta solicitada
    selected_plants: Optional[List[str]] = None
    if planta_id:
        plant_candidate = normalize_plant_id(planta_id)
        if allowed_plants and plant_candidate not in allowed_plants:
            raise HTTPException(status_code=403, detail="Planta no autorizada")
        selected_plants = [plant_candidate]
    elif allowed_plants:
        selected_plants = allowed_plants

    pool = require_trend_pool()
    effective_limit = max(1, min(int(limit), 1000))
    if selected_plants is not None:
        query = """
            SELECT DISTINCT tag
            FROM trends
            WHERE empresa_id = $1
              AND planta_id = ANY($2)
            ORDER BY tag ASC
            LIMIT $3
        """
        params = (company_id, selected_plants, effective_limit)
    else:
        query = """
            SELECT DISTINCT tag
            FROM trends
            WHERE empresa_id = $1
            ORDER BY tag ASC
            LIMIT $2
        """
        params = (company_id, effective_limit)
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    tags = [row["tag"] for row in rows if row["tag"]]
    visible_plants = []
    for item in plants_list:
        raw_id = item.get("id") or item.get("serialCode") or item.get("name") or ""
        norm_id = normalize_plant_id(raw_id)
        if allowed_plants and norm_id not in allowed_plants:
            continue
        visible_plants.append({"id": norm_id, "name": item.get("name") or raw_id})
    return {
        "empresaId": company_id,
        "tags": tags,
        "count": len(tags),
        "plants": visible_plants,
        "selectedPlantas": selected_plants or [],
    }


@app.get("/api/tendencias")
async def read_trend_series(
    tags: List[str] = Query(..., alias="tag"),
    authorization: Optional[str] = Header(None),
    empresa_id: Optional[str] = Query(None),
    planta_id: Optional[str] = Query(None, alias="plantaId"),
    from_ts: Optional[str] = Query(None, alias="from"),
    to_ts: Optional[str] = Query(None, alias="to"),
    resolution: str = Query("raw"),
    limit: Optional[int] = Query(None, ge=1, le=10000),
):
    if not tags:
        raise HTTPException(status_code=400, detail="tag es requerido")

    normalized_tags: List[str] = []
    seen: Set[str] = set()
    for raw in tags:
        if raw is None:
            continue
        candidate = raw.strip()
        if not candidate:
            continue
        lowered = candidate.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized_tags.append(candidate)

    if not normalized_tags:
        raise HTTPException(status_code=400, detail="tag es requerido")

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

    config = load_scada_config(company_id)
    email = decoded.get("email") if decoded else None
    role = "admin" if is_master else role_for_email(config, email)
    allowed_plants = [normalize_plant_id(pid) for pid in resolve_user_plant_ids(config, email, role, is_master)]
    selected_plants: Optional[List[str]] = None
    if planta_id:
        plant_candidate = normalize_plant_id(planta_id)
        if allowed_plants and plant_candidate not in allowed_plants:
            raise HTTPException(status_code=403, detail="Planta no autorizada")
        selected_plants = [plant_candidate]
    elif allowed_plants:
        selected_plants = allowed_plants

    resolution_key = (resolution or "raw").strip().lower()
    if resolution_key not in TRENDS_RESOLUTION_SECONDS:
        raise HTTPException(status_code=400, detail=f"Resolucion no soportada: {resolution}")
    interval_seconds = TRENDS_RESOLUTION_SECONDS[resolution_key]

    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
    end_dt = parse_iso8601(to_ts) or now_utc
    start_dt = parse_iso8601(from_ts) or (end_dt - timedelta(hours=DEFAULT_TRENDS_RANGE_HOURS))
    if start_dt >= end_dt:
        raise HTTPException(status_code=400, detail="El rango de fechas es invalido")

    fetch_limit = TRENDS_FETCH_LIMIT
    if limit is not None:
        try:
            fetch_limit = max(1, min(int(limit), TRENDS_FETCH_LIMIT))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"limit invalido: {exc}") from exc

    pool = require_trend_pool()
    series_collection: List[Dict[str, Any]] = []
    total_points = 0

    async with pool.acquire() as conn:
        for normalized_tag in normalized_tags:
            stats_query = """
                SELECT
                    COUNT(*) OVER () AS count,
                    MIN(valor) OVER () AS min_value,
                    MAX(valor) OVER () AS max_value,
                    AVG(valor) OVER () AS avg_value,
                    FIRST_VALUE(valor) OVER (ORDER BY timestamp DESC) AS latest_value,
                    FIRST_VALUE(timestamp) OVER (ORDER BY timestamp DESC) AS latest_timestamp
                FROM trends
                WHERE empresa_id = $1
                  AND tag = $2
                  {planta_filter}
                  AND timestamp BETWEEN $3 AND $4
                ORDER BY timestamp DESC
                LIMIT 1
            """.format(planta_filter="AND planta_id = ANY($5)" if selected_plants is not None else "")
            stats_params = [company_id, normalized_tag, start_dt, end_dt]
            if selected_plants is not None:
                stats_params.append(selected_plants)
            stats_row = await conn.fetchrow(stats_query, *stats_params)

            if stats_row is None or not stats_row["count"]:
                series_collection.append(
                    {
                        "tag": normalized_tag,
                        "points": [],
                        "stats": None,
                        "count": 0,
                    }
                )
                continue

            if interval_seconds is None:
                data_query = """
                    SELECT timestamp, valor
                    FROM trends
                    WHERE empresa_id = $1
                      AND tag = $2
                      {planta_filter}
                      AND timestamp BETWEEN $3 AND $4
                    ORDER BY timestamp ASC
                    LIMIT $5
                """.format(
                    planta_filter="AND planta_id = ANY($6)" if selected_plants is not None else ""
                )
                params = [company_id, normalized_tag, start_dt, end_dt, fetch_limit]
                if selected_plants is not None:
                    params.append(selected_plants)
                rows = await conn.fetch(data_query, *params)
                points = [
                    {"timestamp": isoformat_utc(row["timestamp"]), "value": float(row["valor"])}  # type: ignore[arg-type]
                    for row in rows
                ]
            else:
                data_query = """
                    SELECT to_timestamp(floor(extract(epoch FROM timestamp)/$5)*$5) AS bucket,
                           AVG(valor) AS value
                    FROM trends
                    WHERE empresa_id = $1
                      AND tag = $2
                      {planta_filter}
                      AND timestamp BETWEEN $3 AND $4
                    GROUP BY bucket
                    ORDER BY bucket ASC
                    LIMIT $6
                """.format(
                    planta_filter="AND planta_id = ANY($7)" if selected_plants is not None else ""
                )
                params = [
                    company_id,
                    normalized_tag,
                    start_dt,
                    end_dt,
                    interval_seconds,
                    fetch_limit,
                ]
                if selected_plants is not None:
                    params.append(selected_plants)
                rows = await conn.fetch(
                    data_query,
                    *params,
                )
                points = [
                    {"timestamp": isoformat_utc(row["bucket"]), "value": float(row["value"])}  # type: ignore[arg-type]
                    for row in rows
                ]

            total_points += len(points)
            stats = {
                "latest": float(stats_row["latest_value"]) if stats_row["latest_value"] is not None else None,
                "min": float(stats_row["min_value"]) if stats_row["min_value"] is not None else None,
                "max": float(stats_row["max_value"]) if stats_row["max_value"] is not None else None,
                "avg": float(stats_row["avg_value"]) if stats_row["avg_value"] is not None else None,
                "latestTimestamp": isoformat_utc(stats_row["latest_timestamp"]),
                "count": int(stats_row["count"]),
            }
            series_collection.append(
                {
                    "tag": normalized_tag,
                    "points": points,
                    "stats": stats,
                    "count": len(points),
                }
            )

    meta = {
        "tags": normalized_tags,
        "empresaId": company_id,
        "resolution": resolution_key,
        "from": isoformat_utc(start_dt),
        "to": isoformat_utc(end_dt),
        "limit": fetch_limit,
        "datasetSize": sum(entry["count"] for entry in series_collection),
        "totalPoints": total_points,
        "requested": len(normalized_tags),
    }
    return {"series": series_collection, "meta": meta}


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
    plantIds: Optional[List[str]] = None


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
    fallback = any(not user.get("uid") for user in users)
    payload: Dict[str, Any] = {"empresaId": company_id, "users": users, "fallback": fallback}
    if fallback:
        payload["message"] = "No se pudo obtener el detalle completo desde Firebase. Se muestran los correos configurados."
    return payload


@app.post("/users", status_code=201)
def create_user_endpoint(payload: UserCreate, authorization: Optional[str] = Header(None)):
    decoded = verify_bearer_token(authorization)
    actor_email = decoded.get("email")
    target = payload.empresaId or extract_company_id(decoded)
    if not target:
        raise HTTPException(status_code=400, detail="empresaId requerido")
    company_id = ensure_company_admin(decoded, target)
    role = sanitize_user_role(payload.role)
    requested_plants = payload.plantIds
    email = payload.email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email requerido")
    try:
        user_record = firebase_auth.create_user(email=email, app=firebase_app)
    except firebase_exceptions.FirebaseError as exc:
        if getattr(exc, "code", "") == "email-already-exists":
            raise HTTPException(status_code=409, detail="El correo ya esta registrado") from exc
        logger.exception("No se pudo crear usuario %s: %s", email, exc)
        raise HTTPException(status_code=502, detail=f"No se pudo crear el usuario: {exc}") from exc
    except Exception as exc:
        logger.exception("Error inesperado al crear usuario %s: %s", email, exc)
        raise HTTPException(status_code=502, detail=f"No se pudo crear el usuario: {exc}") from exc
    claims = merge_custom_claims({}, company_id, role)
    try:
        firebase_auth.set_custom_user_claims(user_record.uid, claims, app=firebase_app)
    except firebase_exceptions.FirebaseError as exc:
        logger.exception("No se pudo asignar claims para %s: %s", email, exc)
        try:
            firebase_auth.delete_user(user_record.uid, app=firebase_app)
        except Exception:
            logger.exception("No se pudo revertir usuario creado %s", email)
        raise HTTPException(status_code=502, detail=f"No se pudo asignar claims al usuario: {exc}") from exc
    except Exception as exc:
        logger.exception("Error inesperado asignando claims para %s: %s", email, exc)
        try:
            firebase_auth.delete_user(user_record.uid, app=firebase_app)
        except Exception:
            logger.exception("No se pudo revertir usuario creado %s", email)
        raise HTTPException(status_code=502, detail=f"No se pudo asignar claims al usuario: {exc}") from exc
    try:
        apply_role_to_config(company_id, email, role, actor_email, plant_ids=requested_plants)
    except Exception as exc:
        logger.exception("No se pudo actualizar roles para %s: %s", email, exc)
        try:
            firebase_auth.delete_user(user_record.uid, app=firebase_app)
        except Exception:
            logger.exception("No se pudo revertir usuario tras fallo de configuracion %s", email)
        raise HTTPException(status_code=500, detail="No se pudo actualizar la configuracion de la empresa") from exc
    metadata = getattr(user_record, "user_metadata", None)
    created_at = firebase_timestamp_to_iso(getattr(metadata, "creation_timestamp", None)) if metadata else None
    last_login = firebase_timestamp_to_iso(getattr(metadata, "last_sign_in_timestamp", None)) if metadata else None
    action_settings = build_action_code_settings()
    reset_link = None
    try:
        reset_link = firebase_auth.generate_password_reset_link(email, action_settings, app=firebase_app)
    except firebase_exceptions.FirebaseError as exc:
        logger.warning("No se pudo generar link de recuperacion para %s: %s", email, exc)
    invite_sent = False
    if payload.sendInvite and reset_link:
        invite_sent = send_password_reset_email(email, None)
    cfg_after = load_scada_config(company_id)
    assigned_plant_ids = resolve_user_plant_ids(cfg_after, email, role, False)
    plants_lookup = plant_lookup(cfg_after.get("plants", []) or [])
    plant_serials = [plants_lookup[pid]["serialCode"] for pid in assigned_plant_ids if pid in plants_lookup]
    plant_names = [plants_lookup[pid]["name"] for pid in assigned_plant_ids if pid in plants_lookup]
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
            "plantIds": assigned_plant_ids,
            "plantSerials": plant_serials,
            "plantNames": plant_names,
        },
        "resetLink": reset_link,
        "inviteSent": invite_sent,
    }


@app.delete("/users/{uid}")
def delete_user_endpoint(uid: str, authorization: Optional[str] = Header(None), empresa_id: Optional[str] = Query(None)):
    decoded = verify_bearer_token(authorization)
    actor_email = decoded.get("email")
    try:
        user_record = firebase_auth.get_user(uid, app=firebase_app)
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
        firebase_auth.delete_user(uid, app=firebase_app)
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
        user_record = firebase_auth.get_user(uid, app=firebase_app)
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
        reset_link = firebase_auth.generate_password_reset_link(user_record.email, action_settings, app=firebase_app)
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
    cfg = load_scada_config(company_id)
    prefixes = allowed_prefixes_for_user(uid, company_id, decoded=decoded, cfg=cfg)
    normalized_prefixes = [x.rstrip("/") + "/" for x in prefixes]
    if not normalized_prefixes:
        raise HTTPException(status_code=403, detail="Usuario sin plantas asignadas")
    if not any(p.topic.startswith(pref) for pref in normalized_prefixes):
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
    cfg = load_scada_config(company_id)
    prefixes = allowed_prefixes_for_user(uid, company_id, decoded=decoded, cfg=cfg)
    if not prefixes:
        await websocket.send_json({"type": "error", "error": "Usuario sin plantas asignadas"})
        await websocket.close(code=4403)
        return
    try:
        ensure_mqtt_connected(broker_key)
    except HTTPException as exc:
        await websocket.send_json({"type": "error", "error": exc.detail or "MQTT broker not connected"})
        await websocket.close(code=1013)
        return

    session_pool = trend_db_pool
    session_id = str(uuid.uuid4())
    session_claimed = False
    if session_pool is not None:
        claimed, claim_error = await claim_session_slot(session_pool, session_id, company_id, uid)
        if not claimed:
            await websocket.send_json({"type": "error", "error": claim_error or "Limite de usuarios activos superado"})
            await websocket.close(code=4403)
            return
        session_claimed = True
    else:
        logger.warning("Pool de base de datos no disponible; omitiendo control de sesiones para WS de %s", uid)

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
            if session_pool is not None and session_claimed:
                await touch_session(session_pool, session_id)
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
        pass
    except Exception:
        logger.exception("Error en WS para uid=%s empresa=%s", uid, company_id)
    finally:
        if session_pool is not None and session_claimed:
            await drop_session(session_pool, session_id)
        ConnectionManager.remove(websocket)
        try:
            await websocket.close()
        except Exception:
            pass























