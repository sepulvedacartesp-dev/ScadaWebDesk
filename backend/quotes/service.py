from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple

import asyncpg

from . import db as quote_db
from .enums import FINAL_STATUSES, QuoteEventType, QuoteStatus, STATUS_TRANSITIONS
from .exceptions import (
    CatalogError,
    ClientExistsError,
    InvalidStatusTransition,
    QuoteError,
    QuoteNotFoundError,
)
from .repository import (
    delete_catalog_item,
    fetch_catalog,
    fetch_clients,
    fetch_quote,
    fetch_quote_events,
    fetch_quote_items,
    insert_client,
    insert_quote,
    insert_quote_event,
    list_quotes,
    replace_quote_items,
    touch_quote_status,
    update_quote as update_quote_record,
    upsert_catalog_category,
    upsert_catalog_item,
)
from .schemas import (
    CatalogItemUpsert,
    CatalogCategoryOut,
    CatalogItemOut,
    ClientCreatePayload,
    ClientSummary,
    Pagination,
    QuoteCreatePayload,
    QuoteDetail,
    QuoteEventOut,
    QuoteItemInput,
    QuoteItemOut,
    QuoteListFilters,
    QuoteSummary,
    QuoteUpdatePayload,
)


TAX_RATE = Decimal("0.19")
UF_QUANT = Decimal("0.01")


def _round_uf(value: Decimal) -> Decimal:
    return value.quantize(UF_QUANT, rounding=ROUND_HALF_UP)


def _normalize_rut(value: str) -> str:
    return value.strip().upper()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def _catalog_id_map(conn: asyncpg.Connection, slugs: Iterable[str]) -> Dict[str, uuid.UUID]:
    cleaned = [slug for slug in slugs if slug]
    if not cleaned:
        return {}
    rows = await conn.fetch(
        "SELECT slug, id FROM quote_catalog WHERE slug = ANY($1::text[])",
        cleaned,
    )
    return {row["slug"]: row["id"] for row in rows}


async def _next_quote_number(conn: asyncpg.Connection, empresa_id: str) -> str:
    current_year = _now_utc().year
    prefix = f"SUR-{empresa_id}-{current_year}-"
    row = await conn.fetchrow(
        """
        SELECT quote_number
        FROM quotes
        WHERE empresa_id = $1 AND quote_number LIKE $2
        ORDER BY quote_number DESC
        LIMIT 1
        """,
        empresa_id,
        f"{prefix}%",
    )
    if not row:
        return f"{prefix}001"
    try:
        last_seq = int(str(row["quote_number"]).rsplit("-", maxsplit=1)[-1])
    except (ValueError, AttributeError):
        last_seq = 0
    return f"{prefix}{last_seq + 1:03d}"


def _build_items_snapshot(items: List[QuoteItemInput], totals: List[Decimal]) -> Dict[str, Any]:
    generated_at = _now_utc().isoformat()
    snapshot_items = []
    for item, total in zip(items, totals):
        snapshot_items.append(
            {
                "descripcion": item.descripcion,
                "cantidad": item.cantidad,
                "precioUF": str(item.precio_uf),
                "totalUF": str(total),
                "nota": item.nota,
                "catalogSlug": item.catalog_slug,
            }
        )
    return {"generatedAt": generated_at, "items": snapshot_items}


def _compute_totals(items: List[QuoteItemInput], descuento_pct: Decimal) -> Tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    subtotales = []
    for item in items:
        line_total = Decimal(item.cantidad) * item.precio_uf
        subtotales.append(_round_uf(line_total))
    subtotal = _round_uf(sum(subtotales, Decimal("0")))
    discount_rate = (descuento_pct or Decimal("0")) / Decimal("100")
    discount_rate = max(Decimal("0"), min(discount_rate, Decimal("1")))
    descuento = _round_uf(subtotal * discount_rate)
    neto = _round_uf(subtotal - descuento)
    iva = _round_uf(neto * TAX_RATE)
    total = _round_uf(neto + iva)
    return subtotal, descuento, neto, iva, total


