from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    AuthenticatedStaff,
    authenticate_patient_session,
    authenticate_staff_token,
    require_doctor,
    require_idempotency_key,
)
from app.api.errors import ApiError
from app.database import get_db_session
from app.domain.enums import (
    AuditActorType,
    CaseStatus,
    InviteStatus,
    Role,
    SessionStatus,
)
from app.domain.transitions import SESSION_TRANSITIONS, InvalidStateTransition, assert_transition
from app.models.entities import ClinicalCase, PatientSession, SessionInvite
from app.schemas.sessions import (
    AdjustmentUsage,
    SessionControlRequest,
    SessionResponse,
    StartSessionRequest,
)
from app.services.core import add_audit, add_idempotency, find_idempotency, utc_now

router = APIRouter()


def stage_for_status(status: SessionStatus) -> str:
    return {
        SessionStatus.WAITING_DOCTOR: "waiting_doctor_start",
        SessionStatus.ACTIVE: "voice_interview",
        SessionStatus.PAUSED: "safety_paused",
        SessionStatus.ENDED: "ended",
        SessionStatus.EXPIRED: "expired",
    }[status]


def session_response(
    patient_session: PatientSession, *, study_code: str | None = None
) -> SessionResponse:
    return SessionResponse(
        session_id=patient_session.session_id,
        case_id=patient_session.case_id,
        study_code=study_code,
        status=patient_session.status,
        stage=stage_for_status(patient_session.status),
        adjustments=AdjustmentUsage(),
        created_at=patient_session.created_at,
        started_at=patient_session.started_at,
        paused_at=patient_session.paused_at,
        ended_at=patient_session.ended_at,
        expires_at=patient_session.expires_at,
    )


async def doctor_session_or_404(
    session: AsyncSession, session_id: UUID, doctor_id: UUID
) -> PatientSession:
    patient_session = await session.get(PatientSession, session_id)
    if patient_session is None or patient_session.supervising_doctor_id != doctor_id:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "会话不存在或无权访问")
    return patient_session


def ensure_transition(current: SessionStatus, target: SessionStatus) -> None:
    try:
        assert_transition(current, target, SESSION_TRANSITIONS)
    except InvalidStateTransition as exc:
        raise ApiError(409, "STATE_CONFLICT", "当前会话状态不允许此操作") from exc


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: UUID,
    authorization: str | None = Header(default=None, alias="Authorization"),
    patient_token: str | None = Header(default=None, alias="X-Session-Token"),
    session: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    if authorization:
        staff = await authenticate_staff_token(authorization, session)
        if staff.user.role != Role.DOCTOR:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "会话不存在或无权访问")
        patient_session = await doctor_session_or_404(session, session_id, staff.user.user_id)
        case = await session.get(ClinicalCase, patient_session.case_id)
        return session_response(patient_session, study_code=case.study_code if case else None)
    patient_session = await authenticate_patient_session(session_id, patient_token, session)
    patient_session.last_seen_at = utc_now()
    await session.commit()
    return session_response(patient_session)


@router.post("/sessions/{session_id}/start", response_model=SessionResponse)
async def start_session(
    session_id: UUID,
    payload: StartSessionRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    patient_session = await doctor_session_or_404(session, session_id, staff.user.user_id)
    scope = f"doctor:{staff.user.user_id}:session:{session_id}"
    request_payload = payload.model_dump()
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="start_session",
        key=idempotency_key,
        payload=request_payload,
    )
    case = await session.get(ClinicalCase, patient_session.case_id)
    if existing:
        return session_response(patient_session, study_code=case.study_code if case else None)
    if not payload.consent_confirmed:
        raise ApiError(422, "VALIDATION_ERROR", "医生必须确认已完成当面知情同意")
    ensure_transition(patient_session.status, SessionStatus.ACTIVE)
    if case is None or case.status == CaseStatus.ARCHIVED:
        raise ApiError(409, "STATE_CONFLICT", "当前病例不能启动会话")
    now = utc_now()
    patient_session.status = SessionStatus.ACTIVE
    patient_session.started_at = now
    patient_session.consent_confirmed_by = staff.user.user_id
    patient_session.consent_confirmed_at = now
    patient_session.consent_version = payload.consent_version
    invite = await session.get(SessionInvite, patient_session.invite_id)
    if invite:
        invite.status = InviteStatus.ACTIVE
    if case.status == CaseStatus.DRAFT:
        case.status = CaseStatus.IN_PROGRESS
        case.updated_at = now
    add_idempotency(
        session,
        actor_scope=scope,
        operation="start_session",
        key=idempotency_key,
        payload=request_payload,
        resource_id=session_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=patient_session.case_id,
        invite_id=patient_session.invite_id,
        session_id=session_id,
        action="session.started",
        metadata={"consent_version": payload.consent_version},
    )
    await session.commit()
    return session_response(patient_session, study_code=case.study_code)


