from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage import get_object_storage
from app.api.dependencies import (
    AuthenticatedStaff,
    authenticate_patient_session,
    require_doctor,
    require_idempotency_key,
)
from app.api.errors import ApiError
from app.api.routes.avatars import avatar_response, create_adjustment_generation
from app.api.routes.cases import owned_case_or_404
from app.config.settings import get_settings
from app.database import get_db_session
from app.domain.enums import (
    AdjustmentStatus,
    AuditActorType,
    AuditResult,
    AuthorizationStatus,
    SessionStatus,
)
from app.models.entities import (
    AdjustmentRequest,
    AvatarVersion,
    SessionAvatarAuthorization,
)
from app.schemas.adjustments import (
    DoctorAdjustmentListResponse,
    DoctorAdjustmentResponse,
    PatientAdjustmentListResponse,
    PatientAdjustmentResponse,
    PatientAvatarResponse,
    ReviewAdjustmentRequest,
    SubmitAdjustmentRequest,
    SubmitAdjustmentResponse,
)
from app.schemas.avatars import AvatarVersionResponse
from app.security.crypto import decrypt_sensitive_text, encrypt_sensitive_text
from app.security.rate_limit import PATIENT_ADJUSTMENT_POLICY, enforce_rate_limit
from app.services.adjustments import (
    ADJUSTMENT_LIMIT,
    CONTROLLED_ADJUSTMENT_OPTIONS,
    adjustment_usage,
    build_controlled_instruction,
)
from app.services.core import add_audit, add_idempotency, find_idempotency, utc_now
from app.services.risk_engine import (
    SERVICE_UNAVAILABLE_MESSAGE,
    RiskServiceUnavailable,
    evaluate_adjustment_text,
)

router = APIRouter()


async def active_avatar_authorization(
    session: AsyncSession, session_id: UUID
) -> tuple[SessionAvatarAuthorization, AvatarVersion] | None:
    row = (
        await session.execute(
            select(SessionAvatarAuthorization, AvatarVersion)
            .join(AvatarVersion, AvatarVersion.version_id == SessionAvatarAuthorization.version_id)
            .where(
                SessionAvatarAuthorization.session_id == session_id,
                SessionAvatarAuthorization.status == AuthorizationStatus.AUTHORIZED,
            )
            .order_by(SessionAvatarAuthorization.authorized_at.desc())
            .limit(1)
        )
    ).one_or_none()
    return row


def patient_adjustment_response(request: AdjustmentRequest) -> PatientAdjustmentResponse:
    return PatientAdjustmentResponse(
        request_id=request.request_id,
        sequence_no=request.sequence_no,
        status=request.doctor_status,
        submitted_at=request.submitted_at,
        reviewed_at=request.reviewed_at,
    )


def doctor_adjustment_response(request: AdjustmentRequest) -> DoctorAdjustmentResponse:
    settings = get_settings()
    controlled = (
        decrypt_sensitive_text(request.reviewed_instruction_encrypted, settings.secret_key)
        if request.reviewed_instruction_encrypted
        else None
    )
    return DoctorAdjustmentResponse(
        **patient_adjustment_response(request).model_dump(),
        instruction=decrypt_sensitive_text(request.submitted_text_encrypted, settings.secret_key),
        controlled_instruction=controlled,
    )


@router.get(
    "/patient-sessions/{session_id}/avatar",
    response_model=PatientAvatarResponse,
)
async def get_patient_avatar(
    session_id: UUID,
    patient_token: str | None = Header(default=None, alias="X-Session-Token"),
    session: AsyncSession = Depends(get_db_session),
) -> PatientAvatarResponse:
    patient_session = await authenticate_patient_session(session_id, patient_token, session)
    authorization = await active_avatar_authorization(session, session_id)
    if authorization is None:
        raise ApiError(409, "STATE_CONFLICT", "医生尚未授权当前 Avatar")
    _, version = authorization
    patient_session.last_seen_at = utc_now()
    await session.commit()
    if version.image_object_key and version.output_mime_type:
        return PatientAvatarResponse(
            version_id=version.version_id,
            display_mode="image",
            image_url=get_object_storage(get_settings()).get_url(
                version.image_object_key, version.output_mime_type
            ),
        )
    return PatientAvatarResponse(
        version_id=version.version_id,
        display_mode="mock_placeholder",
        message="当前授权版本没有图像文件，请联系现场医生。",
    )


