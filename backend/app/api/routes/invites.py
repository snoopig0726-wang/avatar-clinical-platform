from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AuthenticatedStaff, require_doctor, require_idempotency_key
from app.api.errors import ApiError
from app.api.routes.cases import owned_case_or_404
from app.config.settings import get_settings
from app.database import get_db_session
from app.domain.enums import (
    AuditActorType,
    CaseStatus,
    InviteStatus,
    SessionStatus,
)
from app.models.entities import PatientSession, SessionInvite
from app.schemas.sessions import (
    CreateInviteRequest,
    InviteListResponse,
    InviteResponse,
    RedeemInviteRequest,
    RedeemInviteResponse,
)
from app.security.crypto import (
    derive_invite_code,
    derive_patient_token,
    hash_secret,
    normalize_invite_code,
)
from app.security.rate_limit import INVITE_REDEMPTION_POLICY, enforce_rate_limit
from app.services.core import add_audit, add_idempotency, find_idempotency, is_expired, utc_now

router = APIRouter()


def invite_response(
    invite: SessionInvite,
    *,
    include_code: bool = False,
    session_id: UUID | None = None,
) -> InviteResponse:
    settings = get_settings()
    return InviteResponse(
        invite_id=invite.invite_id,
        session_id=session_id,
        code=derive_invite_code(invite.invite_id, settings.secret_key) if include_code else None,
        code_mask=invite.code_mask,
        status=invite.status,
        created_at=invite.created_at,
        expires_at=invite.expires_at,
    )


@router.post("/cases/{case_id}/session-invites", response_model=InviteResponse, status_code=201)
async def create_invite(
    case_id: UUID,
    payload: CreateInviteRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> InviteResponse:
    case = await owned_case_or_404(
        session, case_id, staff.user.user_id, for_update=True
    )
    if case.status == CaseStatus.ARCHIVED:
        raise ApiError(409, "STATE_CONFLICT", "归档病例不能创建邀请码")
    scope = f"doctor:{staff.user.user_id}:case:{case_id}"
    request_payload = payload.model_dump()
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="create_invite",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing and existing.resource_id:
        invite = await session.get(SessionInvite, existing.resource_id)
        if invite is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "邀请码不存在")
        patient_session = await session.scalar(
            select(PatientSession).where(PatientSession.invite_id == invite.invite_id)
        )
        return invite_response(
            invite,
            include_code=invite.status == InviteStatus.ISSUED,
            session_id=patient_session.session_id if patient_session else None,
        )

    settings = get_settings()
    now = utc_now()
    invite_id = uuid4()
    code = derive_invite_code(invite_id, settings.secret_key)
    invite = SessionInvite(
        invite_id=invite_id,
        case_id=case_id,
        issuing_doctor_id=staff.user.user_id,
        code_hash=hash_secret(
            normalize_invite_code(code), settings.secret_key, "session-invite-code"
        ),
        code_mask=f"****-{code[-4:]}",
        status=InviteStatus.ISSUED,
        created_at=now,
        expires_at=now + timedelta(hours=payload.expires_in_hours),
    )
    session.add(invite)
    # PostgreSQL enforces the audit foreign key during the same flush. Persist
    # the invite first so the audit row cannot be ordered ahead of its parent.
    await session.flush()
    add_idempotency(
        session,
        actor_scope=scope,
        operation="create_invite",
        key=idempotency_key,
        payload=request_payload,
        resource_id=invite_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=case_id,
        invite_id=invite_id,
        action="invite.created",
    )
    await session.commit()
    return invite_response(invite, include_code=True)


@router.get("/cases/{case_id}/session-invites", response_model=InviteListResponse)
async def list_invites(
    case_id: UUID,
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> InviteListResponse:
    await owned_case_or_404(session, case_id, staff.user.user_id)
    invites = (
        await session.scalars(
            select(SessionInvite)
            .where(SessionInvite.case_id == case_id)
            .order_by(SessionInvite.created_at.desc())
        )
    ).all()
    changed = False
    for invite in invites:
        if invite.status == InviteStatus.ISSUED and is_expired(invite.expires_at):
            invite.status = InviteStatus.EXPIRED
            changed = True
    if changed:
        await session.commit()
    session_rows = (
        await session.scalars(select(PatientSession).where(PatientSession.case_id == case_id))
    ).all()
    session_ids = {row.invite_id: row.session_id for row in session_rows}
    return InviteListResponse(
        items=[
            invite_response(
                invite,
                include_code=invite.status == InviteStatus.ISSUED,
                session_id=session_ids.get(invite.invite_id),
            )
            for invite in invites
        ]
    )


@router.delete("/session-invites/{invite_id}", response_model=InviteResponse)
async def revoke_invite(
    invite_id: UUID,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> InviteResponse:
    invite = await session.scalar(
        select(SessionInvite)
        .join(SessionInvite.case)
        .where(
            SessionInvite.invite_id == invite_id,
            SessionInvite.issuing_doctor_id == staff.user.user_id,
        )
    )
    if invite is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "邀请码不存在或无权访问")
    scope = f"doctor:{staff.user.user_id}:invite:{invite_id}"
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="revoke_invite",
        key=idempotency_key,
        payload={},
    )
    if existing:
        return invite_response(invite)
    if invite.status != InviteStatus.ISSUED:
        raise ApiError(409, "STATE_CONFLICT", "当前邀请码状态不能撤销")
    invite.status = InviteStatus.REVOKED
    invite.revoked_at = utc_now()
    add_idempotency(
        session,
        actor_scope=scope,
        operation="revoke_invite",
        key=idempotency_key,
        payload={},
        resource_id=invite_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=invite.case_id,
        invite_id=invite_id,
        action="invite.revoked",
    )
    await session.commit()
    return invite_response(invite)


