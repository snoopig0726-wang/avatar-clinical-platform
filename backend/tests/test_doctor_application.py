from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_db_session
from app.domain.enums import ApprovalStatus, Role
from app.main import app
from app.models import Base, EmailVerificationToken, StaffUser
from app.security.crypto import hash_password


@pytest.mark.asyncio
async def test_doctor_application_verification_approval_and_login(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'applications.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        session.add(
            StaffUser(
                email="application-admin@example.com",
                password_hash=hash_password("safe-admin-password-2026"),
                display_name="申请审批管理员",
                role=Role.ADMIN,
                email_verified=True,
                approval_status=ApprovalStatus.APPROVED,
                is_active=True,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            application = await client.post(
                "/api/auth/doctor-applications",
                headers={"Idempotency-Key": "doctor-application-001"},
                json={
                    "email": "new-doctor@hospital.example",
                    "password": "safe-doctor-password-2026",
                    "display_name": "新申请医生",
                },
            )
            assert application.status_code == 202
            token = application.json()["development_verification_token"]
            assert token

            before_verification = await client.post(
                "/api/auth/login",
                json={
                    "email": "new-doctor@hospital.example",
                    "password": "safe-doctor-password-2026",
                },
            )
            assert before_verification.status_code == 401

            verified = await client.post(
                "/api/auth/verify-email",
                headers={"Idempotency-Key": "verify-doctor-email-001"},
                json={"token": token},
            )
            assert verified.status_code == 200
            assert verified.json()["approval_status"] == "pending"

            before_approval = await client.post(
                "/api/auth/login",
                json={
                    "email": "new-doctor@hospital.example",
                    "password": "safe-doctor-password-2026",
                },
            )
            assert before_approval.status_code == 401

            admin_login = await client.post(
                "/api/auth/login",
                json={
                    "email": "application-admin@example.com",
                    "password": "safe-admin-password-2026",
                },
            )
            admin_headers = {
                "Authorization": f"Bearer {admin_login.json()['access_token']}",
            }
            doctors = await client.get("/api/admin/doctors", headers=admin_headers)
            applicant = next(
                item
                for item in doctors.json()["items"]
                if item["email"] == "new-doctor@hospital.example"
            )
            approved = await client.patch(
                f"/api/admin/doctors/{applicant['user_id']}",
                headers={
                    **admin_headers,
                    "Idempotency-Key": "approve-doctor-application-001",
                },
                json={"approval_status": "approved"},
            )
            assert approved.status_code == 200

            login = await client.post(
                "/api/auth/login",
                json={
                    "email": "new-doctor@hospital.example",
                    "password": "safe-doctor-password-2026",
                },
            )
            assert login.status_code == 200
            assert login.json()["user"]["role"] == "doctor"

        async with factory() as session:
            verification = await session.scalar(select(EmailVerificationToken))
            assert verification is not None
            assert verification.used_at is not None
            assert token.encode() not in verification.token_hash
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
