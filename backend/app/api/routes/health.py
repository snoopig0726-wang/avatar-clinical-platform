import asyncio

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.adapters.storage import get_object_storage
from app.config.settings import get_settings
from app.database import get_db_session
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter()


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.app_env,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(
    session: AsyncSession = Depends(get_db_session),
) -> ReadinessResponse:
    settings = get_settings()
    dependencies: dict[str, str] = {}
    try:
        await session.execute(text("SELECT 1"))
        dependencies["database"] = "ok"
    except Exception:
        dependencies["database"] = "unavailable"

    redis_client = Redis.from_url(settings.redis_url, socket_connect_timeout=2)
    try:
        dependencies["redis"] = "ok" if await redis_client.ping() else "unavailable"
    except Exception:
        dependencies["redis"] = "unavailable"
    finally:
        await redis_client.aclose()

    try:
        await asyncio.to_thread(get_object_storage, settings)
        dependencies["object_storage"] = "ok"
    except Exception:
        dependencies["object_storage"] = "unavailable"

    if settings.model_provider == "mock":
        dependencies["image_provider"] = "mock"
    elif settings.model_provider == "openai" and settings.model_api_key:
        dependencies["image_provider"] = "configured"
    else:
        dependencies["image_provider"] = "credentials_missing"

    if settings.semantic_image_safety_provider == "mock":
        dependencies["semantic_image_safety"] = "mock"
    elif (
        settings.semantic_image_safety_provider == "openai"
        and settings.semantic_image_safety_api_key
    ):
        dependencies["semantic_image_safety"] = "configured"
    else:
        dependencies["semantic_image_safety"] = "credentials_missing"

    infrastructure_ready = all(
        dependencies[name] == "ok" for name in ("database", "redis", "object_storage")
    )
    provider_ready = dependencies["image_provider"] in {"mock", "configured"}
    semantic_safety_ready = dependencies["semantic_image_safety"] in {
        "mock",
        "configured",
    }
    return ReadinessResponse(
        status=(
            "ready"
            if infrastructure_ready and provider_ready and semantic_safety_ready
            else "degraded"
        ),
        dependencies=dependencies,
    )
