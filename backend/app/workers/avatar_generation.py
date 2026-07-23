from __future__ import annotations

import asyncio
from uuid import UUID

from app.adapters.image_generation.providers import ImageGenerationError
from app.config.settings import get_settings
from app.database import get_session_factory
from app.models.entities import AvatarVersion
from app.services.avatar_generation import (
    mark_avatar_generation_failed,
    process_avatar_generation,
)
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, name="avatar.generate", max_retries=3)
def generate_avatar(self, version_id: str) -> dict[str, str]:
    async def run() -> dict[str, str]:
        settings = get_settings()
        async with get_session_factory(settings.database_url)() as session:
            version = await process_avatar_generation(session, UUID(version_id), settings)
            return {"version_id": version_id, "status": version.generation_status.value}

    try:
        return asyncio.run(run())
    except ImageGenerationError as exc:
        if exc.retryable and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** (self.request.retries + 1)) from exc

        async def mark_exhausted() -> None:
            settings = get_settings()
            async with get_session_factory(settings.database_url)() as session:
                version = await session.get(AvatarVersion, UUID(version_id))
                if version is not None:
                    await mark_avatar_generation_failed(
                        session, version, "PROVIDER_RETRY_EXHAUSTED"
                    )

        asyncio.run(mark_exhausted())
        return {"version_id": version_id, "status": "failed"}
