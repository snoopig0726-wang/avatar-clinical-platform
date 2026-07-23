from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AuthenticatedStaff, require_admin, require_idempotency_key
from app.api.errors import ApiError
from app.database import get_db_session
from app.domain.enums import (
    AdjustmentStatus,
    ApprovalStatus,
    AuditActorType,
    CaseStatus,
    GenerationStatus,
    RetentionStatus,
    RiskRuleType,
    Role,
    SessionStatus,
)
from app.models.entities import (
    AdjustmentRequest,
    AuditLog,
    AvatarVersion,
    ClinicalCase,
    PatientSession,
    RetentionJob,
    RiskRule,
    StaffAccessSession,
    StaffUser,
)
from app.schemas.admin import (
    AdminArchivedCaseListResponse,
    AdminArchivedCaseResponse,
    AdminAuditListResponse,
    AdminAuditResponse,
    AdminDoctorListResponse,
    AdminDoctorResponse,
    AdminRiskRuleListResponse,
    AdminRiskRuleResponse,
    AdminStatsResponse,
    OperationalAlertResponse,
    RestoreCaseRequest,
    RestoreCaseResponse,
    RetentionJobListResponse,
    RetentionJobResponse,
    UpdateDoctorAccessRequest,
    UpdateRiskRuleRequest,
)
from app.services.core import (
    add_audit,
    add_idempotency,
    ensure_utc,
    find_idempotency,
    utc_now,
)

router = APIRouter()

AUDIT_METADATA_ALLOWLIST = {
    "changed_fields",
    "consent_version",
    "decision",
    "modified_keys",
    "reason_present",
    "risk_rule_version",
    "rule_codes",
    "sequence_no",
    "source",
    "version",
}


