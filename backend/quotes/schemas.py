from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .enums import QuoteEventType, QuoteStatus


class QuoteClientInfo(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nombre: str = Field(min_length=1, max_length=200)
    rut: str = Field(min_length=3, max_length=32)
    contacto: Optional[str] = Field(default=None, max_length=120)
    correo: Optional[EmailStr] = None
    telefono: Optional[str] = Field(default=None, max_length=40)


class QuoteItemInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    descripcion: str = Field(min_length=1, max_length=300)
    cantidad: int = Field(ge=0, le=10_000)
    precio_uf: Decimal = Field(ge=0)
    nota: Optional[str] = Field(default=None, max_length=500)
    orden: Optional[int] = Field(default=None, ge=0, le=10_000)
    catalog_slug: Optional[str] = Field(default=None, max_length=100)


class QuoteCreatePayload(BaseModel):
    cliente: QuoteClientInfo
    items: List[QuoteItemInput]
    prepared_by: str = Field(min_length=1, max_length=120)
    prepared_email: Optional[EmailStr] = None
    descuento_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    uf_valor_clp: Optional[Decimal] = Field(default=None, ge=0)
    vigencia_dias: int = Field(default=30, ge=1, le=180)
    observaciones: Optional[str] = Field(default=None, max_length=2000)


class QuoteUpdatePayload(BaseModel):
    cliente: QuoteClientInfo
    items: List[QuoteItemInput]
    descuento_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    uf_valor_clp: Optional[Decimal] = Field(default=None, ge=0)
    vigencia_dias: int = Field(default=30, ge=1, le=180)
    observaciones: Optional[str] = Field(default=None, max_length=2000)
    prepared_by: Optional[str] = Field(default=None, max_length=120)
    prepared_email: Optional[EmailStr] = None


class QuoteListFilters(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    estados: Optional[List[QuoteStatus]] = None
    search: Optional[str] = Field(default=None, max_length=120)
    cliente_rut: Optional[str] = Field(default=None, max_length=32)
    prepared_by: Optional[str] = Field(default=None, max_length=120)
    quote_number: Optional[str] = Field(default=None, max_length=80)
    created_from: Optional[datetime] = None
    created_to: Optional[datetime] = None


class Pagination(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class QuoteItemOut(BaseModel):
    descripcion: str
    cantidad: int
    precio_unitario_uf: Decimal
    total_uf: Decimal
    nota: Optional[str] = None
    orden: Optional[int] = None
    catalog_slug: Optional[str] = None


class QuoteEventOut(BaseModel):
    id: str
    tipo: QuoteEventType
    descripcion: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: datetime
    actor_email: Optional[str] = None


class QuoteSummary(BaseModel):
    id: str
    quote_number: str
    estado: QuoteStatus
    cliente_nombre: str
    cliente_rut: str
    cliente_contacto: Optional[str] = None
    cliente_correo: Optional[str] = None
    cliente_telefono: Optional[str] = None
    total_uf: Decimal
    vigencia_hasta: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class QuoteDetail(QuoteSummary):
    subtotal_uf: Decimal
    descuento_pct: Decimal
    descuento_uf: Decimal
    neto_uf: Decimal
    iva_uf: Decimal
    prepared_by: Optional[str] = None
    prepared_email: Optional[str] = None
    uf_valor_clp: Optional[Decimal] = None
    observaciones: Optional[str] = None
    catalog_snapshot: Optional[dict] = None
    items: List[QuoteItemOut]
    eventos: List[QuoteEventOut]


class QuoteStatusChange(BaseModel):
    estado: QuoteStatus
    descripcion: Optional[str] = Field(default=None, max_length=240)


class QuoteListResponse(BaseModel):
    results: List[QuoteSummary]
    page: int
    page_size: int
    total: int


from datetime import datetime, date

class CatalogItemOut(BaseModel):
    id: str
    label: str
    valor_uf: Decimal
    nota: Optional[str] = None
    orden: int
    valid_from: date
    valid_to: Optional[date] = None
    catalog_id: str


class CatalogCategoryOut(BaseModel):
    id: str
    slug: str
    nombre: str
    descripcion: Optional[str] = None
    activo: bool
    items: List[CatalogItemOut]


class CatalogItemUpsert(BaseModel):
    id: Optional[str] = None
    catalog_id: Optional[str] = None
    slug: Optional[str] = None
    label: str
    valor_uf: Decimal = Field(ge=0)
    nota: Optional[str] = Field(default=None, max_length=500)
    orden: int = Field(default=0, ge=0, le=10_000)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


class CatalogUpsertPayload(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    nombre: str = Field(min_length=1, max_length=200)
    descripcion: Optional[str] = Field(default=None, max_length=500)
    activo: bool = True
    items: List[CatalogItemUpsert]
    catalog_id: Optional[str] = None


class CatalogResponse(BaseModel):
    items: List[CatalogCategoryOut]


class ClientCreatePayload(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    rut: str = Field(min_length=3, max_length=32)
    contacto: Optional[str] = Field(default=None, max_length=120)
    correo: Optional[EmailStr] = None
    telefono: Optional[str] = Field(default=None, max_length=40)
    notas: Optional[str] = Field(default=None, max_length=500)


class ClientSummary(BaseModel):
    id: str
    empresa_id: str
    nombre: str
    rut: str
    contacto: Optional[str] = None
    correo: Optional[str] = None
    telefono: Optional[str] = None
    notas: Optional[str] = None


class ClientListResponse(BaseModel):
    empresaId: str
    results: List[ClientSummary]
