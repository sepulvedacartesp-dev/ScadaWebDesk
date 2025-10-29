from __future__ import annotations

import asyncpg

from typing import Optional

quote_db_pool: Optional[asyncpg.pool.Pool] = None


async def init_pool(
    database_url: str,
    *,
    min_size: int = 1,
    max_size: int = 5,
    timeout: int = 10,
) -> Optional[asyncpg.pool.Pool]:
    """Inicializa el pool dedicado al cotizador."""
    global quote_db_pool
    if not database_url:
        quote_db_pool = None
        return None
    quote_db_pool = await asyncpg.create_pool(
        database_url,
        min_size=min_size,
        max_size=max_size,
        timeout=timeout,
    )
    return quote_db_pool


async def close_pool() -> None:
    """Cierra el pool dedicado al cotizador si existe."""
    global quote_db_pool
    pool = quote_db_pool
    if pool is not None:
        try:
            await pool.close()
        finally:
            quote_db_pool = None


def get_pool() -> asyncpg.pool.Pool:
    if quote_db_pool is None:
        raise RuntimeError("quote_db_pool no inicializado")
    return quote_db_pool