def doctor_response(user: StaffUser) -> AdminDoctorResponse:
    return AdminDoctorResponse(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name or "未命名医生",
        email_verified=user.email_verified,
        approval_status=user.approval_status,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def rule_response(rule: RiskRule) -> AdminRiskRuleResponse:
    return AdminRiskRuleResponse(
        rule_id=rule.rule_id,
        rule_code=rule.rule_code,
        category=rule.category,
        rule_type=rule.rule_type,
        trigger_terms=rule.trigger_terms,
        context_terms=rule.context_terms,
        exclusion_terms=rule.exclusion_terms,
        patient_message_type=rule.patient_message_type,
        version=rule.version,
        is_enabled=rule.is_enabled,
        updated_at=rule.updated_at,
    )


def retention_response(job: RetentionJob) -> RetentionJobResponse:
    return RetentionJobResponse(
        retention_job_id=job.retention_job_id,
        status=job.status,
        retention_started_at=job.retention_started_at,
        retention_due_at=job.retention_due_at,
        attempt_count=job.attempt_count,
        last_attempt_at=job.last_attempt_at,
        deleted_categories=job.deleted_categories_json,
        last_error_code=job.last_error_code,
        completed_at=job.completed_at,
    )


async def enum_counts(session: AsyncSession, column, values) -> dict[str, int]:
    rows = (await session.execute(select(column, func.count()).group_by(column))).all()
    found = {status.value: count for status, count in rows}
    return {value.value: found.get(value.value, 0) for value in values}


@router.get("/doctors", response_model=AdminDoctorListResponse)
async def list_doctors(
    staff: AuthenticatedStaff = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminDoctorListResponse:
    del staff
    doctors = (
        await session.scalars(
            select(StaffUser)
            .where(StaffUser.role == Role.DOCTOR)
            .order_by(StaffUser.created_at.desc())
        )
    ).all()
    return AdminDoctorListResponse(
        items=[doctor_response(item) for item in doctors], total=len(doctors)
    )


@router.patch("/doctors/{doctor_id}", response_model=AdminDoctorResponse)
async def update_doctor_access(
    doctor_id: UUID,
    payload: UpdateDoctorAccessRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminDoctorResponse:
    doctor = await session.get(StaffUser, doctor_id)
    if doctor is None or doctor.role != Role.DOCTOR:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "医生账户不存在")
    request_payload = payload.model_dump(exclude_unset=True)
    scope = f"admin:{staff.user.user_id}:doctor:{doctor_id}"
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="update_doctor_access",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing:
        return doctor_response(doctor)
    if payload.approval_status == ApprovalStatus.APPROVED and not doctor.email_verified:
        raise ApiError(409, "STATE_CONFLICT", "邮箱尚未验证，不能批准该医生账户")

    changed_fields: list[str] = []
    if payload.approval_status is not None and payload.approval_status != doctor.approval_status:
        doctor.approval_status = payload.approval_status
        changed_fields.append("approval_status")
    if payload.is_active is not None and payload.is_active != doctor.is_active:
        doctor.is_active = payload.is_active
        changed_fields.append("is_active")
    if payload.is_active is False or payload.approval_status == ApprovalStatus.REJECTED:
        await session.execute(
            update(StaffAccessSession)
            .where(
                StaffAccessSession.user_id == doctor_id,
                StaffAccessSession.revoked_at.is_(None),
            )
            .values(revoked_at=utc_now())
        )
    add_idempotency(
        session,
        actor_scope=scope,
        operation="update_doctor_access",
        key=idempotency_key,
        payload=request_payload,
        resource_id=doctor_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.ADMIN,
        actor_user_id=staff.user.user_id,
        action="admin.doctor_access_updated",
        metadata={"changed_fields": changed_fields},
    )
    await session.commit()
    return doctor_response(doctor)


@router.get("/risk-rules", response_model=AdminRiskRuleListResponse)
async def list_risk_rules(
    staff: AuthenticatedStaff = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminRiskRuleListResponse:
    del staff
    rules = (await session.scalars(select(RiskRule).order_by(RiskRule.rule_code))).all()
    return AdminRiskRuleListResponse(items=[rule_response(rule) for rule in rules])


@router.put("/risk-rules/{rule_id}", response_model=AdminRiskRuleResponse)
async def update_risk_rule(
    rule_id: UUID,
    payload: UpdateRiskRuleRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminRiskRuleResponse:
    rule = await session.get(RiskRule, rule_id)
    if rule is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "风险规则不存在")
    request_payload = payload.model_dump(exclude_unset=True)
    scope = f"admin:{staff.user.user_id}:risk-rule:{rule_id}"
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="update_risk_rule",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing:
        return rule_response(rule)
    if payload.version == rule.version:
        raise ApiError(422, "VALIDATION_ERROR", "修改风险规则时必须更新规则版本")

    changed_fields: list[str] = []
    for field in (
        "category",
        "trigger_terms",
        "context_terms",
        "exclusion_terms",
        "patient_message_type",
        "is_enabled",
    ):
        if field in request_payload and getattr(rule, field) != request_payload[field]:
            setattr(rule, field, request_payload[field])
            changed_fields.append(field)
    if rule.rule_type == RiskRuleType.CONTEXT and not rule.context_terms:
        raise ApiError(422, "VALIDATION_ERROR", "上下文规则必须至少包含一个关联条件")
    if not rule.trigger_terms:
        raise ApiError(422, "VALIDATION_ERROR", "风险规则必须至少包含一个触发词")
    policy_updated_at = utc_now()
    await session.execute(
        update(RiskRule).values(version=payload.version, updated_at=policy_updated_at)
    )
    rule.version = payload.version
    rule.updated_at = policy_updated_at
    changed_fields.append("version")
    add_idempotency(
        session,
        actor_scope=scope,
        operation="update_risk_rule",
        key=idempotency_key,
        payload=request_payload,
        resource_id=rule_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.ADMIN,
        actor_user_id=staff.user.user_id,
        action="admin.risk_rule_updated",
        metadata={"changed_fields": changed_fields, "version": payload.version},
    )
    await session.commit()
    return rule_response(rule)


@router.get("/stats", response_model=AdminStatsResponse)
async def admin_stats(
    staff: AuthenticatedStaff = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminStatsResponse:
    del staff
    doctor_rows = (
        await session.execute(
            select(StaffUser.approval_status, StaffUser.is_active, func.count())
            .where(StaffUser.role == Role.DOCTOR)
            .group_by(StaffUser.approval_status, StaffUser.is_active)
        )
    ).all()
    doctors = {"total": 0, "pending": 0, "approved": 0, "rejected": 0, "disabled": 0}
    for approval, active, count in doctor_rows:
        doctors["total"] += count
        doctors[approval.value] += count
        if not active:
            doctors["disabled"] += count
    risk_blocks = await session.scalar(
        select(func.count(AuditLog.audit_id)).where(AuditLog.action == "adjustment.risk_blocked")
    )
    now = utc_now()
    generation_counts = await enum_counts(
        session,
        AvatarVersion.generation_status,
        GenerationStatus,
    )
    successful_generations = sum(
        generation_counts[status.value]
        for status in (
            GenerationStatus.PENDING_DOCTOR_REVIEW,
            GenerationStatus.APPROVED,
            GenerationStatus.REJECTED,
        )
    )
    completed_generations = (
        successful_generations
        + generation_counts[GenerationStatus.FAILED.value]
        + generation_counts[GenerationStatus.CANCELLED.value]
    )
    duration_rows = (
        await session.execute(
            select(AvatarVersion.started_at, AvatarVersion.completed_at).where(
                AvatarVersion.started_at.is_not(None),
                AvatarVersion.completed_at.is_not(None),
            )
        )
    ).all()
    durations = [
        (ensure_utc(completed_at) - ensure_utc(started_at)).total_seconds()
        for started_at, completed_at in duration_rows
        if started_at is not None and completed_at is not None
    ]
    retention_counts = await enum_counts(session, RetentionJob.status, RetentionStatus)
    overdue_retention = await session.scalar(
        select(func.count(RetentionJob.retention_job_id)).where(
            RetentionJob.retention_due_at <= now,
            RetentionJob.status.in_(
                {RetentionStatus.SCHEDULED, RetentionStatus.RETRYING}
            ),
        )
    )
    stuck_generations = await session.scalar(
        select(func.count(AvatarVersion.version_id)).where(
            AvatarVersion.generation_status.in_(
                {
                    GenerationStatus.QUEUED,
                    GenerationStatus.GENERATING,
                    GenerationStatus.CHECKING,
                }
            ),
            AvatarVersion.created_at <= now - timedelta(minutes=15),
        )
    )
    recent_generation_failures = await session.scalar(
        select(func.count(AvatarVersion.version_id)).where(
            AvatarVersion.generation_status == GenerationStatus.FAILED,
            AvatarVersion.created_at >= now - timedelta(hours=24),
        )
    )
    alerts: list[OperationalAlertResponse] = []
    if retention_counts[RetentionStatus.FAILED.value]:
        alerts.append(
            OperationalAlertResponse(
                code="RETENTION_FAILED",
                severity="critical",
                message="存在永久删除失败任务，需要人工检查依赖服务。",
                count=retention_counts[RetentionStatus.FAILED.value],
            )
        )
    if overdue_retention:
        alerts.append(
            OperationalAlertResponse(
                code="RETENTION_OVERDUE",
                severity="critical",
                message="存在已到删除时间但尚未完成的病例。",
                count=overdue_retention,
            )
        )
    if stuck_generations:
        alerts.append(
            OperationalAlertResponse(
                code="GENERATION_STUCK",
                severity="warning",
                message="存在超过 15 分钟仍未完成的生图任务。",
                count=stuck_generations,
            )
        )
    if recent_generation_failures:
        alerts.append(
            OperationalAlertResponse(
                code="GENERATION_FAILED_24H",
                severity="warning",
                message="过去 24 小时存在生图失败任务。",
                count=recent_generation_failures,
            )
        )
    return AdminStatsResponse(
        doctors=doctors,
        cases=await enum_counts(session, ClinicalCase.status, CaseStatus),
        sessions=await enum_counts(session, PatientSession.status, SessionStatus),
        adjustments=await enum_counts(session, AdjustmentRequest.doctor_status, AdjustmentStatus),
        risk_blocks=risk_blocks or 0,
        retention_jobs=retention_counts,
        generations=generation_counts,
        generation_success_rate=(
            round(successful_generations / completed_generations, 4)
            if completed_generations
            else None
        ),
        average_generation_seconds=(
            round(sum(durations) / len(durations), 2) if durations else None
        ),
        alerts=alerts,
    )


@router.get("/audit-logs", response_model=AdminAuditListResponse)
async def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    staff: AuthenticatedStaff = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminAuditListResponse:
    del staff
    total = await session.scalar(select(func.count(AuditLog.audit_id)))
    events = (
        await session.scalars(
            select(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = []
    for event in events:
        metadata = {
            key: value
            for key, value in (event.metadata_json or {}).items()
            if key in AUDIT_METADATA_ALLOWLIST
        } or None
        items.append(
            AdminAuditResponse(
                audit_id=event.audit_id,
                actor_type=event.actor_type,
                actor_user_id=event.actor_user_id,
                action=event.action,
                result=event.result,
                metadata=metadata,
                created_at=event.created_at,
            )
        )
    return AdminAuditListResponse(items=items, page=page, page_size=page_size, total=total or 0)


@router.get("/archived-cases", response_model=AdminArchivedCaseListResponse)
async def list_archived_cases(
    staff: AuthenticatedStaff = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminArchivedCaseListResponse:
    del staff
    now = utc_now()
    cases = (
        await session.scalars(
            select(ClinicalCase)
            .where(ClinicalCase.status == CaseStatus.ARCHIVED)
            .order_by(ClinicalCase.retention_due_at)
        )
    ).all()
    return AdminArchivedCaseListResponse(
        items=[
            AdminArchivedCaseResponse(
                case_id=case.case_id,
                archived_at=case.archived_at,
                retention_due_at=case.retention_due_at,
                restorable=ensure_utc(case.retention_due_at) > now,
            )
            for case in cases
            if case.archived_at is not None and case.retention_due_at is not None
        ]
    )


@router.post("/cases/{case_id}/restore", response_model=RestoreCaseResponse)
async def restore_case(
    case_id: UUID,
    payload: RestoreCaseRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> RestoreCaseResponse:
    case = await session.get(ClinicalCase, case_id)
    if case is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "归档病例不存在")
    scope = f"admin:{staff.user.user_id}:case:{case_id}"
    request_payload = {"reason_present": bool(payload.reason)}
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="restore_case",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing and case.retention_due_at is not None:
        return RestoreCaseResponse(
            case_id=case_id,
            status=case.status.value,
            retention_due_at=case.retention_due_at,
        )
    if case.status != CaseStatus.ARCHIVED or case.retention_due_at is None:
        raise ApiError(409, "STATE_CONFLICT", "病例当前不可恢复")
    if ensure_utc(case.retention_due_at) <= utc_now():
        raise ApiError(409, "RETENTION_EXPIRED", "病例已达到永久删除时间，不能恢复")

    case.status = CaseStatus.DRAFT
    case.archived_at = None
    case.updated_at = utc_now()
    add_idempotency(
        session,
        actor_scope=scope,
        operation="restore_case",
        key=idempotency_key,
        payload=request_payload,
        resource_id=case_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.ADMIN,
        actor_user_id=staff.user.user_id,
        case_id=case_id,
        action="admin.case_restored",
        metadata={"reason_present": bool(payload.reason)},
    )
    await session.commit()
    return RestoreCaseResponse(
        case_id=case_id,
        status=case.status.value,
        retention_due_at=case.retention_due_at,
    )


@router.get("/retention-jobs", response_model=RetentionJobListResponse)
async def list_retention_jobs(
    staff: AuthenticatedStaff = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> RetentionJobListResponse:
    del staff
    jobs = (
        await session.scalars(select(RetentionJob).order_by(RetentionJob.retention_due_at))
    ).all()
    return RetentionJobListResponse(items=[retention_response(job) for job in jobs])