async def create_quote(
    payload: QuoteCreatePayload,
    *,
    empresa_id: str,
    actor_email: Optional[str],
    actor_uid: Optional[str],
) -> QuoteDetail:
    if not payload.items:
        raise QuoteError("La cotizacion debe contener al menos un item")
    pool = quote_db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            attempts = 0
            quote_record = None
            subtotal, descuento, neto, iva, total = _compute_totals(payload.items, payload.descuento_pct)
            totals_by_item = [
                _round_uf(Decimal(item.cantidad) * item.precio_uf) for item in payload.items
            ]
            catalog_snapshot = _build_items_snapshot(payload.items, totals_by_item)
            vigencia_hasta = _now_utc() + timedelta(days=payload.vigencia_dias)
            catalog_map = await _catalog_id_map(conn, [item.catalog_slug for item in payload.items if item.catalog_slug])
            while attempts < 10:
                attempts += 1
                quote_number = await _next_quote_number(conn, empresa_id)
                quote_id = uuid.uuid4()
                try:
                    quote_record = await insert_quote(
                        conn,
                        {
                            "id": quote_id,
                            "empresa_id": empresa_id,
                            "quote_number": quote_number,
                            "estado": QuoteStatus.BORRADOR.value,
                            "cliente_nombre": payload.cliente.nombre,
                            "cliente_rut": _normalize_rut(payload.cliente.rut),
                            "contacto": payload.cliente.contacto,
                            "correo": str(payload.cliente.correo) if payload.cliente.correo else None,
                            "telefono": payload.cliente.telefono,
                            "prepared_by": payload.prepared_by,
                            "prepared_email": str(payload.prepared_email) if payload.prepared_email else None,
                            "subtotal_uf": subtotal,
                            "descuento_pct": payload.descuento_pct,
                            "neto_uf": neto,
                            "iva_uf": iva,
                            "total_uf": total,
                            "uf_valor_clp": payload.uf_valor_clp,
                            "vigencia_hasta": vigencia_hasta,
                            "observaciones": payload.observaciones,
                            "catalog_snapshot": catalog_snapshot,
                        },
                    )
                    break
                except asyncpg.UniqueViolationError:
                    continue
            if quote_record is None:
                raise QuoteError("No se pudo generar un folio unico para la cotizacion")

            await replace_quote_items(
                conn,
                quote_record["id"],
                [
                    {
                        "descripcion": item.descripcion,
                        "cantidad": item.cantidad,
                        "precio_unitario_uf": item.precio_uf,
                        "total_uf": total_item,
                        "nota": item.nota,
                        "orden": item.orden or index,
                        "catalog_id": catalog_map.get(item.catalog_slug) if item.catalog_slug else None,
                    }
                    for index, (item, total_item) in enumerate(zip(payload.items, totals_by_item), start=1)
                ],
            )
            await insert_quote_event(
                conn,
                {
                    "id": uuid.uuid4(),
                    "quote_id": quote_record["id"],
                    "empresa_id": empresa_id,
                    "evento": QuoteEventType.CREATED.value,
                    "descripcion": "Cotizacion creada",
                    "metadata": {"totalUF": str(total)},
                    "actor_uid": actor_uid,
                    "actor_email": actor_email,
                },
            )
            return await _build_quote_detail(conn, quote_record, payload.items, totals_by_item, None)