@router.post(
    "/patient-sessions/{session_id}/adjustment-requests",
    response_model=SubmitAdjustmentResponse,
    status_code=201,
)
async def submit_adjustment(
    session_id: UUID,
    payload: SubmitAdjustmentRequest,
    http_request: Request,
    patient_token: str | None = Header(default=None, alias="X-Session-Token"),
    idempotency_key: str = Depends(require_idempotency_key),
    session: AsyncSession = Depends(get_db_session),
) -> SubmitAdjustmentResponse:
    patient_session = await authenticate_patient_session(session_id, patient_token, session)
    client_host = http_request.client.host if http_request.client else "unknown"
    await enforce_rate_limit(
        get_settings(),
        PATIENT_ADJUSTMENT_POLICY,
        f"{client_host}:{session_id}:{patient_token or ''}",
    )
    if patient_session.status != SessionStatus.ACTIVE:
        raise ApiError(409, "SESSION_INVALID", "会话已结束或暂时不可用。")
    if await active_avatar_authorization(session, session_id) is None:
        raise ApiError(409, "SESSION_INVALID", "会话已结束或暂时不可用。")

    scope = f"patient-session:{session_id}"
    request_payload = payload.model_dump()
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="submit_adjustment",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing and existing.resource_id:
        prior = await session.get(AdjustmentRequest, existing.resource_id)
        if prior is None:
            raise ApiError(409, "STATE_CONFLICT", "调整请求状态异常")
        usage = await adjustment_usage(session, patient_session.case_id)
        return SubmitAdjustmentResponse(
            **patient_adjustment_response(prior).model_dump(),
            used=usage.used,
        )

    try:
        risk = await evaluate_adjustment_text(session, payload.instruction)
    except RiskServiceUnavailable as exc:
        raise ApiError(503, "DEPENDENCY_UNAVAILABLE", SERVICE_UNAVAILABLE_MESSAGE) from exc
    if not risk.allowed:
        if risk.patient_message_type == "crisis":
            patient_session.status = SessionStatus.PAUSED
            patient_session.paused_at = utc_now()
            add_audit(
                session,
                actor_type=AuditActorType.SYSTEM,
                case_id=patient_session.case_id,
                invite_id=patient_session.invite_id,
                session_id=session_id,
                action="session.safety_paused",
                result=AuditResult.BLOCKED,
                metadata={"source": "risk_interception", "risk_rule_version": risk.rule_version},
            )
        add_audit(
            session,
            actor_type=AuditActorType.PATIENT,
            case_id=patient_session.case_id,
            invite_id=patient_session.invite_id,
            session_id=session_id,
            action="adjustment.risk_blocked",
            result=AuditResult.BLOCKED,
            metadata={
                "risk_rule_version": risk.rule_version,
                "rule_codes": list(risk.matched_rule_codes),
            },
        )
        await session.commit()
        raise ApiError(422, "RISK_BLOCKED", risk.patient_message)

    await owned_case_or_404(
        session,
        patient_session.case_id,
        patient_session.supervising_doctor_id,
        for_update=True,
    )
    usage = await adjustment_usage(session, patient_session.case_id)
    if usage.used >= ADJUSTMENT_LIMIT:
        raise ApiError(409, "ADJUSTMENT_LIMIT_REACHED", "本病例的三次调整额度已用完")
    if usage.has_pending:
        raise ApiError(409, "STATE_CONFLICT", "已有调整请求等待医生处理")

    now = utc_now()
    request = AdjustmentRequest(
        case_id=patient_session.case_id,
        session_id=session_id,
        sequence_no=usage.used + 1,
        submitted_text_encrypted=encrypt_sensitive_text(
            payload.instruction, get_settings().secret_key
        ),
        risk_status="passed",
        risk_rule_version=risk.rule_version,
        doctor_status=AdjustmentStatus.PENDING_DOCTOR_REVIEW,
        submitted_at=now,
    )
    session.add(request)
    await session.flush()
    add_idempotency(
        session,
        actor_scope=scope,
        operation="submit_adjustment",
        key=idempotency_key,
        payload=request_payload,
        resource_id=request.request_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.PATIENT,
        case_id=patient_session.case_id,
        invite_id=patient_session.invite_id,
        session_id=session_id,
        action="adjustment.submitted",
        metadata={"sequence_no": request.sequence_no, "risk_rule_version": risk.rule_version},
    )
    await session.commit()
    return SubmitAdjustmentResponse(
        **patient_adjustment_response(request).model_dump(),
        used=usage.used + 1,
    )


@router.get(
    "/patient-sessions/{session_id}/adjustment-requests",
    response_model=PatientAdjustmentListResponse,
)
async def list_patient_adjustments(
    session_id: UUID,
    patient_token: str | None = Header(default=None, alias="X-Session-Token"),
    session: AsyncSession = Depends(get_db_session),
) -> PatientAdjustmentListResponse:
    patient_session = await authenticate_patient_session(session_id, patient_token, session)
    requests = (
        await session.scalars(
            select(AdjustmentRequest)
            .where(AdjustmentRequest.session_id == session_id)
            .order_by(AdjustmentRequest.sequence_no)
        )
    ).all()
    usage = await adjustment_usage(session, patient_session.case_id)
    return PatientAdjustmentListResponse(
        items=[patient_adjustment_response(item) for item in requests],
        **usage.model_dump(),
    )


