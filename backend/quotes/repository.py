from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

import asyncpg

from .enums import QuoteStatus
from .schemas import QuoteListFilters

_QUOTE_ITEMS_HAS_CATALOG_COLUMN: Optional[bool] = None


async def _quote_items_supports_catalog(conn: asyncpg.Connection) -> bool:
    global _QUOTE_ITEMS_HAS_CATALOG_COLUMN
    if _QUOTE_ITEMS_HAS_CATALOG_COLUMN is not None:
        return _QUOTE_ITEMS_HAS_CATALOG_COLUMN
    query = """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'quote_items'
          AND column_name = 'catalog_id'
          AND table_schema = ANY (current_schemas(FALSE))
        LIMIT 1
    """
    exists = await conn.fetchval(query)
    _QUOTE_ITEMS_HAS_CATALOG_COLUMN = bool(exists)
    return _QUOTE_ITEMS_HAS_CATALOG_COLUMN

def _build_filters(filters: QuoteListFilters, empresa_id: str) -> Tuple[str, List[Any]]:
    clauses = ["empresa_id = $1"]
    params: List[Any] = [empresa_id]
    placeholder = 2

    if filters.estados:
        clauses.append(f"estado = ANY(${placeholder})")
        params.append([status.value for status in filters.estados])
        placeholder += 1

    if filters.search:
        clauses.append(f"(cliente_nombre ILIKE ${placeholder} OR quote_number ILIKE ${placeholder})")
        params.append(f"%{filters.search}%")
        placeholder += 1

    if filters.cliente_rut:
        clauses.append(f"cliente_rut ILIKE ${placeholder}")
        params.append(f"%{filters.cliente_rut}%")
        placeholder += 1

    if filters.prepared_by:
        clauses.append(f"prepared_by ILIKE ${placeholder}")
        params.append(f"%{filters.prepared_by}%")
        placeholder += 1

    if filters.quote_number:
        clauses.append(f"quote_number ILIKE ${placeholder}")
        params.append(f"%{filters.quote_number}%")
        placeholder += 1

    if filters.created_from:
        clauses.append(f"created_at >= ${placeholder}")
        params.append(filters.created_from)
        placeholder += 1

    if filters.created_to:
        clauses.append(f"created_at <= ${placeholder}")
        params.append(filters.created_to)
        placeholder += 1

    where_clause = " AND ".join(clauses)
    return where_clause, params


async def fetch_quote(
    conn: asyncpg.Connection,
    quote_id: uuid.UUID,
    empresa_id: str,
    *,
    for_update: bool = False,
) -> Optional[asyncpg.Record]:
    sql = """
        SELECT *
        FROM quotes
        WHERE id = $1 AND empresa_id = $2
    """
    if for_update:
        sql += " FOR UPDATE"
    return await conn.fetchrow(sql, quote_id, empresa_id)


async def fetch_quote_items(conn: asyncpg.Connection, quote_id: uuid.UUID) -> List[asyncpg.Record]:
    has_catalog = await _quote_items_supports_catalog(conn)
    if has_catalog:
        sql = """
            SELECT qi.id,
                   qi.quote_id,
                   qi.descripcion,
                   qi.cantidad,
                   qi.precio_unitario_uf,
                   qi.total_uf,
                   qi.nota,
                   qi.orden,
                   qi.catalog_id,
                   c.slug AS catalog_slug
            FROM quote_items qi
            LEFT JOIN quote_catalog c ON c.id = qi.catalog_id
            WHERE qi.quote_id = $1
            ORDER BY qi.orden ASC, qi.id ASC
        """
    else:
        sql = """
            SELECT qi.id,
                   qi.quote_id,
                   qi.descripcion,
                   qi.cantidad,
                   qi.precio_unitario_uf,
                   qi.total_uf,
                   qi.nota,
                   qi.orden,
                   NULL::uuid AS catalog_id,
                   NULL::text AS catalog_slug
            FROM quote_items qi
            WHERE qi.quote_id = $1
            ORDER BY qi.orden ASC, qi.id ASC
        """
    return await conn.fetch(sql, quote_id)


async def fetch_quote_events(conn: asyncpg.Connection, quote_id: uuid.UUID) -> List[asyncpg.Record]:
    sql = """
        SELECT id, quote_id, evento, descripcion, metadata, created_at, actor_email
        FROM quote_events
        WHERE quote_id = $1
        ORDER BY created_at DESC
    """
    return await conn.fetch(sql, quote_id)


