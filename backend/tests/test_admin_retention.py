from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_db_session
from app.config.settings import get_settings
from app.domain.enums import ApprovalStatus, CaseStatus, RetentionStatus, Role
from app.main import app
from app.models import (
    AdjustmentRequest,
    Base,
    ClinicalCase,
    PatientSession,
    RetentionJob,
    StaffUser,
)
from app.security.crypto import hash_password, hash_secret
from app.services.example_data import seed_example_data
from app.services.retention import process_due_retention_jobs
from app.services.risk_engine import seed_default_risk_rules


def staff_user(
    email: str,
    role: Role,
    *,
    approval: ApprovalStatus = ApprovalStatus.APPROVED,
    active: bool = True,
) -> StaffUser:
    return StaffUser(
        email=email,
        password_hash=hash_password("safe-password-2026"),
        display_name=email.split("@")[0],
        role=role,
        email_verified=True,
        approval_status=approval,
        is_active=active,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_admin_access_rules_audit_restore_and_permanent_delete(
    tmp_path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'admin.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        session.add_all(
            [
                staff_user("admin-flow@example.com", Role.ADMIN),
                staff_user(
                    "pending-flow@example.com",
                    Role.DOCTOR,
                    approval=ApprovalStatus.PENDING,
                ),
                staff_user("owner-flow@example.com", Role.DOCTOR),
            ]
        )
        await seed_default_risk_rules(session)
        await session.commit()

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            admin_login = await client.post(
                "/api/auth/login",
                json={"email": "admin-flow@example.com", "password": "safe-password-2026"},
            )
            assert admin_login.status_code == 200
            admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
            pending_login = await client.post(
                "/api/auth/login",
                json={"email": "pending-flow@example.com", "password": "safe-password-2026"},
            )
            assert pending_login.status_code == 401

            doctors = await client.get("/api/admin/doctors", headers=admin_headers)
            pending = next(
                item
                for item in doctors.json()["items"]
                if item["email"] == "pending-flow@example.com"
            )
            approved = await client.patch(
                f"/api/admin/doctors/{pending['user_id']}",
                headers={**admin_headers, "Idempotency-Key": "approve-pending-doctor"},
                json={"approval_status": "approved"},
            )
            assert approved.json()["approval_status"] == "approved"
            pending_login = await client.post(
                "/api/auth/login",
                json={"email": "pending-flow@example.com", "password": "safe-password-2026"},
            )
            doctor_headers = {"Authorization": f"Bearer {pending_login.json()['access_token']}"}
            forbidden = await client.get("/api/admin/stats", headers=doctor_headers)
            assert forbidden.status_code == 404

            disabled = await client.patch(
                f"/api/admin/doctors/{pending['user_id']}",
                headers={**admin_headers, "Idempotency-Key": "disable-approved-doctor"},
                json={"is_active": False},
            )
            assert disabled.json()["is_active"] is False
            revoked_session = await client.get("/api/users/me", headers=doctor_headers)
            assert revoked_session.status_code == 401

            rules = await client.get("/api/admin/risk-rules", headers=admin_headers)
            first_rule = rules.json()["items"][0]
            updated_rule = await client.put(
                f"/api/admin/risk-rules/{first_rule['rule_id']}",
                headers={**admin_headers, "Idempotency-Key": "update-risk-version"},
                json={"is_enabled": False, "version": "RISK-V1.4"},
            )
            assert updated_rule.json()["version"] == "RISK-V1.4"
            assert updated_rule.json()["is_enabled"] is False
            refreshed_rules = await client.get("/api/admin/risk-rules", headers=admin_headers)
            assert {item["version"] for item in refreshed_rules.json()["items"]} == {"RISK-V1.4"}

            owner_login = await client.post(
                "/api/auth/login",
                json={"email": "owner-flow@example.com", "password": "safe-password-2026"},
            )
            owner_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}
            created = await client.post(
                "/api/cases",
                headers={**owner_headers, "Idempotency-Key": "admin-restore-case-create"},
                json={"study_code": "ADMIN-RESTORE-001"},
            )
            case_id = created.json()["case_id"]
            archived = await client.post(
                f"/api/cases/{case_id}/archive",
                headers={**owner_headers, "Idempotency-Key": "admin-restore-case-archive"},
                json={"reason": "lifecycle_test"},
            )
            original_due = archived.json()["retention_due_at"]

            archived_cases = await client.get("/api/admin/archived-cases", headers=admin_headers)
            archived_item = next(
                item for item in archived_cases.json()["items"] if item["case_id"] == case_id
            )
            assert archived_item["study_code"] == "ADMIN-RESTORE-001"
            restored = await client.post(
                f"/api/admin/cases/{case_id}/restore",
                headers={**admin_headers, "Idempotency-Key": "admin-case-restore"},
                json={"reason": "approved_restore"},
            )
            assert restored.json()["status"] == "draft"
            assert datetime.fromisoformat(
                restored.json()["retention_due_at"].replace("Z", "+00:00")
            ).replace(tzinfo=None) == datetime.fromisoformat(
                original_due.replace("Z", "+00:00")
            ).replace(tzinfo=None)
            rearchived = await client.post(
                f"/api/cases/{case_id}/archive",
                headers={**owner_headers, "Idempotency-Key": "admin-case-rearchive"},
                json={"reason": "rearchive"},
            )
            assert datetime.fromisoformat(
                rearchived.json()["retention_due_at"].replace("Z", "+00:00")
            ).replace(tzinfo=None) == datetime.fromisoformat(
                original_due.replace("Z", "+00:00")
            ).replace(tzinfo=None)
            invalid_delete = await client.post(
                f"/api/admin/cases/{case_id}/permanent-delete",
                headers={
                    **admin_headers,
                    "Idempotency-Key": "admin-case-invalid-delete",
                },
                json={"confirmation": "DELETE"},
            )
            assert invalid_delete.status_code == 422
            delete_headers = {
                **admin_headers,
                "Idempotency-Key": "admin-case-permanent-delete",
            }
            permanently_deleted = await client.post(
                f"/api/admin/cases/{case_id}/permanent-delete",
                headers=delete_headers,
                json={
                    "confirmation": "PERMANENTLY_DELETE_ARCHIVED_CASE",
                    "reason": "test_cleanup",
                },
            )
            assert permanently_deleted.status_code == 202
            assert permanently_deleted.json()["status"] == "scheduled"
            assert permanently_deleted.json()["retention_job_id"]

            async with factory() as retention_session:
                deletion_result = await process_due_retention_jobs(retention_session)
                assert deletion_result == {
                    "processed": 1,
                    "completed": 1,
                    "retrying": 0,
                    "failed": 0,
                }

            replayed_delete = await client.post(
                f"/api/admin/cases/{case_id}/permanent-delete",
                headers=delete_headers,
                json={
                    "confirmation": "PERMANENTLY_DELETE_ARCHIVED_CASE",
                    "reason": "test_cleanup",
                },
            )
            assert replayed_delete.json() == permanently_deleted.json()
            remaining_archived = await client.get(
                "/api/admin/archived-cases", headers=admin_headers
            )
            assert all(
                item["case_id"] != case_id
                for item in remaining_archived.json()["items"]
            )

            stats = await client.get("/api/admin/stats", headers=admin_headers)
            assert stats.status_code == 200
            assert stats.json()["doctors"]["total"] == 2
            assert "items" not in stats.json()["cases"]
            assert "generations" in stats.json()
            assert "generation_success_rate" in stats.json()
            assert isinstance(stats.json()["alerts"], list)
            audits = await client.get("/api/admin/audit-logs", headers=admin_headers)
            assert audits.status_code == 200
            serialized = str(audits.json())
            assert "study_code" not in serialized
            assert "submitted_text" not in serialized
            assert all("case_id" not in item for item in audits.json()["items"])
            assert any(
                item["action"] == "retention.case_permanently_deleted"
                for item in audits.json()["items"]
            )
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest.mark.asyncio
async def test_due_retention_deletes_case_data_and_retries_failures(tmp_path) -> None:
    settings = get_settings()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retention.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    now = datetime.now(UTC)
    async with factory() as session:
        doctor = staff_user("retention-doctor@example.com", Role.DOCTOR)
        session.add(doctor)
        await session.flush()
        await seed_default_risk_rules(session)
        await seed_example_data(session, doctor, settings)
        case = await session.scalar(
            select(ClinicalCase).where(ClinicalCase.study_code == "DEMO-VOICE-001")
        )
        assert case is not None
        case.status = CaseStatus.ARCHIVED
        case.archived_at = now - timedelta(days=31)
        case.retention_started_at = case.archived_at
        case.retention_due_at = now - timedelta(days=1)
        job = RetentionJob(
            case_id=case.case_id,
            case_reference_hash=hash_secret(
                str(case.case_id), settings.secret_key, "retention-case-reference"
            ),
            retention_started_at=case.retention_started_at,
            retention_due_at=case.retention_due_at,
            status=RetentionStatus.SCHEDULED,
            attempt_count=0,
        )
        session.add(job)
        await session.commit()
        deleted_case_id = case.case_id
        job_id = job.retention_job_id

        result = await process_due_retention_jobs(session, now=now)
        assert result == {"processed": 1, "completed": 1, "retrying": 0, "failed": 0}
        assert await session.get(ClinicalCase, deleted_case_id) is None
        assert (
            await session.scalar(
                select(func.count(PatientSession.session_id)).where(
                    PatientSession.case_id == deleted_case_id
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count(AdjustmentRequest.request_id)).where(
                    AdjustmentRequest.case_id == deleted_case_id
                )
            )
            == 0
        )
        completed = await session.get(RetentionJob, job_id)
        assert completed is not None
        assert completed.status == RetentionStatus.COMPLETED
        assert completed.case_id is None
        assert completed.deleted_categories_json["cases"] == 1

        failing_case = ClinicalCase(
            owner_doctor_id=doctor.user_id,
            study_code="RETENTION-FAILURE-001",
            status=CaseStatus.ARCHIVED,
            archived_at=now - timedelta(days=31),
            retention_started_at=now - timedelta(days=31),
            retention_due_at=now - timedelta(days=1),
            created_at=now - timedelta(days=31),
            updated_at=now,
        )
        session.add(failing_case)
        await session.flush()
        failing_job = RetentionJob(
            case_id=failing_case.case_id,
            case_reference_hash=hash_secret(
                str(failing_case.case_id), settings.secret_key, "retention-case-reference"
            ),
            retention_started_at=failing_case.retention_started_at,
            retention_due_at=failing_case.retention_due_at,
            status=RetentionStatus.SCHEDULED,
            attempt_count=0,
        )
        session.add(failing_job)
        await session.commit()

        async def failing_cleanup(case_id):
            del case_id
            raise RuntimeError("object store unavailable")

        for expected_status in (
            RetentionStatus.RETRYING,
            RetentionStatus.RETRYING,
            RetentionStatus.FAILED,
        ):
            await process_due_retention_jobs(session, now=now, object_cleanup=failing_cleanup)
            refreshed = await session.get(RetentionJob, failing_job.retention_job_id)
            assert refreshed.status == expected_status
        assert await session.get(ClinicalCase, failing_case.case_id) is not None
        assert refreshed.attempt_count == 3
        assert refreshed.last_error_code == "RETENTION_DEPENDENCY_OR_DELETE_FAILED"

    await engine.dispose()


