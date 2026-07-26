from __future__ import annotations

import asyncio
import io
import json
import zipfile
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage import get_object_storage
from app.api.dependencies import AuthenticatedStaff, require_doctor, require_idempotency_key
from app.api.errors import ApiError
from app.api.routes.cases import owned_case_or_404
from app.config.settings import get_settings
from app.database import get_db_session
from app.domain.enums import (
    AdjustmentStatus,
    AuditActorType,
    AuthorizationStatus,
    GenerationMode,
    GenerationStatus,
    SessionStatus,
)
from app.models.entities import (
    AdjustmentRequest,
    AvatarVersion,
    PatientSession,
    SessionAvatarAuthorization,
)
from app.schemas.avatars import (
    AuthorizeAvatarRequest,
    AvatarVersionDetailResponse,
    AvatarVersionListResponse,
    AvatarVersionResponse,
    CancelAvatarGenerationRequest,
    CreateAvatarGenerationRequest,
    DeleteAvatarVersionRequest,
    DeleteAvatarVersionResponse,
    ReviewAvatarRequest,
    RevokeAvatarAuthorizationRequest,
    RevokeAvatarAuthorizationResponse,
    RollbackAvatarRequest,
)
from app.services.avatar_generation import create_avatar_generation, process_avatar_generation
from app.services.core import add_audit, add_idempotency, find_idempotency, utc_now

router = APIRouter()


def avatar_response(
    version: AvatarVersion, *, is_authorized: bool = False
) -> AvatarVersionResponse:
    image_url = None
    if version.image_object_key and version.output_mime_type:
        image_url = get_object_storage(get_settings()).get_url(
            version.image_object_key, version.output_mime_type
        )
    return AvatarVersionResponse(
        version_id=version.version_id,
        case_id=version.case_id,
        generation_round=version.generation_round,
        generation_mode=version.generation_mode,
        generation_status=version.generation_status,
        safety_status=version.safety_status,
        doctor_review_status=version.doctor_review_status,
        provider_kind=version.provider_kind,
        provider_model=version.provider_model,
        prompt_template_version=version.prompt_template_version,
        image_url=image_url,
        failure_code=version.failure_code,
        is_current_candidate=version.is_current_candidate,
        is_authorized=is_authorized,
        snapshot_available=(
            version.voice_features_snapshot_json is not None
            and version.visual_features_snapshot_json is not None
        ),
        doctor_reviewed_at=version.doctor_reviewed_at,
        source_adjustment_request_id=version.source_adjustment_request_id,
        created_at=version.created_at,
        completed_at=version.completed_at,
    )


async def _is_authorized(session: AsyncSession, version_id: UUID) -> bool:
    authorization = await session.scalar(
        select(SessionAvatarAuthorization.authorization_id).where(
            SessionAvatarAuthorization.version_id == version_id,
            SessionAvatarAuthorization.status == AuthorizationStatus.AUTHORIZED,
        )
    )
    return authorization is not None


async def _delete_avatar_version(
    session: AsyncSession,
    version: AvatarVersion,
) -> None:
    """Remove one non-authorized version and keep the case candidate chain usable."""
    if await _is_authorized(session, version.version_id):
        raise ApiError(
            409,
            "AUTHORIZED_VERSION_DELETE_FORBIDDEN",
            "患者当前正在查看该版本，请先撤销患者授权",
        )

    image_object_key = version.image_object_key
    if image_object_key:
        try:
            await asyncio.to_thread(
                get_object_storage(get_settings()).delete,
                image_object_key,
            )
        except Exception as exc:
            raise ApiError(
                503,
                "STORAGE_UNAVAILABLE",
                "图像文件暂时无法删除，请稍后重试",
            ) from exc

    await session.execute(
        delete(SessionAvatarAuthorization).where(
            SessionAvatarAuthorization.version_id == version.version_id
        )
    )

    if version.is_current_candidate:
        replacement = await session.scalar(
            select(AvatarVersion)
            .where(
                AvatarVersion.case_id == version.case_id,
                AvatarVersion.version_id != version.version_id,
                AvatarVersion.generation_status == GenerationStatus.APPROVED,
            )
            .order_by(AvatarVersion.generation_round.desc())
            .limit(1)
        )
        if replacement is not None:
            replacement.is_current_candidate = True

    await session.delete(version)