async def insert_quote(
    conn: asyncpg.Connection,
    data: Dict[str, Any],
) -> asyncpg.Record:
    columns = ", ".join(data.keys())
    placeholders = ", ".join(f"${idx}" for idx in range(1, len(data) + 1))
    sql = f"INSERT INTO quotes ({columns}) VALUES ({placeholders}) RETURNING *"
    return await conn.fetchrow(sql, *data.values())


async def update_quote(
    conn: asyncpg.Connection,
    quote_id: uuid.UUID,
    empresa_id: str,
    fields: Dict[str, Any],
) -> asyncpg.Record:
    assignments = ", ".join(f"{column} = ${idx}" for idx, column in enumerate(fields.keys(), start=1))
    sql = f"""
        UPDATE quotes
        SET {assignments}, updated_at = NOW()
        WHERE id = ${len(fields) + 1} AND empresa_id = ${len(fields) + 2}
        RETURNING *
    """
    params = list(fields.values()) + [quote_id, empresa_id]
    return await conn.fetchrow(sql, *params)


async def replace_quote_items(
    conn: asyncpg.Connection,
    quote_id: uuid.UUID,
    items: Sequence[Dict[str, Any]],
) -> None:
    has_catalog = await _quote_items_supports_catalog(conn)
    await conn.execute("DELETE FROM quote_items WHERE quote_id = $1", quote_id)
    if not items:
        return
    if has_catalog:
        sql = """
            INSERT INTO quote_items (
                id,
                quote_id,
                descripcion,
                cantidad,
                precio_unitario_uf,
                total_uf,
                nota,
                orden,
                catalog_id
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9
            )
        """
        params = [
            (
                item.get("id", uuid.uuid4()),
                quote_id,
                item["descripcion"],
                item["cantidad"],
                item["precio_unitario_uf"],
                item["total_uf"],
                item.get("nota"),
                item.get("orden", 0),
                item.get("catalog_id"),
            )
            for item in items
        ]
    else:
        sql = """
            INSERT INTO quote_items (
                id,
                quote_id,
                descripcion,
                cantidad,
                precio_unitario_uf,
                total_uf,
                nota,
                orden
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8
            )
        """
        params = [
            (
                item.get("id", uuid.uuid4()),
                quote_id,
                item["descripcion"],
                item["cantidad"],
                item["precio_unitario_uf"],
                item["total_uf"],
                item.get("nota"),
                item.get("orden", 0),
            )
            for item in items
        ]
    await conn.executemany(sql, params)


async def insert_quote_event(
    conn: asyncpg.Connection,
    data: Dict[str, Any],
) -> asyncpg.Record:
    sql = """
        INSERT INTO quote_events (
            id,
            quote_id,
            empresa_id,
            evento,
            descripcion,
            metadata,
            actor_uid,
            actor_email
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        RETURNING id, quote_id, evento, descripcion, metadata, created_at, actor_email
    """
    return await conn.fetchrow(
        sql,
        data["id"],
        data["quote_id"],
        data["empresa_id"],
        data["evento"],
        data.get("descripcion"),
        data.get("metadata"),
        data.get("actor_uid"),
        data.get("actor_email"),
    )


async def list_quotes(
    conn: asyncpg.Connection,
    empresa_id: str,
    filters: QuoteListFilters,
    *,
    limit: int,
    offset: int,
) -> Tuple[List[asyncpg.Record], int]:
    where_clause, params = _build_filters(filters, empresa_id)
    count_sql = f"SELECT COUNT(*) FROM quotes WHERE {where_clause}"
    total = await conn.fetchval(count_sql, *params)

    sql = f"""
        SELECT id, quote_number, estado, cliente_nombre, cliente_rut, total_uf, vigencia_hasta, created_at, updated_at
        FROM quotes
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ${len(params) + 1}
        OFFSET ${len(params) + 2}
    """
    rows = await conn.fetch(sql, *params, limit, offset)
    return rows, total


async def fetch_catalog(
    conn: asyncpg.Connection,
    *,
    include_inactive: bool = False,
) -> List[asyncpg.Record]:
    sql = """
        SELECT c.id AS catalog_id,
               c.slug,
               c.nombre,
               c.descripcion,
               c.activo,
               i.id AS item_id,
               i.label,
               i.valor_uf,
               i.nota,
               i.orden,
               i.valid_from,
               i.valid_to
        FROM quote_catalog c
        LEFT JOIN quote_catalog_items i ON i.catalog_id = c.id
        WHERE ($1 OR c.activo = TRUE)
        ORDER BY c.nombre ASC, i.orden ASC, i.id ASC
    """
    return await conn.fetch(sql, include_inactive)


