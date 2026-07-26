from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_db_session
from app.config.settings import get_settings
from app.domain.enums import ApprovalStatus, Role
from app.main import app
from app.models import (
    AuditLog,
    AvatarVersion,
    Base,
    ClinicalCase,
    PatientSession,
    StaffUser,
)
from app.security.crypto import derive_patient_token, hash_password
from app.services.example_data import seed_example_data


@pytest.mark.asyncio
async def test_review_authorize_rollback_snapshots_and_download(tmp_path) -> None:
    settings = get_settings()
    original_storage_provider = settings.storage_provider
    original_image_dir = settings.local_image_dir
    original_dispatch_mode = settings.generation_dispatch_mode
    original_model_provider = settings.model_provider
    original_semantic_safety_provider = settings.semantic_image_safety_provider
    settings.storage_provider = "local"
    settings.local_image_dir = str(tmp_path / "images")
    settings.generation_dispatch_mode = "inline"
    settings.model_provider = "mock"
    settings.semantic_image_safety_provider = "mock"

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'versions.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        doctor = StaffUser(
            email="version-doctor@example.com",
            password_hash=hash_password("safe-password-2026"),
            display_name="版本审核医生",
            role=Role.DOCTOR,
            email_verified=True,
            approval_status=ApprovalStatus.APPROVED,
            is_active=True,
            created_at=datetime.now(UTC),
        )
        session.add(doctor)
        await session.flush()
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
                json={"email": "version-doctor@example.com", "password": "safe-password-2026"},
            )
            doctor_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            existing = await client.get(
                f"/api/cases/{case_id}/avatar-versions", headers=doctor_headers
            )
            legacy_id = existing.json()["items"][0]["version_id"]

            generated = await client.post(
                f"/api/cases/{case_id}/avatar-generations",
                headers={**doctor_headers, "Idempotency-Key": "generate-snapshot-version"},
                json={"mode": "same_features_regenerate"},
            )
            assert generated.status_code == 202
            generated_id = generated.json()["version_id"]
            assert generated.json()["generation_status"] == "pending_doctor_review"
            assert generated.json()["snapshot_available"] is True

            reviewed = await client.post(
                f"/api/avatar-versions/{generated_id}/review",
                headers={**doctor_headers, "Idempotency-Key": "review-snapshot-version"},
                json={"decision": "approve"},
            )
            assert reviewed.status_code == 200
            assert reviewed.json()["is_authorized"] is False

            patient_still_sees_legacy = await client.get(
                f"/api/patient-sessions/{session_id}/avatar", headers=patient_headers
            )
            assert patient_still_sees_legacy.status_code == 200
            assert patient_still_sees_legacy.json()["version_id"] == legacy_id

            authorized = await client.post(
                f"/api/avatar-versions/{generated_id}/authorize",
                headers={**doctor_headers, "Idempotency-Key": "authorize-snapshot-version"},
                json={"session_id": str(session_id)},
            )
            assert authorized.status_code == 200
            assert authorized.json()["is_authorized"] is True

            protected_delete = await client.post(
                f"/api/avatar-versions/{generated_id}/delete",
                headers={**doctor_headers, "Idempotency-Key": "delete-authorized-version"},
                json={"confirmation": "DELETE_UNAUTHORIZED_AVATAR_VERSION"},
            )
            assert protected_delete.status_code == 409
            assert (
                protected_delete.json()["error"]["code"]
                == "AUTHORIZED_VERSION_DELETE_FORBIDDEN"
            )

            reject_candidate = await client.post(
                f"/api/cases/{case_id}/avatar-generations",
                headers={**doctor_headers, "Idempotency-Key": "generate-rejected-version"},
                json={"mode": "same_features_regenerate"},
            )
            assert reject_candidate.status_code == 202
            rejected_id = reject_candidate.json()["version_id"]
            rejected = await client.post(
                f"/api/avatar-versions/{rejected_id}/review",
                headers={**doctor_headers, "Idempotency-Key": "reject-and-delete-version"},
                json={"decision": "reject"},
            )
            assert rejected.status_code == 200
            assert rejected.json()["generation_status"] == "rejected"
            assert rejected.json()["image_url"] is None
            rejected_replay = await client.post(
                f"/api/avatar-versions/{rejected_id}/review",
                headers={**doctor_headers, "Idempotency-Key": "reject-and-delete-version"},
                json={"decision": "reject"},
            )
            assert rejected_replay.status_code == 200
            assert rejected_replay.json() == rejected.json()
            remaining = await client.get(
                f"/api/cases/{case_id}/avatar-versions", headers=doctor_headers
            )
            assert rejected_id not in {
                item["version_id"] for item in remaining.json()["items"]
            }

            changed = await client.put(
                f"/api/sessions/{session_id}/voice-features/voice_gender",
                headers={**doctor_headers, "Idempotency-Key": "change-after-version"},
                json={"value": "female", "source": "doctor_interview"},
            )
            assert changed.status_code == 200

            downloaded = await client.get(
                f"/api/cases/{case_id}/avatar-versions/{generated_id}/download",
                headers=doctor_headers,
            )
            assert downloaded.status_code == 200
            assert downloaded.headers["content-type"] == "application/zip"
            with zipfile.ZipFile(io.BytesIO(downloaded.content)) as bundle:
                assert set(bundle.namelist()) == {"avatar.png", "q1-q8.json"}
                snapshot = json.loads(bundle.read("q1-q8.json"))
                assert snapshot["q1_q8"]["voice_gender"] == "male"
                assert bundle.read("avatar.png").startswith(b"\x89PNG\r\n\x1a\n")
                assert "prompt" not in json.dumps(snapshot).lower()

            rollback = await client.post(
                f"/api/avatar-versions/{legacy_id}/rollback",
                headers={**doctor_headers, "Idempotency-Key": "rollback-to-legacy"},
                json={"session_id": str(session_id)},
            )
            assert rollback.status_code == 200
            assert rollback.json()["generation_status"] == "pending_doctor_review"
            assert rollback.json()["doctor_review_status"] == "pending_re_review"

            no_avatar_during_re_review = await client.get(
                f"/api/patient-sessions/{session_id}/avatar", headers=patient_headers
            )
            assert no_avatar_during_re_review.status_code == 409

            bypass_review = await client.post(
                f"/api/avatar-versions/{legacy_id}/authorize",
                headers={**doctor_headers, "Idempotency-Key": "bypass-rollback-review"},
                json={"session_id": str(session_id)},
            )
            assert bypass_review.status_code == 409

            re_reviewed = await client.post(
                f"/api/avatar-versions/{legacy_id}/review",
                headers={**doctor_headers, "Idempotency-Key": "re-review-legacy"},
                json={"decision": "approve"},
            )
            assert re_reviewed.status_code == 200
            assert re_reviewed.json()["is_authorized"] is False

            still_hidden = await client.get(
                f"/api/patient-sessions/{session_id}/avatar", headers=patient_headers
            )
            assert still_hidden.status_code == 409

            reauthorized = await client.post(
                f"/api/avatar-versions/{legacy_id}/authorize",
                headers={**doctor_headers, "Idempotency-Key": "reauthorize-legacy"},
                json={"session_id": str(session_id)},
            )
            assert reauthorized.status_code == 200
            assert reauthorized.json()["is_authorized"] is True

            detail = await client.get(
                f"/api/cases/{case_id}/avatar-versions/{legacy_id}",
                headers=doctor_headers,
            )
            assert detail.status_code == 200
            assert detail.json()["voice_features_snapshot"]["voice_gender"] == "male"

            revoked = await client.post(
                f"/api/cases/{case_id}/authorization/revoke",
                headers={**doctor_headers, "Idempotency-Key": "manual-revoke-legacy"},
                json={
                    "session_id": str(session_id),
                    "reason": "doctor_manual_revoke",
                },
            )
            assert revoked.status_code == 200
            assert revoked.json()["revoked_count"] == 1
            hidden_after_revoke = await client.get(
                f"/api/patient-sessions/{session_id}/avatar", headers=patient_headers
            )
            assert hidden_after_revoke.status_code == 409

            async with factory() as verification_session:
                generated_before_delete = await verification_session.get(
                    AvatarVersion, UUID(generated_id)
                )
                assert generated_before_delete is not None
                assert generated_before_delete.semantic_safety_provider == "mock"
                assert generated_before_delete.semantic_safety_model == "mock-semantic-safety-v1"
                assert generated_before_delete.semantic_safety_categories_json == []

            deleted = await client.post(
                f"/api/avatar-versions/{generated_id}/delete",
                headers={**doctor_headers, "Idempotency-Key": "delete-revoked-version"},
                json={
                    "confirmation": "DELETE_UNAUTHORIZED_AVATAR_VERSION",
                    "reason": "lifecycle_test",
                },
            )
            assert deleted.status_code == 200
            assert deleted.json()["deleted"] is True
            assert deleted.json()["version_id"] == generated_id
            deleted_replay = await client.post(
                f"/api/avatar-versions/{generated_id}/delete",
                headers={**doctor_headers, "Idempotency-Key": "delete-revoked-version"},
                json={
                    "confirmation": "DELETE_UNAUTHORIZED_AVATAR_VERSION",
                    "reason": "lifecycle_test",
                },
            )
            assert deleted_replay.status_code == 200
            assert deleted_replay.json() == deleted.json()

        async with factory() as session:
            generated_version = await session.get(AvatarVersion, UUID(generated_id))
            download_audit = await session.scalar(
                select(AuditLog).where(AuditLog.action == "avatar.downloaded")
            )
            rollback_audit = await session.scalar(
                select(AuditLog).where(AuditLog.action == "avatar.rollback_requested")
            )
            assert generated_version is None
            assert download_audit is not None
            assert rollback_audit is not None
    finally:
        app.dependency_overrides.clear()
        settings.storage_provider = original_storage_provider
        settings.local_image_dir = original_image_dir
        settings.generation_dispatch_mode = original_dispatch_mode
        settings.model_provider = original_model_provider
        settings.semantic_image_safety_provider = original_semantic_safety_provider
        await engine.dispose()
