from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_db_session
from app.domain.enums import (
    ApprovalStatus,
    GenerationMode,
    GenerationStatus,
    Role,
)
from app.main import app
from app.models import AvatarVersion, Base, StaffUser
from app.security.crypto import hash_password


@pytest.mark.asyncio
async def test_doctor_case_invite_and_supervised_session_flow(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'flow.db'}"
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        session.add(
            StaffUser(
                email="flow-doctor@example.com",
                password_hash=hash_password("safe-password-2026"),
                display_name="流程医生",
                role=Role.DOCTOR,
                email_verified=True,
                approval_status=ApprovalStatus.APPROVED,
                is_active=True,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            login = await client.post(
                "/api/auth/login",
                json={"email": "flow-doctor@example.com", "password": "safe-password-2026"},
            )
            assert login.status_code == 200
            doctor_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            missing_key = await client.post(
                "/api/cases", headers=doctor_headers, json={"study_code": "ST-FLOW-001"}
            )
            assert missing_key.status_code == 400
            assert missing_key.json()["error"]["code"] == "INVALID_REQUEST"

            create_headers = {**doctor_headers, "Idempotency-Key": "create-flow-case"}
            created = await client.post(
                "/api/cases", headers=create_headers, json={"study_code": "ST-FLOW-001"}
            )
            assert created.status_code == 201
            case_id = created.json()["case_id"]
            replay = await client.post(
                "/api/cases", headers=create_headers, json={"study_code": "ST-FLOW-001"}
            )
            assert replay.json()["case_id"] == case_id

            cancelled_invite = await client.post(
                f"/api/cases/{case_id}/session-invites",
                headers={**doctor_headers, "Idempotency-Key": "create-cancelled-invite"},
                json={"expires_in_hours": 24},
            )
            cancelled = await client.delete(
                f"/api/session-invites/{cancelled_invite.json()['invite_id']}",
                headers={**doctor_headers, "Idempotency-Key": "cancel-unused-invite"},
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "revoked"

            invite = await client.post(
                f"/api/cases/{case_id}/session-invites",
                headers={**doctor_headers, "Idempotency-Key": "create-flow-invite"},
                json={"expires_in_hours": 24},
            )
            assert invite.status_code == 201
            invite_code = invite.json()["code"]

            redeem = await client.post(
                "/api/session-invites/redeem",
                headers={"Idempotency-Key": "redeem-flow-invite"},
                json={"code": invite_code, "device_binding": "flow-browser-device-0001"},
            )
            assert redeem.status_code == 200
            session_id = redeem.json()["session_id"]
            patient_headers = {"X-Session-Token": redeem.json()["patient_session_token"]}

            listed_invites = await client.get(
                f"/api/cases/{case_id}/session-invites",
                headers=doctor_headers,
            )
            listed_by_id = {
                item["invite_id"]: item for item in listed_invites.json()["items"]
            }
            assert listed_by_id[invite.json()["invite_id"]]["code"] == invite_code
            assert cancelled_invite.json()["invite_id"] not in listed_by_id

            case_with_session = await client.get(
                f"/api/cases/{case_id}", headers=doctor_headers
            )
            assert case_with_session.json()["active_session_count"] == 1
            assert case_with_session.json()["total_session_count"] == 1

            waiting = await client.get(f"/api/sessions/{session_id}", headers=patient_headers)
            assert waiting.json()["status"] == "waiting_doctor"
            assert waiting.json()["study_code"] is None

            consent_required = await client.post(
                f"/api/sessions/{session_id}/start",
                headers={**doctor_headers, "Idempotency-Key": "start-without-consent"},
                json={"consent_confirmed": False, "consent_version": "v1"},
            )
            assert consent_required.status_code == 422

            started = await client.post(
                f"/api/sessions/{session_id}/start",
                headers={**doctor_headers, "Idempotency-Key": "start-with-consent"},
                json={"consent_confirmed": True, "consent_version": "v1"},
            )
            assert started.json()["status"] == "active"

            answers = {
                "voice_gender": "male",
                "age_sense": "young",
                "pitch_level": 3,
                "speaking_rate_level": 2,
                "timbre": "low_rich",
                "emotions": ["sadness", "indifference"],
                "power_level": 3,
                "malice_level": 1,
            }
            for index, (question_key, value) in enumerate(answers.items(), start=1):
                saved = await client.put(
                    f"/api/sessions/{session_id}/voice-features/{question_key}",
                    headers={
                        **doctor_headers,
                        "Idempotency-Key": f"save-question-{index}",
                    },
                    json={"value": value, "source": "doctor_interview"},
                )
                assert saved.status_code == 200
                assert saved.json()["completed_count"] == index

            form = await client.get(f"/api/cases/{case_id}/voice-features", headers=doctor_headers)
            assert form.json()["complete"] is True
            assert form.json()["answers"]["emotions"] == ["sadness", "indifference"]

            extracted = await client.post(
                f"/api/cases/{case_id}/extract-features",
                headers={**doctor_headers, "Idempotency-Key": "extract-features"},
                json={"session_id": session_id},
            )
            assert extracted.status_code == 200
            visual = await client.get(
                f"/api/cases/{case_id}/visual-features", headers=doctor_headers
            )
            assert visual.status_code == 200
            assert (
                visual.json()["mapping_explanation"]["initial_risk_classification_performed"]
                is False
            )
            assert "柔" in visual.json()["system_result"]["lighting"]

            effective = visual.json()["effective_features"]
            effective["lighting"] = visual.json()["controlled_options"]["lighting"][0]
            confirmed = await client.put(
                f"/api/cases/{case_id}/visual-features",
                headers={**doctor_headers, "Idempotency-Key": "confirm-visual"},
                json={
                    "effective_features": effective,
                    "restore_system_result": False,
                    "doctor_confirmed": True,
                },
            )
            assert confirmed.status_code == 200
            assert confirmed.json()["is_doctor_confirmed"] is True
            assert confirmed.json()["doctor_edited"] == {"lighting": effective["lighting"]}

            unchanged = await client.put(
                f"/api/sessions/{session_id}/voice-features/voice_gender",
                headers={**doctor_headers, "Idempotency-Key": "save-unchanged-question"},
                json={"value": "male", "source": "doctor_interview"},
            )
            assert unchanged.status_code == 200
            still_confirmed = await client.get(
                f"/api/cases/{case_id}/visual-features", headers=doctor_headers
            )
            assert still_confirmed.json()["is_doctor_confirmed"] is True

            async with session_factory() as session:
                generated_version = AvatarVersion(
                    case_id=UUID(case_id),
                    source_visual_feature_id=UUID(
                        confirmed.json()["visual_feature_id"]
                    ),
                    voice_features_snapshot_json=answers,
                    visual_features_snapshot_json=effective,
                    generation_round=1,
                    generation_mode=GenerationMode.INITIAL,
                    generation_status=GenerationStatus.QUEUED,
                    image_object_key=None,
                    provider_kind="mock",
                    provider_model="mock-avatar-v1",
                    prompt_template_version="test",
                    prompt_sha256=b"test-prompt",
                    safety_status="pending",
                    doctor_review_status="pending",
                    is_current_candidate=True,
                    created_at=datetime.now(UTC),
                )
                session.add(generated_version)
                await session.commit()
                generated_version_id = generated_version.version_id

            patient_generation_stage = await client.get(
                f"/api/sessions/{session_id}",
                headers=patient_headers,
            )
            assert patient_generation_stage.json()["stage"] == "image_generation"

            async with session_factory() as session:
                generated_version = await session.get(
                    AvatarVersion,
                    generated_version_id,
                )
                assert generated_version is not None
                generated_version.generation_status = (
                    GenerationStatus.PENDING_DOCTOR_REVIEW
                )
                await session.commit()

            patient_review_stage = await client.get(
                f"/api/sessions/{session_id}",
                headers=patient_headers,
            )
            assert patient_review_stage.json()["stage"] == "image_review"

            paused = await client.post(
                f"/api/patient-sessions/{session_id}/pause",
                headers={**patient_headers, "Idempotency-Key": "patient-safety-pause"},
                json={"reason": "patient_requested"},
            )
            assert paused.json()["status"] == "paused"

            resumed = await client.post(
                f"/api/sessions/{session_id}/resume",
                headers={**doctor_headers, "Idempotency-Key": "doctor-resume"},
                json={},
            )
            assert resumed.json()["status"] == "active"

            ended = await client.post(
                f"/api/sessions/{session_id}/stop",
                headers={**doctor_headers, "Idempotency-Key": "doctor-stop"},
                json={"reason": "completed"},
            )
            assert ended.json()["status"] == "ended"
            case_after_end = await client.get(
                f"/api/cases/{case_id}", headers=doctor_headers
            )
            assert case_after_end.json()["active_session_count"] == 0
            assert case_after_end.json()["total_session_count"] == 1
            patient_end_status = await client.get(
                f"/api/sessions/{session_id}", headers=patient_headers
            )
            assert patient_end_status.status_code == 200
            assert patient_end_status.json()["status"] == "ended"

            denied_write_after_end = await client.post(
                f"/api/patient-sessions/{session_id}/pause",
                headers={
                    **patient_headers,
                    "Idempotency-Key": "patient-pause-after-end",
                },
                json={"reason": "patient_requested"},
            )
            assert denied_write_after_end.status_code == 404

            second_invite = await client.post(
                f"/api/cases/{case_id}/session-invites",
                headers={**doctor_headers, "Idempotency-Key": "create-reuse-invite"},
                json={"expires_in_hours": 24},
            )
            second_redeem = await client.post(
                "/api/session-invites/redeem",
                headers={"Idempotency-Key": "redeem-reuse-invite"},
                json={
                    "code": second_invite.json()["code"],
                    "device_binding": "flow-browser-device-0002",
                },
            )
            second_session_id = second_redeem.json()["session_id"]
            second_waiting = await client.get(
                f"/api/sessions/{second_session_id}",
                headers=doctor_headers,
            )
            assert second_waiting.json()["has_prior_assessment"] is True

            mode_required = await client.post(
                f"/api/sessions/{second_session_id}/start",
                headers={**doctor_headers, "Idempotency-Key": "reuse-mode-required"},
                json={"consent_confirmed": True, "consent_version": "v1"},
            )
            assert mode_required.status_code == 422
            assert mode_required.json()["error"]["code"] == "ASSESSMENT_MODE_REQUIRED"

            reused = await client.post(
                f"/api/sessions/{second_session_id}/start",
                headers={**doctor_headers, "Idempotency-Key": "start-reuse-session"},
                json={
                    "consent_confirmed": True,
                    "consent_version": "v1",
                    "assessment_mode": "reuse_previous",
                },
            )
            assert reused.status_code == 200
            assert reused.json()["assessment_mode"] == "reuse_previous"
            assert reused.json()["stage"] == "avatar_review"

            reused_session_form = await client.get(
                f"/api/sessions/{second_session_id}/voice-features",
                headers=doctor_headers,
            )
            assert reused_session_form.json()["complete"] is False
            assert reused_session_form.json()["answered_questions"] == []

            reuse_write_blocked = await client.put(
                f"/api/sessions/{second_session_id}/voice-features/voice_gender",
                headers={**doctor_headers, "Idempotency-Key": "reuse-write-blocked"},
                json={"value": "female", "source": "doctor_interview"},
            )
            assert reuse_write_blocked.status_code == 409
            assert reuse_write_blocked.json()["error"]["code"] == "ASSESSMENT_REUSED"

            original_session_form = await client.get(
                f"/api/sessions/{session_id}/voice-features",
                headers=doctor_headers,
            )
            assert original_session_form.json()["answers"] == answers

            await client.post(
                f"/api/sessions/{second_session_id}/stop",
                headers={**doctor_headers, "Idempotency-Key": "stop-reuse-session"},
                json={"reason": "completed"},
            )

            archived = await client.post(
                f"/api/cases/{case_id}/archive",
                headers={**doctor_headers, "Idempotency-Key": "archive-flow-case"},
                json={"reason": "research_complete"},
            )
            assert archived.json()["status"] == "archived"
            retention_due = datetime.fromisoformat(archived.json()["retention_due_at"])
            archived_at = datetime.fromisoformat(archived.json()["archived_at"])
            assert (retention_due - archived_at).days == 30
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
