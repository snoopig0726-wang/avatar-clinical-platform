from __future__ import annotations

from sqlalchemy import select

from app.config.settings import Settings
from app.database import get_engine, get_session_factory
from app.domain.enums import ApprovalStatus, RetentionStatus, Role
from app.models import Base, ClinicalCase, RetentionJob, StaffUser
from app.security.crypto import hash_password, hash_secret
from app.services.core import utc_now
from app.services.example_data import seed_example_data
from app.services.risk_engine import seed_default_risk_rules


async def initialize_local_database(settings: Settings) -> None:
    engine = get_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    await bootstrap_database_data(settings)


async def bootstrap_database_data(settings: Settings) -> None:
    async with get_session_factory(settings.database_url)() as session:
        await seed_default_risk_rules(session)
        retained_cases = (
            await session.scalars(
                select(ClinicalCase).where(
                    ClinicalCase.retention_started_at.is_not(None),
                    ClinicalCase.retention_due_at.is_not(None),
                )
            )
        ).all()
        for case in retained_cases:
            existing_job = await session.scalar(
                select(RetentionJob).where(RetentionJob.case_id == case.case_id)
            )
            if existing_job is None:
                session.add(
                    RetentionJob(
                        case_id=case.case_id,
                        case_reference_hash=hash_secret(
                            str(case.case_id),
                            settings.secret_key,
                            "retention-case-reference",
                        ),
                        retention_started_at=case.retention_started_at,
                        retention_due_at=case.retention_due_at,
                        status=RetentionStatus.SCHEDULED,
                        attempt_count=0,
                    )
                )
        if not settings.bootstrap_demo_data:
            await session.commit()
            return
        email = settings.demo_doctor_email.strip().lower()
        existing = await session.scalar(select(StaffUser).where(StaffUser.email == email))
        if existing is None:
            existing = StaffUser(
                email=email,
                password_hash=hash_password(settings.demo_doctor_password),
                display_name=settings.demo_doctor_name,
                role=Role.DOCTOR,
                email_verified=True,
                approval_status=ApprovalStatus.APPROVED,
                is_active=True,
                created_at=utc_now(),
            )
            session.add(existing)
            await session.flush()
        admin_email = settings.demo_admin_email.strip().lower()
        admin = await session.scalar(select(StaffUser).where(StaffUser.email == admin_email))
        if admin is None:
            session.add(
                StaffUser(
                    email=admin_email,
                    password_hash=hash_password(settings.demo_admin_password),
                    display_name=settings.demo_admin_name,
                    role=Role.ADMIN,
                    email_verified=True,
                    approval_status=ApprovalStatus.APPROVED,
                    is_active=True,
                    created_at=utc_now(),
                )
            )
        sample_accounts = (
            (
                "pending-doctor@example.com",
                "待审批医生",
                ApprovalStatus.PENDING,
                True,
            ),
            (
                "disabled-doctor@example.com",
                "已停用医生",
                ApprovalStatus.APPROVED,
                False,
            ),
        )
        for sample_email, name, approval, active in sample_accounts:
            sample = await session.scalar(select(StaffUser).where(StaffUser.email == sample_email))
            if sample is None:
                session.add(
                    StaffUser(
                        email=sample_email,
                        password_hash=hash_password(settings.demo_doctor_password),
                        display_name=name,
                        role=Role.DOCTOR,
                        email_verified=True,
                        approval_status=approval,
                        is_active=active,
                        created_at=utc_now(),
                    )
                )
        if settings.bootstrap_example_data:
            await seed_example_data(session, existing, settings)
        else:
            await session.commit()
