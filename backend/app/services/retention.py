from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import RetentionStatus
from app.models.entities import (
    AdjustmentRequest,
    AuditLog,
    AvatarVersion,
    ClinicalCase,
    IdempotencyRecord,
    PatientSession,
    RetentionJob,
    SessionAvatarAuthorization,
    SessionInvite,
    SoundDescription,
    VisualFeature,
)
from app.services.core import utc_now

ObjectCleanup = Callable[[UUID], Awaitable[dict[str, int]]]
MAX_RETENTION_ATTEMPTS = 3


async def noop_object_cleanup(case_id: UUID) -> dict[str, int]:
    del case_id
    return {"object_files": 0, "backup_records": 0}


async def _delete_case_business_data(
    session: AsyncSession,
    job: RetentionJob,
    case_id: UUID,
    object_cleanup: ObjectCleanup,
) -> dict[str, int]:
    object_counts = await object_cleanup(case_id)
    session_ids = list(
        (
            await session.scalars(
                select(PatientSession.session_id).where(PatientSession.case_id == case_id)
            )
        ).all()
    )
    invite_ids = list(
        (
            await session.scalars(
                select(SessionInvite.invite_id).where(SessionInvite.case_id == case_id)
            )
        ).all()
    )
    adjustment_ids = list(
        (
            await session.scalars(
                select(AdjustmentRequest.request_id).where(AdjustmentRequest.case_id == case_id)
            )
        ).all()
    )
    avatar_ids = list(
        (
            await session.scalars(
                select(AvatarVersion.version_id).where(AvatarVersion.case_id == case_id)
            )
        ).all()
    )
    sound_ids = list(
        (
            await session.scalars(
                select(SoundDescription.sound_description_id).where(
                    SoundDescription.case_id == case_id
                )
            )
        ).all()
    )
    visual_ids = list(
        (
            await session.scalars(
                select(VisualFeature.visual_feature_id).where(VisualFeature.case_id == case_id)
            )
        ).all()
    )
    authorization_ids = (
        list(
            (
                await session.scalars(
                    select(SessionAvatarAuthorization.authorization_id).where(
                        SessionAvatarAuthorization.session_id.in_(session_ids)
                    )
                )
            ).all()
        )
        if session_ids
        else []
    )
    resource_ids: list[UUID] = [
        case_id,
        *session_ids,
        *invite_ids,
        *adjustment_ids,
        *avatar_ids,
        *sound_ids,
        *visual_ids,
        *authorization_ids,
    ]

    audit_result = await session.execute(
        delete(AuditLog).where(
            or_(
                AuditLog.case_id == case_id,
                AuditLog.session_id.in_(session_ids) if session_ids else False,
                AuditLog.invite_id.in_(invite_ids) if invite_ids else False,
            )
        )
    )
    idempotency_result = await session.execute(
        delete(IdempotencyRecord).where(
            or_(
                IdempotencyRecord.resource_id.in_(resource_ids),
                IdempotencyRecord.actor_scope.contains(str(case_id)),
                *(
                    [IdempotencyRecord.actor_scope.contains(str(item)) for item in session_ids]
                    if session_ids
                    else []
                ),
            )
        )
    )
    adjustment_result = await session.execute(
        delete(AdjustmentRequest).where(AdjustmentRequest.case_id == case_id)
    )
    if session_ids:
        authorization_result = await session.execute(
            delete(SessionAvatarAuthorization).where(
                SessionAvatarAuthorization.session_id.in_(session_ids)
            )
        )
    else:
        authorization_result = None
    avatar_result = await session.execute(
        delete(AvatarVersion).where(AvatarVersion.case_id == case_id)
    )
    visual_result = await session.execute(
        delete(VisualFeature).where(VisualFeature.case_id == case_id)
    )
    sound_result = await session.execute(
        delete(SoundDescription).where(SoundDescription.case_id == case_id)
    )
    patient_session_result = await session.execute(
        delete(PatientSession).where(PatientSession.case_id == case_id)
    )
    invite_result = await session.execute(
        delete(SessionInvite).where(SessionInvite.case_id == case_id)
    )
    job.case_id = None
    await session.flush()
    case_result = await session.execute(delete(ClinicalCase).where(ClinicalCase.case_id == case_id))

    return {
        "cases": case_result.rowcount or 0,
        "sessions": patient_session_result.rowcount or 0,
        "invites": invite_result.rowcount or 0,
        "sound_descriptions": sound_result.rowcount or 0,
        "visual_features": visual_result.rowcount or 0,
        "avatar_versions": avatar_result.rowcount or 0,
        "authorizations": authorization_result.rowcount if authorization_result else 0,
        "adjustment_requests": adjustment_result.rowcount or 0,
        "audit_events": audit_result.rowcount or 0,
        "idempotency_records": idempotency_result.rowcount or 0,
        **object_counts,
    }


async def process_due_retention_jobs(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    object_cleanup: ObjectCleanup = noop_object_cleanup,
) -> dict[str, int]:
    effective_now = now or utc_now()
    jobs = (
        await session.scalars(
            select(RetentionJob)
            .where(
                RetentionJob.status.in_({RetentionStatus.SCHEDULED, RetentionStatus.RETRYING}),
                RetentionJob.retention_due_at <= effective_now,
            )
            .order_by(RetentionJob.retention_due_at)
        )
    ).all()
    result = {"processed": 0, "completed": 0, "retrying": 0, "failed": 0}
    for selected_job in jobs:
        job_id = selected_job.retention_job_id
        case_id = selected_job.case_id
        if case_id is None:
            continue
        selected_job.status = RetentionStatus.RUNNING
        selected_job.attempt_count += 1
        selected_job.last_attempt_at = effective_now
        selected_job.last_error_code = None
        await session.commit()
        result["processed"] += 1
        try:
            deleted = await _delete_case_business_data(
                session, selected_job, case_id, object_cleanup
            )
            selected_job.status = RetentionStatus.COMPLETED
            selected_job.deleted_categories_json = deleted
            selected_job.completed_at = effective_now
            await session.commit()
            result["completed"] += 1
        except Exception:
            await session.rollback()
            job = await session.get(RetentionJob, job_id)
            if job is None:
                raise
            job.status = (
                RetentionStatus.FAILED
                if job.attempt_count >= MAX_RETENTION_ATTEMPTS
                else RetentionStatus.RETRYING
            )
            job.last_error_code = "RETENTION_DEPENDENCY_OR_DELETE_FAILED"
            await session.commit()
            result[job.status.value] += 1
    return result
