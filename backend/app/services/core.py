from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.domain.enums import AuditActorType, AuditResult
from app.models.entities import AuditLog, IdempotencyRecord


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def is_expired(value: datetime) -> bool:
    return ensure_utc(value) <= utc_now()


def request_hash(payload: dict[str, Any]) -> bytes:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).digest()


async def find_idempotency(
    session: AsyncSession,
    *,
    actor_scope: str,
    operation: str,
    key: str,
    payload: dict[str, Any],
) -> IdempotencyRecord | None:
    record = await session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.actor_scope == actor_scope,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.key == key,
        )
    )
    if record is not None and record.request_hash != request_hash(payload):
        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "幂等键已用于不同请求")
    return record


def add_idempotency(
    session: AsyncSession,
    *,
    actor_scope: str,
    operation: str,
    key: str,
    payload: dict[str, Any],
    resource_id: UUID | None,
    response_snapshot: dict[str, Any] | None = None,
) -> None:
    now = utc_now()
    session.add(
        IdempotencyRecord(
            actor_scope=actor_scope,
            operation=operation,
            key=key,
            request_hash=request_hash(payload),
            resource_id=resource_id,
            response_snapshot=response_snapshot,
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )
    )


def add_audit(
    session: AsyncSession,
    *,
    actor_type: AuditActorType,
    action: str,
    result: AuditResult = AuditResult.SUCCESS,
    actor_user_id: UUID | None = None,
    case_id: UUID | None = None,
    invite_id: UUID | None = None,
    session_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            case_id=case_id,
            invite_id=invite_id,
            session_id=session_id,
            action=action,
            result=result,
            metadata_json=metadata,
            created_at=utc_now(),
        )
    )