@router.post("/session-invites/redeem", response_model=RedeemInviteResponse)
async def redeem_invite(
    payload: RedeemInviteRequest,
    request: Request,
    idempotency_key: str = Depends(require_idempotency_key),
    session: AsyncSession = Depends(get_db_session),
) -> RedeemInviteResponse:
    settings = get_settings()
    normalized_code = normalize_invite_code(payload.code)
    client_host = request.client.host if request.client else "unknown"
    await enforce_rate_limit(
        settings,
        INVITE_REDEMPTION_POLICY,
        f"{client_host}:{normalized_code}",
    )
    device_hash = hash_secret(payload.device_binding, settings.secret_key, "device-binding")
    scope = f"patient-device:{device_hash.hex()}"
    request_payload = {
        "code_hash": hash_secret(normalized_code, settings.secret_key, "request").hex()
    }
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="redeem_invite",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing and existing.resource_id:
        patient_session = await session.get(PatientSession, existing.resource_id)
        if patient_session is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "邀请码无效、过期或已使用")
        return RedeemInviteResponse(
            session_id=patient_session.session_id,
            patient_session_token=derive_patient_token(
                patient_session.session_id, settings.secret_key
            ),
            status=patient_session.status,
            expires_at=patient_session.expires_at,
        )

    code_hash = hash_secret(normalized_code, settings.secret_key, "session-invite-code")
    invite = await session.scalar(select(SessionInvite).where(SessionInvite.code_hash == code_hash))
    now = utc_now()
    if invite is None or invite.status != InviteStatus.ISSUED or is_expired(invite.expires_at):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "邀请码无效、过期或已使用")
    case = await owned_case_or_404(
        session,
        invite.case_id,
        invite.issuing_doctor_id,
        for_update=True,
    )
    invite = await session.scalar(
        select(SessionInvite)
        .where(SessionInvite.invite_id == invite.invite_id)
        .with_for_update()
    )
    if invite is None or invite.status != InviteStatus.ISSUED or is_expired(invite.expires_at):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "邀请码无效、过期或已使用")
    if case.status == CaseStatus.ARCHIVED:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "邀请码无效、过期或已使用")

    session_id = uuid4()
    patient_token = derive_patient_token(session_id, settings.secret_key)
    invite_expiry = invite.expires_at
    if invite_expiry.tzinfo is None:
        invite_expiry = invite_expiry.replace(tzinfo=now.tzinfo)
    expires_at = min(invite_expiry, now + timedelta(hours=settings.session_ttl_hours))
    patient_session = PatientSession(
        session_id=session_id,
        case_id=invite.case_id,
        invite_id=invite.invite_id,
        supervising_doctor_id=invite.issuing_doctor_id,
        device_binding_hash=device_hash,
        patient_session_token_hash=hash_secret(
            patient_token, settings.secret_key, "patient-session-token"
        ),
        status=SessionStatus.WAITING_DOCTOR,
        created_at=now,
        expires_at=expires_at,
        last_seen_at=now,
    )
    session.add(patient_session)
    invite.status = InviteStatus.REDEEMED_WAITING
    invite.redeemed_at = now
    # Persist the new session before inserting audit/idempotency rows that
    # reference it. PostgreSQL does not defer these foreign-key checks.
    await session.flush()
    add_idempotency(
        session,
        actor_scope=scope,
        operation="redeem_invite",
        key=idempotency_key,
        payload=request_payload,
        resource_id=session_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.PATIENT,
        case_id=invite.case_id,
        invite_id=invite.invite_id,
        session_id=session_id,
        action="invite.redeemed",
    )
    await session.commit()
    return RedeemInviteResponse(
        session_id=session_id,
        patient_session_token=patient_token,
        status=patient_session.status,
        expires_at=expires_at,
    )