@pytest.mark.asyncio
async def test_stale_running_manual_delete_is_recovered_and_run_immediately(tmp_path) -> None:
    settings = get_settings()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'stale-retention.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    now = datetime.now(UTC)
    async with factory() as session:
        doctor = staff_user("stale-retention@example.com", Role.DOCTOR)
        session.add(doctor)
        await session.flush()
        case = ClinicalCase(
            owner_doctor_id=doctor.user_id,
            study_code="STALE-RETENTION-001",
            status=CaseStatus.ARCHIVED,
            archived_at=now - timedelta(days=1),
            retention_started_at=now - timedelta(days=1),
            retention_due_at=now + timedelta(days=29),
            created_at=now - timedelta(days=1),
            updated_at=now,
        )
        session.add(case)
        await session.flush()
        job = RetentionJob(
            case_id=case.case_id,
            case_reference_hash=hash_secret(
                str(case.case_id), settings.secret_key, "retention-case-reference"
            ),
            retention_started_at=case.retention_started_at,
            retention_due_at=case.retention_due_at,
            status=RetentionStatus.RUNNING,
            attempt_count=1,
            last_attempt_at=now - timedelta(minutes=10),
        )
        session.add(job)
        await session.commit()
        case_id = case.case_id
        job_id = job.retention_job_id

        result = await process_due_retention_jobs(session, now=now)

        assert result == {"processed": 1, "completed": 1, "retrying": 0, "failed": 0}
        assert await session.get(ClinicalCase, case_id) is None
        completed = await session.get(RetentionJob, job_id)
        assert completed is not None
        assert completed.status == RetentionStatus.COMPLETED
        assert completed.attempt_count == 2
        assert completed.last_error_code is None

    await engine.dispose()
