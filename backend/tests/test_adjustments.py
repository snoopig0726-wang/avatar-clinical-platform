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
from app.services.adjustments import build_controlled_instruction, build_controlled_options
from app.services.example_data import seed_example_data
from app.services.risk_engine import evaluate_adjustment_text, seed_default_risk_rules


def test_controlled_instruction_preserves_patient_direction() -> None:
    controlled = build_controlled_instruction("再老一点，可怕一点。")

    assert "年龄感" in controlled
    assert "令人不安" in controlled
    assert "柔化面部" not in controlled
    assert controlled == build_controlled_options("再老一点，可怕一点。")[0]


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
async def test_adjustment_risk_review_and_per_session_quota(tmp_path) -> None:
    settings = get_settings()
    original_model_provider = settings.model_provider
    original_semantic_safety_provider = settings.semantic_image_safety_provider
    settings.model_provider = "mock"
    settings.semantic_image_safety_provider = "mock"
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

            safety_events = await client.get(
                f"/api/cases/safety-events/recent?case_id={case_id}",
                headers=doctor_headers,
            )
            assert safety_events.status_code == 200
            event_types = {
                item["event_type"] for item in safety_events.json()["items"]
            }
            assert event_types == {"patient_discomfort", "sensitive_adjustment"}
            assert all(
                "instruction" not in item for item in safety_events.json()["items"]
            )

            paused = await client.get(f"/api/sessions/{session_id}", headers=doctor_headers)
            assert paused.json()["status"] == "paused"
            resumed = await client.post(
                f"/api/sessions/{session_id}/resume",
                headers={**doctor_headers, "Idempotency-Key": "resume-after-crisis"},
                json={"reason": "现场医生已评估并确认可以继续"},
            )
            assert resumed.json()["status"] == "active"

            resolved_safety_events = await client.get(
                f"/api/cases/safety-events/recent?case_id={case_id}",
                headers=doctor_headers,
            )
            assert resolved_safety_events.status_code == 200
            assert resolved_safety_events.json()["items"] == []

            blocked_sensitive = await client.post(
                f"/api/patient-sessions/{session_id}/adjustment-requests",
                headers={**patient_headers, "Idempotency-Key": "blocked-sensitive-hit"},
                json={"instruction": "生成挥舞刀具的形象"},
            )
            assert blocked_sensitive.status_code == 422
            still_active = await client.get(
                f"/api/sessions/{session_id}", headers=doctor_headers
            )
            assert still_active.json()["status"] == "active"
            sensitive_events = await client.get(
                f"/api/cases/safety-events/recent?case_id={case_id}",
                headers=doctor_headers,
            )
            assert sensitive_events.status_code == 200
            assert [
                (item["event_type"], item["severity"])
                for item in sensitive_events.json()["items"]
            ] == [("sensitive_adjustment", "warning")]

            patient_list = await client.get(
                f"/api/patient-sessions/{session_id}/adjustment-requests",
                headers=patient_headers,
            )
            assert patient_list.json()["used"] == 1
            assert (
                patient_list.json()["items"][0]["instruction"] == "希望表情更平静，减少阴影和紧张感"
            )

            doctor_list = await client.get(
                f"/api/cases/{case_id}/adjustment-requests", headers=doctor_headers
            )
            first = doctor_list.json()["items"][0]
            assert "更平静" in first["instruction"]

            missing_reason = await client.post(
                f"/api/adjustment-requests/{first['request_id']}/review",
                headers={
                    **doctor_headers,
                    "Idempotency-Key": "reject-first-missing-reason",
                },
                json={"decision": "reject"},
            )
            assert missing_reason.status_code == 422

            rejected = await client.post(
                f"/api/adjustment-requests/{first['request_id']}/review",
                headers={**doctor_headers, "Idempotency-Key": "reject-first"},
                json={
                    "decision": "reject",
                    "rejection_reason": "本次建议与已确认的低刺激视觉方向不一致。",
                },
            )
            assert rejected.json()["status"] == "rejected"
            assert (
                rejected.json()["rejection_reason"]
                == "本次建议与已确认的低刺激视觉方向不一致。"
            )
            patient_rejected = await client.get(
                f"/api/patient-sessions/{session_id}/adjustment-requests",
                headers=patient_headers,
            )
            assert (
                patient_rejected.json()["items"][0]["rejection_reason"]
                == "本次建议与已确认的低刺激视觉方向不一致。"
            )

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
                json={
                    "decision": "reject",
                    "rejection_reason": "请在下一次现场会话中进一步说明希望调整的部分。",
                },
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

            satisfied = await client.post(
                f"/api/patient-sessions/{session_id}/avatar-feedback",
                headers={
                    **patient_headers,
                    "Idempotency-Key": "patient-satisfied-third",
                },
                json={
                    "version_id": generation.json()["version_id"],
                    "satisfied": True,
                },
            )
            assert satisfied.status_code == 200
            assert (
                satisfied.json()["patient_satisfied_version_id"]
                == generation.json()["version_id"]
            )
            assert satisfied.json()["patient_satisfied_at"] is not None

            doctor_session = await client.get(
                f"/api/sessions/{session_id}",
                headers=doctor_headers,
            )
            assert (
                doctor_session.json()["patient_satisfied_version_id"]
                == generation.json()["version_id"]
            )

            withdrawn = await client.post(
                f"/api/patient-sessions/{session_id}/avatar-feedback",
                headers={
                    **patient_headers,
                    "Idempotency-Key": "patient-withdrew-satisfaction",
                },
                json={
                    "version_id": generation.json()["version_id"],
                    "satisfied": False,
                },
            )
            assert withdrawn.status_code == 200
            assert withdrawn.json()["patient_satisfied_version_id"] is None
            assert withdrawn.json()["patient_satisfied_at"] is None

            exhausted = await client.post(
                f"/api/patient-sessions/{session_id}/adjustment-requests",
                headers={**patient_headers, "Idempotency-Key": "safe-fourth"},
                json={"instruction": "希望构图距离稍微远一点"},
            )
            assert exhausted.status_code == 409
            assert exhausted.json()["error"]["code"] == "ADJUSTMENT_LIMIT_REACHED"

            ended = await client.post(
                f"/api/sessions/{session_id}/stop",
                headers={**doctor_headers, "Idempotency-Key": "end-first-session"},
                json={"reason": "completed"},
            )
            assert ended.status_code == 200
            assert ended.json()["status"] == "ended"

            second_invite = await client.post(
                f"/api/cases/{case_id}/session-invites",
                headers={
                    **doctor_headers,
                    "Idempotency-Key": "create-second-session-invite",
                },
                json={"expires_in_hours": 24},
            )
            assert second_invite.status_code == 201
            second_redeem = await client.post(
                "/api/session-invites/redeem",
                headers={"Idempotency-Key": "redeem-second-session-invite"},
                json={
                    "code": second_invite.json()["code"],
                    "device_binding": "adjustment-second-browser-device",
                },
            )
            assert second_redeem.status_code == 200
            second_session_id = second_redeem.json()["session_id"]
            second_patient_headers = {
                "X-Session-Token": second_redeem.json()["patient_session_token"]
            }

            second_started = await client.post(
                f"/api/sessions/{second_session_id}/start",
                headers={
                    **doctor_headers,
                    "Idempotency-Key": "start-second-session",
                },
                json={
                    "consent_confirmed": True,
                    "consent_version": "v1",
                    "assessment_mode": "reuse_previous",
                },
            )
            assert second_started.status_code == 200
            assert second_started.json()["status"] == "active"

            reset_usage = await client.get(
                f"/api/patient-sessions/{second_session_id}/adjustment-requests",
                headers=second_patient_headers,
            )
            assert reset_usage.status_code == 200
            assert reset_usage.json()["used"] == 0
            assert reset_usage.json()["limit"] == 3
            assert reset_usage.json()["has_pending"] is False

            first_in_second_session = await client.post(
                f"/api/patient-sessions/{second_session_id}/adjustment-requests",
                headers={
                    **second_patient_headers,
                    "Idempotency-Key": "second-session-first-adjustment",
                },
                json={"instruction": "Make the background a little softer"},
            )
            assert first_in_second_session.status_code == 201
            assert first_in_second_session.json()["sequence_no"] == 1
            assert first_in_second_session.json()["used"] == 1

        async with factory() as session:
            assert await session.scalar(select(func.count(AdjustmentRequest.request_id))) == 4
            blocked_audit = await session.scalar(
                select(AuditLog).where(AuditLog.action == "adjustment.risk_blocked")
            )
            assert blocked_audit is not None
            assert "自残" not in str(blocked_audit.metadata_json)
    finally:
        app.dependency_overrides.clear()
        settings.model_provider = original_model_provider
        settings.semantic_image_safety_provider = original_semantic_safety_provider
        await engine.dispose()
