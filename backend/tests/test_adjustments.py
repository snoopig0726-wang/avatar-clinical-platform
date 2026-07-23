from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_db_session
from app.config.settings import get_settings
from app.domain.enums import ApprovalStatus, Role
from app.main import app
from app.models import AdjustmentRequest, AuditLog, Base, ClinicalCase, PatientSession, StaffUser
from app.security.crypto import derive_patient_token, hash_password
from app.services.example_data import seed_example_data
from app.services.risk_engine import evaluate_adjustment_text, seed_default_risk_rules


@pytest.mark.asyncio
async def test_risk_matching_semantics(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'risk.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        await seed_default_risk_rules(session)
        await session.commit()
        assert (await evaluate_adjustment_text(session, "不要出现自残内容")).allowed is False
        assert (await evaluate_adjustment_text(session, "不要生成刀具形象")).allowed is True
        assert (await evaluate_adjustment_text(session, "生成挥舞刀具的形象")).allowed is False
        pii = await evaluate_adjustment_text(session, "联系邮箱 test@example.com")
        assert pii.allowed is False
        assert pii.patient_message_type == "identity"
        assert (await evaluate_adjustment_text(session, "希望背景更明亮柔和")).allowed is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_adjustment_risk_review_and_lifetime_quota(tmp_path) -> None:
    settings = get_settings()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'adjustments.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        doctor = StaffUser(
            email="adjustment-doctor@example.com",
            password_hash=hash_password("safe-password-2026"),
            display_name="调整审核医生",
            role=Role.DOCTOR,
            email_verified=True,
            approval_status=ApprovalStatus.APPROVED,
            is_active=True,
            created_at=datetime.now(UTC),
        )
        session.add(doctor)
        await session.flush()
        await seed_default_risk_rules(session)
        await seed_example_data(session, doctor, settings)
        case = await session.scalar(
            select(ClinicalCase).where(ClinicalCase.study_code == "DEMO-VOICE-001")
        )
        assert case is not None
        patient_session = await session.scalar(
            select(PatientSession).where(PatientSession.case_id == case.case_id)
        )
        assert patient_session is not None
        case_id = case.case_id
        session_id = patient_session.session_id

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    patient_headers = {"X-Session-Token": derive_patient_token(session_id, settings.secret_key)}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            login = await client.post(
                "/api/auth/login",
                json={
                    "email": "adjustment-doctor@example.com",
                    "password": "safe-password-2026",
                },
            )
            doctor_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            avatar = await client.get(
                f"/api/patient-sessions/{session_id}/avatar", headers=patient_headers
            )
            assert avatar.status_code == 200
            assert avatar.json()["display_mode"] == "mock_placeholder"

            blocked = await client.post(
                f"/api/patient-sessions/{session_id}/adjustment-requests",
                headers={**patient_headers, "Idempotency-Key": "blocked-direct-hit"},
                json={"instruction": "不要出现自残内容"},
            )
            assert blocked.status_code == 422
            assert "规则" not in blocked.json()["error"]["message"]

            paused = await client.get(f"/api/sessions/{session_id}", headers=doctor_headers)
            assert paused.json()["status"] == "paused"
            resumed = await client.post(
                f"/api/sessions/{session_id}/resume",
                headers={**doctor_headers, "Idempotency-Key": "resume-after-crisis"},
                json={"reason": "现场医生已评估并确认可以继续"},
            )
            assert resumed.json()["status"] == "active"

            patient_list = await client.get(
                f"/api/patient-sessions/{session_id}/adjustment-requests",
                headers=patient_headers,
            )
            assert patient_list.json()["used"] == 1
            assert "instruction" not in patient_list.json()["items"][0]

            doctor_list = await client.get(
                f"/api/cases/{case_id}/adjustment-requests", headers=doctor_headers
            )
            first = doctor_list.json()["items"][0]
            assert "更平静" in first["instruction"]

            rejected = await client.post(
                f"/api/adjustment-requests/{first['request_id']}/review",
                headers={**doctor_headers, "Idempotency-Key": "reject-first"},
                json={"decision": "reject"},
            )
            assert rejected.json()["status"] == "rejected"

            second_headers = {**patient_headers, "Idempotency-Key": "safe-second"}
            second = await client.post(
                f"/api/patient-sessions/{session_id}/adjustment-requests",
                headers=second_headers,
                json={"instruction": "希望背景更明亮柔和"},
            )
            assert second.status_code == 201
            assert second.json()["used"] == 2
            replay = await client.post(
                f"/api/patient-sessions/{session_id}/adjustment-requests",
                headers=second_headers,
                json={"instruction": "希望背景更明亮柔和"},
            )
            assert replay.json()["request_id"] == second.json()["request_id"]
            assert replay.json()["used"] == 2

            await client.post(
                f"/api/adjustment-requests/{second.json()['request_id']}/review",
                headers={**doctor_headers, "Idempotency-Key": "reject-second"},
                json={"decision": "reject"},
            )
            third = await client.post(
                f"/api/patient-sessions/{session_id}/adjustment-requests",
                headers={**patient_headers, "Idempotency-Key": "safe-third"},
                json={"instruction": "希望眼神更加放松自然"},
            )
            assert third.json()["used"] == 3
            approved = await client.post(
                f"/api/adjustment-requests/{third.json()['request_id']}/review",
                headers={**doctor_headers, "Idempotency-Key": "approve-third"},
                json={"decision": "approve_as_is"},
            )
            assert approved.json()["status"] == "approved_as_is"
            assert approved.json()["controlled_instruction"] != approved.json()["instruction"]

            generation = await client.post(
                f"/api/adjustment-requests/{third.json()['request_id']}/generate",
                headers={**doctor_headers, "Idempotency-Key": "generate-third"},
            )
            assert generation.status_code == 202
            assert generation.json()["generation_mode"] == "patient_adjustment"
            assert generation.json()["generation_status"] == "pending_doctor_review"
            assert generation.json()["safety_status"] == "passed"
            assert generation.json()["image_url"].startswith("data:image/png;base64,")

            reviewed_avatar = await client.post(
                f"/api/avatar-versions/{generation.json()['version_id']}/review",
                headers={**doctor_headers, "Idempotency-Key": "review-generated-third"},
                json={"decision": "approve"},
            )
            assert reviewed_avatar.status_code == 200
            assert reviewed_avatar.json()["generation_status"] == "approved"
            assert reviewed_avatar.json()["is_authorized"] is False

            still_old_avatar = await client.get(
                f"/api/patient-sessions/{session_id}/avatar", headers=patient_headers
            )
            assert still_old_avatar.json()["display_mode"] == "mock_placeholder"

            authorized_avatar = await client.post(
                f"/api/avatar-versions/{generation.json()['version_id']}/authorize",
                headers={**doctor_headers, "Idempotency-Key": "authorize-generated-third"},
                json={"session_id": str(session_id)},
            )
            assert authorized_avatar.status_code == 200
            assert authorized_avatar.json()["is_authorized"] is True

            live_avatar = await client.get(
                f"/api/patient-sessions/{session_id}/avatar", headers=patient_headers
            )
            assert live_avatar.json()["display_mode"] == "image"
            assert live_avatar.json()["image_url"].startswith("data:image/png;base64,")

            exhausted = await client.post(
                f"/api/patient-sessions/{session_id}/adjustment-requests",
                headers={**patient_headers, "Idempotency-Key": "safe-fourth"},
                json={"instruction": "希望构图距离稍微远一点"},
            )
            assert exhausted.status_code == 409
            assert exhausted.json()["error"]["code"] == "ADJUSTMENT_LIMIT_REACHED"

        async with factory() as session:
            assert await session.scalar(select(func.count(AdjustmentRequest.request_id))) == 3
            blocked_audit = await session.scalar(
                select(AuditLog).where(AuditLog.action == "adjustment.risk_blocked")
            )
            assert blocked_audit is not None
            assert "自残" not in str(blocked_audit.metadata_json)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
