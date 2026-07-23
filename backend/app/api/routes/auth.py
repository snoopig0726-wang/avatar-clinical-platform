from __future__ import annotations

import re
import secrets
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    AuthenticatedStaff,
    get_current_staff,
    require_idempotency_key,
)
from app.api.errors import ApiError
from app.config.settings import get_settings
from app.database import get_db_session
from app.domain.enums import ApprovalStatus, AuditActorType, Role
from app.models.entities import EmailVerificationToken, StaffAccessSession, StaffUser
from app.schemas.auth import (
    DoctorApplicationRequest,
    DoctorApplicationResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    StaffSummary,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from app.security.crypto import encode_staff_token, hash_password, hash_secret, verify_password
from app.security.rate_limit import (
    DOCTOR_APPLICATION_POLICY,
    EMAIL_VERIFICATION_POLICY,
    LOGIN_POLICY,
    enforce_rate_limit,
)
from app.services.core import (
    add_audit,
    add_idempotency,
    find_idempotency,
    is_expired,
    utc_now,
)

router = APIRouter()


@router.post(
    "/doctor-applications",
    response_model=DoctorApplicationResponse,
    status_code=202,
)
async def create_doctor_application(
    payload: DoctorApplicationRequest,
    request: Request,
    idempotency_key: str = Depends(require_idempotency_key),
    session: AsyncSession = Depends(get_db_session),
) -> DoctorApplicationResponse:
    email = payload.email.strip().lower()
    display_name = payload.display_name.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ApiError(422, "VALIDATION_ERROR", "请输入有效的机构邮箱")
    if not display_name:
        raise ApiError(422, "VALIDATION_ERROR", "请输入医生姓名")

    settings = get_settings()
    client_host = request.client.host if request.client else "unknown"
    await enforce_rate_limit(
        settings,
        DOCTOR_APPLICATION_POLICY,
        f"{client_host}:{email}",
    )
    email_scope = hash_secret(email, settings.secret_key, "doctor-application").hex()[:24]
    scope = f"public:doctor-application:{email_scope}"
    request_payload = {
        "email": email,
        "display_name": display_name,
        "password_fingerprint": hash_secret(
            payload.password, settings.secret_key, "doctor-application-password"
        ).hex(),
    }
    existing_request = await find_idempotency(
        session,
        actor_scope=scope,
        operation="create_doctor_application",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing_request:
        return DoctorApplicationResponse(
            message="账户申请已收到；完成机构邮箱验证后等待管理员审批。"
        )

    user = await session.scalar(select(StaffUser).where(StaffUser.email == email))
    if user is not None and (user.role != Role.DOCTOR or user.email_verified):
        add_idempotency(
            session,
            actor_scope=scope,
            operation="create_doctor_application",
            key=idempotency_key,
            payload=request_payload,
            resource_id=user.user_id,
        )
        await session.commit()
        return DoctorApplicationResponse(
            message="账户申请已收到；完成机构邮箱验证后等待管理员审批。"
        )

    now = utc_now()
    if user is None:
        user = StaffUser(
            email=email,
            password_hash=hash_password(payload.password),
            display_name=display_name,
            role=Role.DOCTOR,
            email_verified=False,
            approval_status=ApprovalStatus.PENDING,
            is_active=True,
            created_at=now,
        )
        session.add(user)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise ApiError(409, "STATE_CONFLICT", "账户申请暂时无法完成，请重试") from exc
    else:
        user.password_hash = hash_password(payload.password)
        user.display_name = display_name

    token = secrets.token_urlsafe(32)
    session.add(
        EmailVerificationToken(
            user_id=user.user_id,
            token_hash=hash_secret(token, settings.secret_key, "email-verification"),
            created_at=now,
            expires_at=now + timedelta(minutes=settings.email_verification_ttl_minutes),
        )
    )
    add_idempotency(
        session,
        actor_scope=scope,
        operation="create_doctor_application",
        key=idempotency_key,
        payload=request_payload,
        resource_id=user.user_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=user.user_id,
        action="doctor.application_submitted",
        metadata={"email_verification_required": True},
    )
    await session.commit()
    return DoctorApplicationResponse(
        message="账户申请已创建；完成机构邮箱验证后等待管理员审批。",
        development_verification_token=(
            token if settings.app_env.lower() in {"local", "test"} else None
        ),
    )


@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_doctor_email(
    payload: VerifyEmailRequest,
    request: Request,
    idempotency_key: str = Depends(require_idempotency_key),
    session: AsyncSession = Depends(get_db_session),
) -> VerifyEmailResponse:
    settings = get_settings()
    client_host = request.client.host if request.client else "unknown"
    await enforce_rate_limit(
        settings,
        EMAIL_VERIFICATION_POLICY,
        f"{client_host}:{payload.token}",
    )
    token_hash = hash_secret(payload.token, settings.secret_key, "email-verification")
    scope = f"public:email-verification:{token_hash.hex()[:24]}"
    request_payload = {"token_fingerprint": token_hash.hex()}
    existing_request = await find_idempotency(
        session,
        actor_scope=scope,
        operation="verify_doctor_email",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing_request and existing_request.resource_id:
        user = await session.get(StaffUser, existing_request.resource_id)
        if user is not None:
            return VerifyEmailResponse(
                approval_status=user.approval_status,
                message="机构邮箱已验证，请等待管理员审批。",
            )

    verification = await session.scalar(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == token_hash,
            EmailVerificationToken.used_at.is_(None),
        )
    )
    if verification is None or is_expired(verification.expires_at):
        raise ApiError(422, "VERIFICATION_INVALID", "验证链接无效或已过期")
    user = await session.get(StaffUser, verification.user_id)
    if user is None or user.role != Role.DOCTOR:
        raise ApiError(422, "VERIFICATION_INVALID", "验证链接无效或已过期")

    now = utc_now()
    verification.used_at = now
    user.email_verified = True
    add_idempotency(
        session,
        actor_scope=scope,
        operation="verify_doctor_email",
        key=idempotency_key,
        payload=request_payload,
        resource_id=user.user_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=user.user_id,
        action="doctor.email_verified",
    )
    await session.commit()
    return VerifyEmailResponse(
        approval_status=user.approval_status,
        message="机构邮箱已验证，请等待管理员审批。",
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> LoginResponse:
    settings = get_settings()
    email = payload.email.strip().lower()
    client_host = request.client.host if request.client else "unknown"
    await enforce_rate_limit(settings, LOGIN_POLICY, f"{client_host}:{email}")
    user = await session.scalar(
        select(StaffUser).where(StaffUser.email == email)
    )
    if (
        user is None
        or not verify_password(payload.password, user.password_hash)
        or not user.is_active
        or not user.email_verified
        or user.approval_status != ApprovalStatus.APPROVED
    ):
        raise ApiError(401, "UNAUTHENTICATED", "邮箱、密码或账户状态无效")

    now = utc_now()
    expires_at = now + timedelta(minutes=settings.access_token_ttl_minutes)
    access_session_id = uuid4()
    token_id = uuid4().hex
    token = encode_staff_token(
        {
            "sub": str(user.user_id),
            "role": user.role.value,
            "sid": str(access_session_id),
            "jti": token_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        },
        settings.secret_key,
    )
    session.add(
        StaffAccessSession(
            access_session_id=access_session_id,
            user_id=user.user_id,
            token_id_hash=hash_secret(token_id, settings.secret_key, "staff-token-id"),
            created_at=now,
            expires_at=expires_at,
        )
    )
    user.last_login_at = now
    await session.commit()
    return LoginResponse(
        access_token=token,
        expires_at=expires_at,
        user=StaffSummary(
            user_id=user.user_id,
            role=user.role,
            display_name=user.display_name or "工作人员",
            email=user.email,
        ),
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    staff: AuthenticatedStaff = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_session),
) -> LogoutResponse:
    staff.access_session.revoked_at = utc_now()
    await session.commit()
    return LogoutResponse(status="revoked")
