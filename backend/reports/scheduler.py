from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import asyncpg

from . import service as report_service
from .runner import spawn_background

CHECK_INTERVAL_SECONDS = 60
SCHEDULER_ENABLED_ENV = "REPORTS_SCHEDULER_ENABLED"


async def process_due_reports(pool: asyncpg.pool.Pool) -> int:
    now = datetime.now(timezone.utc)
    due = await report_service.list_due_definitions(pool, now)
    processed = 0
    for definition in due:
        try:
            run = await report_service.create_run(
                pool,
                definition.empresa_id,
                definition.id,
                definition,
                None,
                "scheduler",
            )
            next_run = report_service.compute_next_run_at(definition, now)
            await report_service.update_next_run(pool, definition.empresa_id, definition.id, next_run)
            spawn_background(pool, run.id)
            processed += 1
        except Exception:
            continue
    return processed


async def scheduler_loop(get_pool_callable) -> None:
    while True:
        try:
            pool: Optional[asyncpg.pool.Pool] = get_pool_callable()
            if pool:
                await process_due_reports(pool)
        except Exception:
            pass
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
