from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_db_session
from app.domain.enums import ApprovalStatus, Role
from app.main import app
from app.models import Base, StaffUser
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
            denied_after_end = await client.get(
                f"/api/sessions/{session_id}", headers=patient_headers
            )
            assert denied_after_end.status_code == 404

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