@router.post("/patient-sessions/{session_id}/pause", response_model=SessionResponse)
async def pause_session(
    session_id: UUID,
    payload: SessionControlRequest,
    patient_token: str | None = Header(default=None, alias="X-Session-Token"),
    idempotency_key: str = Depends(require_idempotency_key),
    session: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    patient_session = await authenticate_patient_session(session_id, patient_token, session)
    scope = f"patient-session:{session_id}"
    request_payload = {"reason_present": bool(payload.reason)}
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="pause_session",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing:
        return session_response(patient_session)
    ensure_transition(patient_session.status, SessionStatus.PAUSED)
    patient_session.status = SessionStatus.PAUSED
    patient_session.paused_at = utc_now()
    add_idempotency(
        session,
        actor_scope=scope,
        operation="pause_session",
        key=idempotency_key,
        payload=request_payload,
        resource_id=session_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.PATIENT,
        case_id=patient_session.case_id,
        invite_id=patient_session.invite_id,
        session_id=session_id,
        action="session.safety_paused",
        metadata={"reason_present": bool(payload.reason)},
    )
    await session.commit()
    return session_response(patient_session)


@router.post("/sessions/{session_id}/resume", response_model=SessionResponse)
async def resume_session(
    session_id: UUID,
    payload: SessionControlRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    patient_session = await doctor_session_or_404(session, session_id, staff.user.user_id)
    scope = f"doctor:{staff.user.user_id}:session:{session_id}"
    request_payload = {"reason_present": bool(payload.reason)}
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="resume_session",
        key=idempotency_key,
        payload=request_payload,
    )
    case = await session.get(ClinicalCase, patient_session.case_id)
    if existing:
        return session_response(patient_session, study_code=case.study_code if case else None)
    ensure_transition(patient_session.status, SessionStatus.ACTIVE)
    patient_session.status = SessionStatus.ACTIVE
    add_idempotency(
        session,
        actor_scope=scope,
        operation="resume_session",
        key=idempotency_key,
        payload=request_payload,
        resource_id=session_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=patient_session.case_id,
        invite_id=patient_session.invite_id,
        session_id=session_id,
        action="session.resumed",
    )
    await session.commit()
    return session_response(patient_session, study_code=case.study_code if case else None)


@router.post("/sessions/{session_id}/stop", response_model=SessionResponse)
async def stop_session(
    session_id: UUID,
    payload: SessionControlRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    patient_session = await doctor_session_or_404(session, session_id, staff.user.user_id)
    scope = f"doctor:{staff.user.user_id}:session:{session_id}"
    request_payload = {"reason_present": bool(payload.reason)}
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="stop_session",
        key=idempotency_key,
        payload=request_payload,
    )
    case = await session.get(ClinicalCase, patient_session.case_id)
    if existing:
        return session_response(patient_session, study_code=case.study_code if case else None)
    ensure_transition(patient_session.status, SessionStatus.ENDED)
    now = utc_now()
    patient_session.status = SessionStatus.ENDED
    patient_session.ended_at = now
    invite = await session.get(SessionInvite, patient_session.invite_id)
    if invite:
        invite.status = InviteStatus.ENDED
    add_idempotency(
        session,
        actor_scope=scope,
        operation="stop_session",
        key=idempotency_key,
        payload=request_payload,
        resource_id=session_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=patient_session.case_id,
        invite_id=patient_session.invite_id,
        session_id=session_id,
        action="session.ended",
        metadata={"reason_present": bool(payload.reason)},
    )
    await session.commit()
    return session_response(patient_session, study_code=case.study_code if case else None)
