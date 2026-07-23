from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.config.settings import get_settings
from app.database import get_db_session
from app.domain.enums import ApprovalStatus, Role, SessionStatus
from app.models.entities import PatientSession, StaffAccessSession, StaffUser
from app.security.crypto import InvalidToken, decode_staff_token, hash_secret
from app.services.core import is_expired


@dataclass(frozen=True)
class AuthenticatedStaff:
    user: StaffUser
    access_session: StaffAccessSession


def require_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str:
    if not idempotency_key or len(idempotency_key) > 128:
        raise ApiError(400, "INVALID_REQUEST", "写操作必须提供有效的 Idempotency-Key")
    return idempotency_key


async def get_current_staff(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: AsyncSession = Depends(get_db_session),
) -> AuthenticatedStaff:
    return await authenticate_staff_token(authorization, session)


async def authenticate_staff_token(
    authorization: str | None,
    session: AsyncSession,
) -> AuthenticatedStaff:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(401, "UNAUTHENTICATED", "需要有效的工作人员凭证")
    settings = get_settings()
    try:
        payload = decode_staff_token(
            authorization.removeprefix("Bearer ").strip(), settings.secret_key
        )
        user_id = UUID(payload["sub"])
        access_session_id = UUID(payload["sid"])
        token_id = str(payload["jti"])
    except (InvalidToken, ValueError, KeyError) as exc:
        raise ApiError(401, "UNAUTHENTICATED", "需要有效的工作人员凭证") from exc

    access_session = await session.scalar(
        select(StaffAccessSession).where(
            StaffAccessSession.access_session_id == access_session_id,
            StaffAccessSession.user_id == user_id,
            StaffAccessSession.token_id_hash
            == hash_secret(token_id, settings.secret_key, "staff-token-id"),
        )
    )
    user = await session.get(StaffUser, user_id)
    if (
        access_session is None
        or access_session.revoked_at is not None
        or is_expired(access_session.expires_at)
        or user is None
        or not user.is_active
        or user.approval_status != ApprovalStatus.APPROVED
    ):
        raise ApiError(401, "UNAUTHENTICATED", "需要有效的工作人员凭证")
    return AuthenticatedStaff(user=user, access_session=access_session)


async def require_doctor(
    staff: AuthenticatedStaff = Depends(get_current_staff),
) -> AuthenticatedStaff:
    if staff.user.role != Role.DOCTOR:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "资源不存在或无权访问")
    return staff


async def require_admin(
    staff: AuthenticatedStaff = Depends(get_current_staff),
) -> AuthenticatedStaff:
    if staff.user.role != Role.ADMIN:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "资源不存在或无权访问")
    return staff


async def authenticate_patient_session(
    session_id: UUID,
    token: str | None,
    session: AsyncSession,
) -> PatientSession:
    if not token:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "会话不存在或无权访问")
    settings = get_settings()
    patient_session = await session.get(PatientSession, session_id)
    if (
        patient_session is None
        or patient_session.patient_session_token_hash
        != hash_secret(token, settings.secret_key, "patient-session-token")
        or patient_session.status in {SessionStatus.ENDED, SessionStatus.EXPIRED}
        or is_expired(patient_session.expires_at)
    ):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "会话不存在或无权访问")
    return patient_session