@router.get(
    "/cases/{case_id}/adjustment-requests",
    response_model=DoctorAdjustmentListResponse,
)
async def list_doctor_adjustments(
    case_id: UUID,
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> DoctorAdjustmentListResponse:
    await owned_case_or_404(session, case_id, staff.user.user_id)
    requests = (
        await session.scalars(
            select(AdjustmentRequest)
            .where(AdjustmentRequest.case_id == case_id)
            .order_by(AdjustmentRequest.sequence_no)
        )
    ).all()
    usage = await adjustment_usage(session, case_id)
    return DoctorAdjustmentListResponse(
        items=[doctor_adjustment_response(item) for item in requests],
        controlled_options=CONTROLLED_ADJUSTMENT_OPTIONS,
        **usage.model_dump(),
    )


@router.post(
    "/adjustment-requests/{request_id}/review",
    response_model=DoctorAdjustmentResponse,
)
async def review_adjustment(
    request_id: UUID,
    payload: ReviewAdjustmentRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> DoctorAdjustmentResponse:
    request = await session.get(AdjustmentRequest, request_id)
    if request is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "调整请求不存在或无权访问")
    await owned_case_or_404(
        session, request.case_id, staff.user.user_id, for_update=True
    )
    scope = f"doctor:{staff.user.user_id}:adjustment:{request_id}"
    request_payload = payload.model_dump()
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="review_adjustment",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing:
        return doctor_adjustment_response(request)
    if request.doctor_status != AdjustmentStatus.PENDING_DOCTOR_REVIEW:
        raise ApiError(409, "STATE_CONFLICT", "该调整请求已处理")

    controlled: str | None = None
    if payload.decision == "approve_as_is":
        raw = decrypt_sensitive_text(request.submitted_text_encrypted, get_settings().secret_key)
        controlled = build_controlled_instruction(raw)
        request.doctor_status = AdjustmentStatus.APPROVED_AS_IS
    elif payload.decision == "approve_edited":
        if payload.controlled_instruction not in CONTROLLED_ADJUSTMENT_OPTIONS:
            raise ApiError(422, "VALIDATION_ERROR", "请选择系统提供的受控调整指令")
        controlled = payload.controlled_instruction
        request.doctor_status = AdjustmentStatus.APPROVED_EDITED
    else:
        request.doctor_status = AdjustmentStatus.REJECTED

    now = utc_now()
    request.reviewed_at = now
    request.reviewed_by = staff.user.user_id
    if controlled:
        request.reviewed_instruction_encrypted = encrypt_sensitive_text(
            controlled, get_settings().secret_key
        )
    add_idempotency(
        session,
        actor_scope=scope,
        operation="review_adjustment",
        key=idempotency_key,
        payload=request_payload,
        resource_id=request_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=request.case_id,
        session_id=request.session_id,
        action="adjustment.reviewed",
        metadata={"decision": payload.decision, "sequence_no": request.sequence_no},
    )
    await session.commit()
    return doctor_adjustment_response(request)


@router.post(
    "/adjustment-requests/{request_id}/generate",
    response_model=AvatarVersionResponse,
    status_code=202,
)
async def generate_adjustment(
    request_id: UUID,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> AvatarVersionResponse:
    request = await session.get(AdjustmentRequest, request_id)
    if request is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "调整请求不存在或无权访问")
    await owned_case_or_404(
        session, request.case_id, staff.user.user_id, for_update=True
    )
    if request.doctor_status not in {
        AdjustmentStatus.APPROVED_AS_IS,
        AdjustmentStatus.APPROVED_EDITED,
    }:
        raise ApiError(409, "STATE_CONFLICT", "调整请求尚未通过医生审核")
    scope = f"doctor:{staff.user.user_id}:adjustment:{request_id}"
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="generate_adjustment",
        key=idempotency_key,
        payload={},
    )
    if existing and existing.resource_id:
        version = await session.get(AvatarVersion, existing.resource_id)
        if version is None:
            raise ApiError(409, "STATE_CONFLICT", "生图版本已不可用")
        return avatar_response(version)
    version = await create_adjustment_generation(request, session)
    add_idempotency(
        session,
        actor_scope=scope,
        operation="generate_adjustment",
        key=idempotency_key,
        payload={},
        resource_id=version.version_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=request.case_id,
        session_id=request.session_id,
        action="avatar.adjustment_generation_requested",
        metadata={"sequence_no": request.sequence_no},
    )
    await session.commit()
    return avatar_response(version)