async def _dispatch_generation(session: AsyncSession, version: AvatarVersion) -> None:
    settings = get_settings()
    if settings.generation_dispatch_mode == "celery":
        from app.workers.avatar_generation import generate_avatar

        generate_avatar.delay(str(version.version_id))
        return
    await process_avatar_generation(session, version.version_id, settings)


@router.post(
    "/cases/{case_id}/avatar-generations",
    response_model=AvatarVersionResponse,
    status_code=202,
)
async def create_generation(
    case_id: UUID,
    payload: CreateAvatarGenerationRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> AvatarVersionResponse:
    await owned_case_or_404(session, case_id, staff.user.user_id)
    scope = f"doctor:{staff.user.user_id}:case:{case_id}"
    request_payload = payload.model_dump(mode="json")
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="create_avatar_generation",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing and existing.resource_id:
        prior = await session.get(AvatarVersion, existing.resource_id)
        if prior is None:
            raise ApiError(409, "STATE_CONFLICT", "生图版本已不可用")
        return avatar_response(prior)
    version = await create_avatar_generation(
        session,
        case_id=case_id,
        mode=GenerationMode(payload.mode),
        settings=get_settings(),
    )
    add_idempotency(
        session,
        actor_scope=scope,
        operation="create_avatar_generation",
        key=idempotency_key,
        payload=request_payload,
        resource_id=version.version_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=case_id,
        action="avatar.generation_requested",
        metadata={"mode": payload.mode, "round": version.generation_round},
    )
    await session.commit()
    await _dispatch_generation(session, version)
    await session.refresh(version)
    return avatar_response(version)


@router.get("/cases/{case_id}/avatar-versions", response_model=AvatarVersionListResponse)
async def list_versions(
    case_id: UUID,
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> AvatarVersionListResponse:
    await owned_case_or_404(session, case_id, staff.user.user_id)
    versions = (
        await session.scalars(
            select(AvatarVersion)
            .where(AvatarVersion.case_id == case_id)
            .order_by(AvatarVersion.generation_round.desc())
        )
    ).all()
    version_ids = [item.version_id for item in versions]
    authorized_ids = (
        set(
            (
                await session.scalars(
                    select(SessionAvatarAuthorization.version_id).where(
                        SessionAvatarAuthorization.version_id.in_(version_ids),
                        SessionAvatarAuthorization.status == AuthorizationStatus.AUTHORIZED,
                    )
                )
            ).all()
        )
        if version_ids
        else set()
    )
    return AvatarVersionListResponse(
        items=[
            avatar_response(item, is_authorized=item.version_id in authorized_ids)
            for item in versions
        ]
    )


@router.post(
    "/avatar-versions/{version_id}/cancel",
    response_model=AvatarVersionResponse,
)
async def cancel_generation(
    version_id: UUID,
    payload: CancelAvatarGenerationRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> AvatarVersionResponse:
    version = await session.get(AvatarVersion, version_id)
    if version is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Avatar 版本不存在或无权访问")
    await owned_case_or_404(session, version.case_id, staff.user.user_id, for_update=True)
    version = await session.scalar(
        select(AvatarVersion)
        .where(AvatarVersion.version_id == version_id)
        .with_for_update()
    )
    if version is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Avatar 版本不存在或无权访问")

    scope = f"doctor:{staff.user.user_id}:avatar:{version_id}"
    request_payload = payload.model_dump(mode="json")
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="cancel_avatar_generation",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing:
        return avatar_response(version)
    if version.generation_status == GenerationStatus.CANCELLED:
        return avatar_response(version)
    if version.generation_status not in {
        GenerationStatus.QUEUED,
        GenerationStatus.GENERATING,
        GenerationStatus.CHECKING,
    }:
        raise ApiError(409, "STATE_CONFLICT", "该生图任务已结束，无法取消")

    version.generation_status = GenerationStatus.CANCELLED
    version.safety_status = "cancelled"
    version.doctor_review_status = "cancelled"
    version.completed_at = utc_now()
    if version.source_adjustment_request_id:
        adjustment = await session.get(
            AdjustmentRequest, version.source_adjustment_request_id
        )
        if adjustment:
            adjustment.doctor_status = AdjustmentStatus.CANCELLED
    add_idempotency(
        session,
        actor_scope=scope,
        operation="cancel_avatar_generation",
        key=idempotency_key,
        payload=request_payload,
        resource_id=version.version_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=version.case_id,
        action="avatar.generation_cancelled",
        metadata={
            "round": version.generation_round,
            "reason_present": bool(payload.reason),
        },
    )
    await session.commit()
    return avatar_response(version)


@router.get(
    "/cases/{case_id}/avatar-versions/{version_id}",
    response_model=AvatarVersionDetailResponse,
)
async def get_version_detail(
    case_id: UUID,
    version_id: UUID,
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> AvatarVersionDetailResponse:
    version = await session.get(AvatarVersion, version_id)
    if version is None or version.case_id != case_id:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Avatar 版本不存在或无权访问")
    await owned_case_or_404(session, case_id, staff.user.user_id)
    summary = avatar_response(
        version, is_authorized=await _is_authorized(session, version.version_id)
    )
    return AvatarVersionDetailResponse(
        **summary.model_dump(),
        voice_features_snapshot=version.voice_features_snapshot_json,
        visual_features_snapshot=version.visual_features_snapshot_json,
    )


@router.get("/cases/{case_id}/avatar-versions/{version_id}/download")
async def download_version(
    case_id: UUID,
    version_id: UUID,
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    version = await session.get(AvatarVersion, version_id)
    if version is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Avatar 版本不存在或无权访问")
    if version.case_id != case_id:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Avatar 版本不存在或无权访问")
    await owned_case_or_404(session, case_id, staff.user.user_id)
    if (
        version.generation_status != GenerationStatus.APPROVED
        or not version.image_object_key
        or version.output_mime_type != "image/png"
    ):
        raise ApiError(409, "STATE_CONFLICT", "只有已审核通过的 PNG 版本可以下载")
    if version.voice_features_snapshot_json is None:
        raise ApiError(409, "SNAPSHOT_NOT_AVAILABLE", "该历史版本没有可下载的 Q1–Q8 快照")
    try:
        image = get_object_storage(get_settings()).get(version.image_object_key)
    except Exception as exc:
        raise ApiError(503, "STORAGE_UNAVAILABLE", "版本文件暂时无法读取") from exc

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("avatar.png", image)
        bundle.writestr(
            "q1-q8.json",
            json.dumps(
                {"q1_q8": version.voice_features_snapshot_json},
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
        )
    archive.seek(0)
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=version.case_id,
        action="avatar.downloaded",
        metadata={"generation_round": version.generation_round, "format": "zip"},
    )
    await session.commit()
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="avatar-version-{version.generation_round}.zip"'
            )
        },
    )


async def _authorize(
    session: AsyncSession,
    version: AvatarVersion,
    session_id: UUID,
    doctor_id: UUID,
) -> None:
    patient_session = await session.get(PatientSession, session_id)
    if (
        patient_session is None
        or patient_session.case_id != version.case_id
        or patient_session.supervising_doctor_id != doctor_id
    ):
        raise ApiError(422, "VALIDATION_ERROR", "只能授权给本病例的当前监督会话")
    if patient_session.status != SessionStatus.ACTIVE:
        raise ApiError(409, "SESSION_INVALID", "只有进行中的监督会话可以接收授权")
    now = utc_now()
    await session.execute(
        update(SessionAvatarAuthorization)
        .where(
            SessionAvatarAuthorization.session_id == session_id,
            SessionAvatarAuthorization.status == AuthorizationStatus.AUTHORIZED,
        )
        .values(
            status=AuthorizationStatus.REVOKED,
            revoked_at=now,
            revoke_reason="superseded_by_doctor",
        )
    )
    session.add(
        SessionAvatarAuthorization(
            session_id=session_id,
            version_id=version.version_id,
            status=AuthorizationStatus.AUTHORIZED,
            authorized_by=doctor_id,
            authorized_at=now,
        )
    )


@router.post("/avatar-versions/{version_id}/review", response_model=AvatarVersionResponse)
async def review_version(
    version_id: UUID,
    payload: ReviewAvatarRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> AvatarVersionResponse:
    scope = f"doctor:{staff.user.user_id}:avatar:{version_id}"
    request_payload = payload.model_dump(mode="json")
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="review_avatar_version",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing and existing.response_snapshot:
        return AvatarVersionResponse(**existing.response_snapshot)

    version = await session.get(AvatarVersion, version_id)
    if version is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Avatar 版本不存在或无权访问")
    await owned_case_or_404(
        session, version.case_id, staff.user.user_id, for_update=True
    )
    if existing:
        return avatar_response(
            version, is_authorized=await _is_authorized(session, version.version_id)
        )
    if version.generation_status != GenerationStatus.PENDING_DOCTOR_REVIEW:
        raise ApiError(409, "STATE_CONFLICT", "该版本当前不能执行审核")
    now = utc_now()
    if payload.decision == "approve":
        version.generation_status = GenerationStatus.APPROVED
        version.doctor_review_status = "approved"
    else:
        version.generation_status = GenerationStatus.REJECTED
        version.doctor_review_status = "rejected"
        if version.source_adjustment_request_id:
            adjustment = await session.get(
                AdjustmentRequest, version.source_adjustment_request_id
            )
            if adjustment:
                adjustment.doctor_status = AdjustmentStatus.GENERATION_FAILED
    version.doctor_reviewed_by = staff.user.user_id
    version.doctor_reviewed_at = now
    response = avatar_response(version)
    if payload.decision == "reject":
        response = response.model_copy(update={"image_url": None})
        await _delete_avatar_version(session, version)
    add_idempotency(
        session,
        actor_scope=scope,
        operation="review_avatar_version",
        key=idempotency_key,
        payload=request_payload,
        resource_id=None if payload.decision == "reject" else version.version_id,
        response_snapshot=response.model_dump(mode="json"),
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=version.case_id,
        action="avatar.reviewed",
        metadata={
            "decision": payload.decision,
            "round": version.generation_round,
            "auto_deleted": payload.decision == "reject",
        },
    )
    await session.commit()
    return response


@router.post(
    "/avatar-versions/{version_id}/delete",
    response_model=DeleteAvatarVersionResponse,
)
async def delete_version(
    version_id: UUID,
    payload: DeleteAvatarVersionRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> DeleteAvatarVersionResponse:
    scope = f"doctor:{staff.user.user_id}:manual-avatar-version-delete"
    request_payload = {
        "version_id": str(version_id),
        "confirmation": payload.confirmation,
        "reason_present": bool(payload.reason),
    }
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="delete_avatar_version",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing and existing.response_snapshot:
        return DeleteAvatarVersionResponse(**existing.response_snapshot)

    version = await session.get(AvatarVersion, version_id)
    if version is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Avatar 版本不存在或无权访问")
    await owned_case_or_404(
        session, version.case_id, staff.user.user_id, for_update=True
    )
    version = await session.scalar(
        select(AvatarVersion)
        .where(AvatarVersion.version_id == version_id)
        .with_for_update()
    )
    if version is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Avatar 版本不存在或无权访问")
    if version.generation_status in {
        GenerationStatus.QUEUED,
        GenerationStatus.GENERATING,
        GenerationStatus.CHECKING,
        GenerationStatus.PENDING_DOCTOR_REVIEW,
    }:
        raise ApiError(
            409,
            "STATE_CONFLICT",
            "生成中版本请先取消，待审核版本请使用“拒绝此图”",
        )
    if await _is_authorized(session, version.version_id):
        raise ApiError(
            409,
            "AUTHORIZED_VERSION_DELETE_FORBIDDEN",
            "患者当前正在查看该版本，请先撤销患者授权",
        )

    case_id = version.case_id
    generation_round = version.generation_round
    response = DeleteAvatarVersionResponse(
        version_id=version.version_id,
        generation_round=generation_round,
    )
    await _delete_avatar_version(session, version)
    add_idempotency(
        session,
        actor_scope=scope,
        operation="delete_avatar_version",
        key=idempotency_key,
        payload=request_payload,
        resource_id=None,
        response_snapshot=response.model_dump(mode="json"),
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=case_id,
        action="avatar.version_deleted",
        metadata={
            "round": generation_round,
            "source": "doctor_manual_delete",
            "reason_present": bool(payload.reason),
        },
    )
    await session.commit()
    return response


@router.post("/avatar-versions/{version_id}/rollback", response_model=AvatarVersionResponse)
async def rollback_version(
    version_id: UUID,
    payload: RollbackAvatarRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> AvatarVersionResponse:
    version = await session.get(AvatarVersion, version_id)
    if version is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Avatar 版本不存在或无权访问")
    await owned_case_or_404(
        session, version.case_id, staff.user.user_id, for_update=True
    )
    scope = f"doctor:{staff.user.user_id}:avatar:{version_id}"
    request_payload = payload.model_dump(mode="json")
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="rollback_avatar_version",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing:
        return avatar_response(
            version, is_authorized=await _is_authorized(session, version.version_id)
        )
    if version.generation_status != GenerationStatus.APPROVED:
        raise ApiError(409, "STATE_CONFLICT", "只有已审核的历史版本可以发起回退")
    if version.is_current_candidate:
        raise ApiError(409, "STATE_CONFLICT", "该版本已经是当前候选版本")
    if payload.session_id is not None:
        patient_session = await session.get(PatientSession, payload.session_id)
        if (
            patient_session is None
            or patient_session.case_id != version.case_id
            or patient_session.supervising_doctor_id != staff.user.user_id
            or patient_session.status != SessionStatus.ACTIVE
        ):
            raise ApiError(422, "VALIDATION_ERROR", "请选择本病例进行中的监督会话")

    now = utc_now()
    case_session_ids = list(
        (
            await session.scalars(
                select(PatientSession.session_id).where(
                    PatientSession.case_id == version.case_id
                )
            )
        ).all()
    )
    await session.execute(
        update(SessionAvatarAuthorization)
        .where(
            SessionAvatarAuthorization.session_id.in_(case_session_ids),
            SessionAvatarAuthorization.status == AuthorizationStatus.AUTHORIZED,
        )
        .values(
            status=AuthorizationStatus.REVOKED,
            revoked_at=now,
            revoke_reason="doctor_rollback_started",
        )
    )
    await session.execute(
        update(AvatarVersion)
        .where(AvatarVersion.case_id == version.case_id)
        .values(is_current_candidate=False)
    )
    version.is_current_candidate = True
    version.generation_status = GenerationStatus.PENDING_DOCTOR_REVIEW
    version.doctor_review_status = "pending_re_review"
    version.doctor_reviewed_by = None
    version.doctor_reviewed_at = None
    add_idempotency(
        session,
        actor_scope=scope,
        operation="rollback_avatar_version",
        key=idempotency_key,
        payload=request_payload,
        resource_id=version.version_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=version.case_id,
        session_id=payload.session_id,
        action="avatar.rollback_requested",
        metadata={
            "round": version.generation_round,
            "reason_present": bool(payload.reason),
        },
    )
    await session.commit()
    return avatar_response(version)


@router.post("/avatar-versions/{version_id}/authorize", response_model=AvatarVersionResponse)
async def authorize_existing_version(
    version_id: UUID,
    payload: AuthorizeAvatarRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> AvatarVersionResponse:
    version = await session.get(AvatarVersion, version_id)
    if version is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Avatar 版本不存在或无权访问")
    await owned_case_or_404(
        session, version.case_id, staff.user.user_id, for_update=True
    )
    if version.generation_status != GenerationStatus.APPROVED:
        raise ApiError(409, "STATE_CONFLICT", "只有已通过审核的版本可以授权")
    if not version.is_current_candidate:
        raise ApiError(409, "ROLLBACK_REVIEW_REQUIRED", "历史版本必须先回退并重新审核")
    scope = f"doctor:{staff.user.user_id}:avatar:{version_id}"
    request_payload = payload.model_dump(mode="json")
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="authorize_avatar_version",
        key=idempotency_key,
        payload=request_payload,
    )
    if not existing:
        await _authorize(session, version, payload.session_id, staff.user.user_id)
        if version.source_adjustment_request_id:
            adjustment = await session.get(
                AdjustmentRequest, version.source_adjustment_request_id
            )
            if adjustment:
                adjustment.doctor_status = AdjustmentStatus.APPLIED
        add_idempotency(
            session,
            actor_scope=scope,
            operation="authorize_avatar_version",
            key=idempotency_key,
            payload=request_payload,
            resource_id=version.version_id,
        )
        add_audit(
            session,
            actor_type=AuditActorType.DOCTOR,
            actor_user_id=staff.user.user_id,
            case_id=version.case_id,
            session_id=payload.session_id,
            action="avatar.authorized",
            metadata={"round": version.generation_round},
        )
        await session.commit()
    return avatar_response(version, is_authorized=True)


@router.post(
    "/cases/{case_id}/authorization/revoke",
    response_model=RevokeAvatarAuthorizationResponse,
)
async def revoke_avatar_authorization(
    case_id: UUID,
    payload: RevokeAvatarAuthorizationRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> RevokeAvatarAuthorizationResponse:
    await owned_case_or_404(
        session, case_id, staff.user.user_id, for_update=True
    )
    patient_session = await session.get(PatientSession, payload.session_id)
    if (
        patient_session is None
        or patient_session.case_id != case_id
        or patient_session.supervising_doctor_id != staff.user.user_id
    ):
        raise ApiError(404, "RESOURCE_NOT_FOUND", "会话不存在或无权访问")
    scope = f"doctor:{staff.user.user_id}:case:{case_id}"
    request_payload = payload.model_dump(mode="json")
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="revoke_avatar_authorization",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing:
        return RevokeAvatarAuthorizationResponse(
            revoked_count=int((existing.response_snapshot or {}).get("revoked_count", 0))
        )

    now = utc_now()
    result = await session.execute(
        update(SessionAvatarAuthorization)
        .where(
            SessionAvatarAuthorization.session_id == payload.session_id,
            SessionAvatarAuthorization.status == AuthorizationStatus.AUTHORIZED,
        )
        .values(
            status=AuthorizationStatus.REVOKED,
            revoked_at=now,
            revoke_reason=payload.reason or "doctor_manual_revoke",
        )
    )
    revoked_count = result.rowcount or 0
    if revoked_count == 0:
        raise ApiError(409, "STATE_CONFLICT", "该会话没有可撤销的 Avatar 授权")
    add_idempotency(
        session,
        actor_scope=scope,
        operation="revoke_avatar_authorization",
        key=idempotency_key,
        payload=request_payload,
        resource_id=payload.session_id,
        response_snapshot={"revoked_count": revoked_count},
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=case_id,
        session_id=payload.session_id,
        action="avatar.authorization_revoked",
        metadata={
            "revoked_count": revoked_count,
            "reason_present": bool(payload.reason),
        },
    )
    await session.commit()
    return RevokeAvatarAuthorizationResponse(revoked_count=revoked_count)


async def create_adjustment_generation(
    request: AdjustmentRequest,
    session: AsyncSession,
) -> AvatarVersion:
    version = await create_avatar_generation(
        session,
        case_id=request.case_id,
        mode=GenerationMode.PATIENT_ADJUSTMENT,
        settings=get_settings(),
        adjustment=request,
    )
    await session.commit()
    await _dispatch_generation(session, version)
    await session.refresh(version)
    return version
