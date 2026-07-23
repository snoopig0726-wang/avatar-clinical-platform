from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AuthenticatedStaff, require_doctor, require_idempotency_key
from app.api.errors import ApiError
from app.config.settings import get_settings
from app.database import get_db_session
from app.domain.enums import (
    AuditActorType,
    AuthorizationStatus,
    CaseStatus,
    InviteStatus,
    RetentionStatus,
    SessionStatus,
)
from app.models.entities import (
    AdjustmentRequest,
    ClinicalCase,
    PatientSession,
    RetentionJob,
    SessionAvatarAuthorization,
    SessionInvite,
)
from app.schemas.cases import (
    ArchiveCaseRequest,
    CaseListResponse,
    CaseResponse,
    CreateCaseRequest,
)
from app.security.crypto import hash_secret
from app.services.core import add_audit, add_idempotency, find_idempotency, utc_now

router = APIRouter()
ACTIVE_SESSION_STATUSES = {
    SessionStatus.WAITING_DOCTOR,
    SessionStatus.ACTIVE,
    SessionStatus.PAUSED,
}


async def owned_case_or_404(
    session: AsyncSession,
    case_id: UUID,
    doctor_id: UUID,
    *,
    for_update: bool = False,
) -> ClinicalCase:
    statement = select(ClinicalCase).where(
            ClinicalCase.case_id == case_id,
            ClinicalCase.owner_doctor_id == doctor_id,
        )
    if for_update:
        statement = statement.with_for_update()
    case = await session.scalar(statement)
    if case is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "病例不存在或无权访问")
    return case


async def case_response(session: AsyncSession, case: ClinicalCase) -> CaseResponse:
    active_count = await session.scalar(
        select(func.count(PatientSession.session_id)).where(
            PatientSession.case_id == case.case_id,
            PatientSession.status.in_(ACTIVE_SESSION_STATUSES),
        )
    )
    return CaseResponse(
        case_id=case.case_id,
        study_code=case.study_code,
        status=case.status,
        created_at=case.created_at,
        updated_at=case.updated_at,
        archived_at=case.archived_at,
        retention_due_at=case.retention_due_at,
        active_session_count=active_count or 0,
    )


@router.get("", response_model=CaseListResponse)
async def list_cases(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: CaseStatus | None = None,
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> CaseListResponse:
    filters = [ClinicalCase.owner_doctor_id == staff.user.user_id]
    if status is not None:
        filters.append(ClinicalCase.status == status)
    total = await session.scalar(select(func.count(ClinicalCase.case_id)).where(*filters))
    cases = (
        await session.scalars(
            select(ClinicalCase)
            .where(*filters)
            .order_by(ClinicalCase.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return CaseListResponse(
        items=[await case_response(session, case) for case in cases],
        page=page,
        page_size=page_size,
        total=total or 0,
    )


@router.post("", response_model=CaseResponse, status_code=201)
async def create_case(
    payload: CreateCaseRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> CaseResponse:
    scope = f"doctor:{staff.user.user_id}"
    request_payload = payload.model_dump()
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="create_case",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing and existing.resource_id:
        case = await owned_case_or_404(session, existing.resource_id, staff.user.user_id)
        return await case_response(session, case)

    now = utc_now()
    case = ClinicalCase(
        owner_doctor_id=staff.user.user_id,
        study_code=payload.study_code.upper(),
        status=CaseStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    session.add(case)
    await session.flush()
    add_idempotency(
        session,
        actor_scope=scope,
        operation="create_case",
        key=idempotency_key,
        payload=request_payload,
        resource_id=case.case_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=case.case_id,
        action="case.created",
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(409, "STATE_CONFLICT", "该研究编号已存在") from exc
    return await case_response(session, case)


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: UUID,
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> CaseResponse:
    case = await owned_case_or_404(session, case_id, staff.user.user_id)
    return await case_response(session, case)


@router.post("/{case_id}/archive", response_model=CaseResponse)
async def archive_case(
    case_id: UUID,
    payload: ArchiveCaseRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> CaseResponse:
    case = await owned_case_or_404(
        session, case_id, staff.user.user_id, for_update=True
    )
    scope = f"doctor:{staff.user.user_id}:case:{case_id}"
    request_payload = payload.model_dump()
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="archive_case",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing:
        return await case_response(session, case)

    now = utc_now()
    if case.status != CaseStatus.ARCHIVED:
        case.status = CaseStatus.ARCHIVED
        case.archived_at = now
        if case.retention_started_at is None or case.retention_due_at is None:
            case.retention_started_at = now
            case.retention_due_at = now + timedelta(days=30)
        case.updated_at = now
        retention_job = await session.scalar(
            select(RetentionJob).where(RetentionJob.case_id == case_id)
        )
        if retention_job is None:
            retention_job = RetentionJob(
                case_id=case_id,
                case_reference_hash=hash_secret(
                    str(case_id), get_settings().secret_key, "retention-case-reference"
                ),
                retention_started_at=case.retention_started_at,
                retention_due_at=case.retention_due_at,
                status=RetentionStatus.SCHEDULED,
                attempt_count=0,
            )
            session.add(retention_job)
        sessions = (
            await session.scalars(
                select(PatientSession).where(
                    PatientSession.case_id == case_id,
                    PatientSession.status.in_(ACTIVE_SESSION_STATUSES),
                )
            )
        ).all()
        for patient_session in sessions:
            patient_session.status = SessionStatus.ENDED
            patient_session.ended_at = now
        invites = (
            await session.scalars(
                select(SessionInvite).where(
                    SessionInvite.case_id == case_id,
                    SessionInvite.status.in_(
                        {InviteStatus.ISSUED, InviteStatus.REDEEMED_WAITING, InviteStatus.ACTIVE}
                    ),
                )
            )
        ).all()
        for invite in invites:
            invite.status = InviteStatus.ENDED
        authorizations = (
            await session.scalars(
                select(SessionAvatarAuthorization)
                .join(
                    PatientSession,
                    PatientSession.session_id == SessionAvatarAuthorization.session_id,
                )
                .where(
                    PatientSession.case_id == case_id,
                    SessionAvatarAuthorization.status == AuthorizationStatus.AUTHORIZED,
                )
            )
        ).all()
        for authorization in authorizations:
            authorization.status = AuthorizationStatus.REVOKED
            authorization.revoked_at = now
            authorization.revoke_reason = "case_archived"
        adjustments = (
            await session.scalars(
                select(AdjustmentRequest).where(AdjustmentRequest.case_id == case_id)
            )
        ).all()
        for adjustment in adjustments:
            adjustment.expires_at = case.retention_due_at

    add_idempotency(
        session,
        actor_scope=scope,
        operation="archive_case",
        key=idempotency_key,
        payload=request_payload,
        resource_id=case_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=case_id,
        action="case.archived",
        metadata={"reason_present": bool(payload.reason)},
    )
    await session.commit()
    return await case_response(session, case)
