from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_db_session
from app.config.settings import get_settings
from app.domain.enums import ApprovalStatus, GenerationStatus, Role
from app.main import app
from app.models import AuditLog, AvatarVersion, Base, ClinicalCase, StaffUser
from app.security.crypto import hash_password
from app.services.example_data import seed_example_data


@pytest.mark.asyncio
async def test_doctor_can_cancel_active_generation_idempotently(tmp_path) -> None:
    settings = get_settings()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cancel.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as session:
        doctor = StaffUser(
            email="cancel-doctor@example.com",
            password_hash=hash_password("safe-password-2026"),
            display_name="取消生图医生",
            role=Role.DOCTOR,
            email_verified=True,
            approval_status=ApprovalStatus.APPROVED,
            is_active=True,
            created_at=datetime.now(UTC),
        )
        session.add(doctor)
        await session.flush()
        await seed_example_data(session, doctor, settings)
        clinical_case = await session.scalar(
            select(ClinicalCase).where(ClinicalCase.study_code == "DEMO-VOICE-001")
        )
        assert clinical_case is not None
        version = await session.scalar(
            select(AvatarVersion).where(AvatarVersion.case_id == clinical_case.case_id)
        )
        assert version is not None
        version.generation_status = GenerationStatus.GENERATING
        version.safety_status = "pending"
        version.doctor_review_status = "pending"
        version.completed_at = None
        await session.commit()
        version_id = version.version_id

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            login = await client.post(
                "/api/auth/login",
                json={
                    "email": "cancel-doctor@example.com",
                    "password": "safe-password-2026",
                },
            )
            doctor_headers = {
                "Authorization": f"Bearer {login.json()['access_token']}",
                "Idempotency-Key": "cancel-active-generation",
            }
            first = await client.post(
                f"/api/avatar-versions/{version_id}/cancel",
                headers=doctor_headers,
                json={"reason": "doctor_cancelled"},
            )
            repeated = await client.post(
                f"/api/avatar-versions/{version_id}/cancel",
                headers=doctor_headers,
                json={"reason": "doctor_cancelled"},
            )

        assert first.status_code == 200
        assert first.json()["generation_status"] == "cancelled"
        assert first.json()["safety_status"] == "cancelled"
        assert repeated.status_code == 200
        assert repeated.json()["generation_status"] == "cancelled"

        async with factory() as session:
            audits = (
                await session.scalars(
                    select(AuditLog).where(
                        AuditLog.action == "avatar.generation_cancelled"
                    )
                )
            ).all()
            assert len(audits) == 1
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