async def upsert_catalog_category(
    conn: asyncpg.Connection,
    *,
    catalog_id: Optional[uuid.UUID],
    slug: str,
    nombre: str,
    descripcion: Optional[str],
    activo: bool,
) -> uuid.UUID:
    if catalog_id is None:
        catalog_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO quote_catalog (id, slug, nombre, descripcion, activo)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (slug) DO UPDATE
            SET nombre = EXCLUDED.nombre,
                descripcion = EXCLUDED.descripcion,
                activo = EXCLUDED.activo,
                updated_at = NOW()
            """,
            catalog_id,
            slug,
            nombre,
            descripcion,
            activo,
        )
    else:
        await conn.execute(
            """
            UPDATE quote_catalog
            SET slug = $2,
                nombre = $3,
                descripcion = $4,
                activo = $5,
                updated_at = NOW()
            WHERE id = $1
            """,
            catalog_id,
            slug,
            nombre,
            descripcion,
            activo,
        )
    return catalog_id


async def upsert_catalog_item(
    conn: asyncpg.Connection,
    *,
    item_id: Optional[uuid.UUID],
    catalog_id: uuid.UUID,
    label: str,
    valor_uf,
    nota: Optional[str],
    orden: int,
    valid_from,
    valid_to,
) -> uuid.UUID:
    if item_id is None:
        item_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO quote_catalog_items (
                id, catalog_id, label, valor_uf, nota, orden, valid_from, valid_to
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            """,
            item_id,
            catalog_id,
            label,
            valor_uf,
            nota,
            orden,
            valid_from,
            valid_to,
        )
    else:
        await conn.execute(
            """
            UPDATE quote_catalog_items
            SET label = $2,
                valor_uf = $3,
                nota = $4,
                orden = $5,
                valid_from = $6,
                valid_to = $7
            WHERE id = $1
            """,
            item_id,
            label,
            valor_uf,
            nota,
            orden,
            valid_from,
            valid_to,
        )
    return item_id


async def delete_catalog_item(conn: asyncpg.Connection, item_id: uuid.UUID) -> None:
    await conn.execute("DELETE FROM quote_catalog_items WHERE id = $1", item_id)


async def fetch_clients(
    conn: asyncpg.Connection,
    empresa_id: str,
    *,
    query: Optional[str],
    limit: int,
) -> List[asyncpg.Record]:
    sql = """
        SELECT id, empresa_id, nombre, rut, contacto, correo, telefono, notas
        FROM clients
        WHERE empresa_id = $1
          AND ($2::text IS NULL OR nombre ILIKE $2 OR rut ILIKE $2)
        ORDER BY nombre ASC
        LIMIT $3
    """
    search = f"%{query}%" if query else None
    return await conn.fetch(sql, empresa_id, search, limit)


async def insert_client(
    conn: asyncpg.Connection,
    empresa_id: str,
    payload: Dict[str, Any],
) -> asyncpg.Record:
    sql = """
        INSERT INTO clients (
            id, empresa_id, nombre, rut, contacto, correo, telefono, notas
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        ON CONFLICT (empresa_id, rut) DO NOTHING
        RETURNING id, empresa_id, nombre, rut, contacto, correo, telefono, notas
    """
    client_id = uuid.uuid4()
    return await conn.fetchrow(
        sql,
        client_id,
        empresa_id,
        payload["nombre"],
        payload["rut"],
        payload.get("contacto"),
        payload.get("correo"),
        payload.get("telefono"),
        payload.get("notas"),
    )


async def touch_quote_status(
    conn: asyncpg.Connection,
    quote_id: uuid.UUID,
    empresa_id: str,
    new_status: QuoteStatus,
    *,
    vigencia_hasta=None,
) -> asyncpg.Record:
    sql = """
        UPDATE quotes
        SET estado = $1,
            vigencia_hasta = COALESCE($2, vigencia_hasta),
            updated_at = NOW()
        WHERE id = $3 AND empresa_id = $4
        RETURNING *
    """
    return await conn.fetchrow(sql, new_status.value, vigencia_hasta, quote_id, empresa_id)
