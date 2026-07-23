from __future__ import annotations

import asyncio

from app.adapters.storage import get_object_storage
from app.config.settings import get_settings
from app.database import get_session_factory
from app.services.retention import process_due_retention_jobs
from app.workers.celery_app import celery_app


@celery_app.task(name="retention.process_due_cases")
def process_due_cases() -> dict[str, int]:
    async def run() -> dict[str, int]:
        settings = get_settings()
        storage = get_object_storage(settings)

        async def cleanup(case_id):
            count = await asyncio.to_thread(storage.delete_prefix, f"cases/{case_id}")
            return {"object_files": count, "backup_records": 0}

        async with get_session_factory(settings.database_url)() as session:
            return await process_due_retention_jobs(session, object_cleanup=cleanup)

    return asyncio.run(run())