async def _build_quote_detail(
    conn: asyncpg.Connection,
    record: asyncpg.Record,
    items_input: Optional[List[QuoteItemInput]] = None,
    totals: Optional[List[Decimal]] = None,
    events_records: Optional[List[asyncpg.Record]] = None,
) -> QuoteDetail:
    quote_id = record["id"]
    if items_input is None or totals is None:
        item_rows = await fetch_quote_items(conn, quote_id)
        items = [
            QuoteItemOut(
                descripcion=row["descripcion"],
                cantidad=row["cantidad"],
                precio_unitario_uf=row["precio_unitario_uf"],
                total_uf=row["total_uf"],
                nota=row["nota"],
                orden=row["orden"],
                catalog_slug=row["catalog_slug"],
            )
            for row in item_rows
        ]
    else:
        items = [
            QuoteItemOut(
                descripcion=item.descripcion,
                cantidad=item.cantidad,
                precio_unitario_uf=item.precio_uf,
                total_uf=total,
                nota=item.nota,
                orden=item.orden or idx,
                catalog_slug=item.catalog_slug,
            )
            for idx, (item, total) in enumerate(zip(items_input, totals), start=1)
        ]

    if events_records is None:
        event_rows = await fetch_quote_events(conn, quote_id)
    else:
        event_rows = events_records
    eventos = [
        QuoteEventOut(
            id=str(row["id"]),
            tipo=QuoteEventType(row["evento"]),
            descripcion=row["descripcion"],
            metadata=row["metadata"],
            created_at=row["created_at"],
            actor_email=row["actor_email"],
        )
        for row in event_rows
    ]

    descuento_pct = record["descuento_pct"] if record["descuento_pct"] is not None else Decimal("0")
    descuento_uf = _round_uf(record["subtotal_uf"] * (descuento_pct / Decimal("100")))

    return QuoteDetail(
        id=str(record["id"]),
        quote_number=record["quote_number"],
        estado=QuoteStatus(record["estado"]),
        cliente_nombre=record["cliente_nombre"],
        cliente_rut=record["cliente_rut"],
        subtotal_uf=record["subtotal_uf"],
        descuento_pct=descuento_pct,
        descuento_uf=descuento_uf,
        neto_uf=record["neto_uf"],
        iva_uf=record["iva_uf"],
        total_uf=record["total_uf"],
        vigencia_hasta=record["vigencia_hasta"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        prepared_by=record["prepared_by"],
        prepared_email=record["prepared_email"],
        uf_valor_clp=record["uf_valor_clp"],
        observaciones=record["observaciones"],
        catalog_snapshot=record["catalog_snapshot"],
        items=items,
        eventos=eventos,
    )


async def update_quote(
    quote_id: uuid.UUID,
    payload: QuoteUpdatePayload,
    *,
    empresa_id: str,
    actor_email: Optional[str],
    actor_uid: Optional[str],
) -> QuoteDetail:
    if not payload.items:
        raise QuoteError("La cotizacion debe contener al menos un item")
    pool = quote_db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            current = await fetch_quote(conn, quote_id, empresa_id, for_update=True)
            if current is None:
                raise QuoteNotFoundError("Cotizacion no encontrada")
            current_status = QuoteStatus(current["estado"])
            if current_status in FINAL_STATUSES:
                raise InvalidStatusTransition("No se puede editar una cotizacion finalizada")

            subtotal, descuento, neto, iva, total = _compute_totals(payload.items, payload.descuento_pct)
            totals_by_item = [
                _round_uf(Decimal(item.cantidad) * item.precio_uf) for item in payload.items
            ]
            vigencia_hasta = (
                (_now_utc() + timedelta(days=payload.vigencia_dias))
                if payload.vigencia_dias
                else current["vigencia_hasta"]
            )
            catalog_map = await _catalog_id_map(conn, [item.catalog_slug for item in payload.items if item.catalog_slug])
            updated = await update_quote_record(
                conn,
                quote_id,
                empresa_id,
                {
                    "cliente_nombre": payload.cliente.nombre,
                    "cliente_rut": _normalize_rut(payload.cliente.rut),
                    "contacto": payload.cliente.contacto,
                    "correo": str(payload.cliente.correo) if payload.cliente.correo else None,
                    "telefono": payload.cliente.telefono,
                    "prepared_by": payload.prepared_by or current["prepared_by"],
                    "prepared_email": str(payload.prepared_email) if payload.prepared_email else current["prepared_email"],
                    "subtotal_uf": subtotal,
                    "descuento_pct": payload.descuento_pct,
                    "neto_uf": neto,
                    "iva_uf": iva,
                    "total_uf": total,
                    "uf_valor_clp": payload.uf_valor_clp,
                    "vigencia_hasta": vigencia_hasta,
                    "observaciones": payload.observaciones,
                    "catalog_snapshot": _build_items_snapshot(payload.items, totals_by_item),
                },
            )
            await replace_quote_items(
                conn,
                quote_id,
                [
                    {
                        "descripcion": item.descripcion,
                        "cantidad": item.cantidad,
                        "precio_unitario_uf": item.precio_uf,
                        "total_uf": total_item,
                        "nota": item.nota,
                        "orden": item.orden or index,
                        "catalog_id": catalog_map.get(item.catalog_slug) if item.catalog_slug else None,
                    }
                    for index, (item, total_item) in enumerate(zip(payload.items, totals_by_item), start=1)
                ],
            )
            await insert_quote_event(
                conn,
                {
                    "id": uuid.uuid4(),
                    "quote_id": quote_id,
                    "empresa_id": empresa_id,
                    "evento": QuoteEventType.UPDATED.value,
                    "descripcion": "Cotizacion actualizada",
                    "metadata": {"estado": current_status.value, "totalUF": str(updated["total_uf"])},
                    "actor_uid": actor_uid,
                    "actor_email": actor_email,
                },
            )
            return await _build_quote_detail(conn, updated, payload.items, totals_by_item, None)


async def get_quote_detail(quote_id: uuid.UUID, *, empresa_id: str) -> QuoteDetail:
    pool = quote_db.get_pool()
    async with pool.acquire() as conn:
        record = await fetch_quote(conn, quote_id, empresa_id, for_update=False)
        if record is None:
            raise QuoteNotFoundError("Cotizacion no encontrada")
        return await _build_quote_detail(conn, record)


async def list_quotes_service(
    filters: QuoteListFilters,
    pagination: Pagination,
    *,
    empresa_id: str,
) -> Dict[str, Any]:
    pool = quote_db.get_pool()
    async with pool.acquire() as conn:
        limit = pagination.page_size
        offset = (pagination.page - 1) * pagination.page_size
        rows, total = await list_quotes(conn, empresa_id, filters, limit=limit, offset=offset)
        summaries = [
            QuoteSummary(
                id=str(row["id"]),
                quote_number=row["quote_number"],
                estado=QuoteStatus(row["estado"]),
                cliente_nombre=row["cliente_nombre"],
                cliente_rut=row["cliente_rut"],
                total_uf=row["total_uf"],
                vigencia_hasta=row["vigencia_hasta"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
        return {
            "results": summaries,
            "page": pagination.page,
            "page_size": pagination.page_size,
            "total": total,
        }


async def change_quote_status(
    quote_id: uuid.UUID,
    new_status: QuoteStatus,
    *,
    empresa_id: str,
    actor_email: Optional[str],
    actor_uid: Optional[str],
    descripcion: Optional[str] = None,
) -> QuoteDetail:
    pool = quote_db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            record = await fetch_quote(conn, quote_id, empresa_id, for_update=True)
            if record is None:
                raise QuoteNotFoundError("Cotizacion no encontrada")
            current_status = QuoteStatus(record["estado"])
            allowed = STATUS_TRANSITIONS.get(current_status, {current_status})
            if new_status not in allowed:
                raise InvalidStatusTransition(
                    f"No se puede cambiar de {current_status.value} a {new_status.value}"
                )
            vigencia = record["vigencia_hasta"]
            if new_status == QuoteStatus.ENVIADA and vigencia is None:
                vigencia = _now_utc() + timedelta(days=30)
            updated = await touch_quote_status(
                conn,
                quote_id,
                empresa_id,
                new_status,
                vigencia_hasta=vigencia,
            )
            await insert_quote_event(
                conn,
                {
                    "id": uuid.uuid4(),
                    "quote_id": quote_id,
                    "empresa_id": empresa_id,
                    "evento": QuoteEventType.STATUS_CHANGED.value,
                    "descripcion": descripcion or f"Estado cambiado a {new_status.value}",
                    "metadata": {
                        "from": current_status.value,
                        "to": new_status.value,
                    },
                    "actor_uid": actor_uid,
                    "actor_email": actor_email,
                },
            )
            return await _build_quote_detail(conn, updated, events_records=None)


async def log_pdf_download(
    quote_id: uuid.UUID,
    *,
    empresa_id: str,
    actor_email: Optional[str],
    actor_uid: Optional[str],
) -> None:
    pool = quote_db.get_pool()
    async with pool.acquire() as conn:
        await insert_quote_event(
            conn,
            {
                "id": uuid.uuid4(),
                "quote_id": quote_id,
                "empresa_id": empresa_id,
                "evento": QuoteEventType.PDF_DOWNLOADED.value,
                "descripcion": "PDF descargado",
                "metadata": None,
                "actor_uid": actor_uid,
                "actor_email": actor_email,
            },
        )


async def get_catalog_service(*, include_inactive: bool = False) -> List[CatalogCategoryOut]:
    pool = quote_db.get_pool()
    async with pool.acquire() as conn:
        rows = await fetch_catalog(conn, include_inactive=include_inactive)
    categories: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        catalog_id = str(row["catalog_id"])
        if catalog_id not in categories:
            categories[catalog_id] = {
                "id": catalog_id,
                "slug": row["slug"],
                "nombre": row["nombre"],
                "descripcion": row["descripcion"],
                "activo": row["activo"],
                "items": [],
            }
        if row["item_id"]:
            categories[catalog_id]["items"].append(
                CatalogItemOut(
                    id=str(row["item_id"]),
                    label=row["label"],
                    valor_uf=row["valor_uf"],
                    nota=row["nota"],
                    orden=row["orden"],
                    valid_from=row["valid_from"],
                    valid_to=row["valid_to"],
                    catalog_id=catalog_id,
                )
            )
    return [
        CatalogCategoryOut(
            id=data["id"],
            slug=data["slug"],
            nombre=data["nombre"],
            descripcion=data["descripcion"],
            activo=data["activo"],
            items=data["items"],
        )
        for data in categories.values()
    ]


async def upsert_catalog_service(
    *,
    slug: str,
    nombre: str,
    descripcion: Optional[str],
    activo: bool,
    items: List[CatalogItemUpsert],
    catalog_id: Optional[uuid.UUID] = None,
) -> CatalogCategoryOut:
    pool = quote_db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            catalog_uuid = await upsert_catalog_category(
                conn,
                catalog_id=catalog_id,
                slug=slug,
                nombre=nombre,
                descripcion=descripcion,
                activo=activo,
            )
            item_models: List[CatalogItemOut] = []
            for item in items:
                try:
                    existing_id = uuid.UUID(item.id) if item.id else None
                except ValueError as exc:
                    raise CatalogError("Identificador de item invalido") from exc
                stored_id = await upsert_catalog_item(
                    conn,
                    item_id=existing_id,
                    catalog_id=catalog_uuid,
                    label=item.label,
                    valor_uf=item.valor_uf,
                    nota=item.nota,
                    orden=item.orden,
                    valid_from=item.valid_from or date.today(),
                    valid_to=item.valid_to,
                )
                item_models.append(
                    CatalogItemOut(
                        id=str(stored_id),
                        label=item.label,
                        valor_uf=item.valor_uf,
                        nota=item.nota,
                        orden=item.orden,
                        valid_from=item.valid_from or date.today(),
                        valid_to=item.valid_to,
                        catalog_id=str(catalog_uuid),
                    )
                )
    return CatalogCategoryOut(
        id=str(catalog_uuid),
        slug=slug,
        nombre=nombre,
        descripcion=descripcion,
        activo=activo,
        items=item_models,
    )


async def delete_catalog_item_service(item_id: uuid.UUID) -> None:
    pool = quote_db.get_pool()
    async with pool.acquire() as conn:
        await delete_catalog_item(conn, item_id)


async def list_clients_service(
    empresa_id: str,
    *,
    query: Optional[str],
    limit: int = 10,
) -> List[ClientSummary]:
    pool = quote_db.get_pool()
    async with pool.acquire() as conn:
        rows = await fetch_clients(conn, empresa_id, query=query, limit=limit)
    return [
        ClientSummary(
            id=str(row["id"]),
            empresa_id=row["empresa_id"],
            nombre=row["nombre"],
            rut=row["rut"],
            contacto=row["contacto"],
            correo=row["correo"],
            telefono=row["telefono"],
            notas=row["notas"],
        )
        for row in rows
    ]


async def create_client_service(
    empresa_id: str,
    payload: ClientCreatePayload,
) -> ClientSummary:
    pool = quote_db.get_pool()
    async with pool.acquire() as conn:
        row = await insert_client(
            conn,
            empresa_id,
            {
                "nombre": payload.nombre,
                "rut": _normalize_rut(payload.rut),
                "contacto": payload.contacto,
                "correo": str(payload.correo) if payload.correo else None,
                "telefono": payload.telefono,
                "notas": payload.notas,
            },
        )
        if row is None:
            raise ClientExistsError("Ya existe un cliente con ese RUT")
    return ClientSummary(
        id=str(row["id"]),
        empresa_id=row["empresa_id"],
        nombre=row["nombre"],
        rut=row["rut"],
        contacto=row["contacto"],
        correo=row["correo"],
        telefono=row["telefono"],
        notas=row["notas"],
    )
