from __future__ import annotations

import argparse
import io
import json
import time
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

TERMINAL_GENERATION_STATUSES = {
    "pending_doctor_review",
    "approved",
    "rejected",
    "failed",
    "cancelled",
}


@dataclass
class AcceptanceEvidence:
    started_at: str
    api_base: str
    site_url: str | None
    study_code: str
    checks: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, **details: Any) -> None:
        self.checks.append({"name": name, "status": "passed", **details})


class OnlineAcceptance:
    def __init__(
        self,
        *,
        api_base: str,
        site_url: str | None,
        doctor_email: str,
        doctor_password: str,
        admin_email: str,
        admin_password: str,
    ) -> None:
        self.client = httpx.Client(
            base_url=api_base.rstrip("/"),
            timeout=45,
            follow_redirects=True,
        )
        self.site_url = site_url.rstrip("/") if site_url else None
        self.doctor_email = doctor_email
        self.doctor_password = doctor_password
        self.admin_email = admin_email
        self.admin_password = admin_password
        self.run_id = uuid4().hex[:10]
        self.study_code = f"ONLINE-ACCEPT-{self.run_id.upper()}"
        self.evidence = AcceptanceEvidence(
            started_at=datetime.now(UTC).isoformat(),
            api_base=api_base.rstrip("/"),
            site_url=self.site_url,
            study_code=self.study_code,
        )

    def close(self) -> None:
        self.client.close()

    def idempotency(self, operation: str) -> str:
        return f"accept-{self.run_id}-{operation}"

    @staticmethod
    def expect(response: httpx.Response, expected: int, name: str) -> httpx.Response:
        if response.status_code != expected:
            body = response.text[:500]
            raise RuntimeError(
                f"{name}: expected HTTP {expected}, got {response.status_code}: {body}"
            )
        return response

    def login(self, email: str, password: str) -> dict[str, str]:
        response = self.expect(
            self.client.post(
                "/auth/login",
                json={"email": email, "password": password},
            ),
            200,
            f"login {email}",
        )
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def keyed(self, headers: dict[str, str], operation: str) -> dict[str, str]:
        return {**headers, "Idempotency-Key": self.idempotency(operation)}

    def wait_for_generation(
        self,
        *,
        case_id: str,
        version_id: str,
        doctor_headers: dict[str, str],
        timeout_seconds: int = 120,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            response = self.expect(
                self.client.get(
                    f"/cases/{case_id}/avatar-versions/{version_id}",
                    headers=doctor_headers,
                ),
                200,
                "poll generation",
            )
            payload = response.json()
            if payload["generation_status"] in TERMINAL_GENERATION_STATUSES:
                return payload
            time.sleep(1)
        raise RuntimeError(f"generation {version_id} did not finish within {timeout_seconds}s")

    def run(self) -> AcceptanceEvidence:
        if self.site_url:
            site = httpx.get(self.site_url, timeout=30, follow_redirects=True)
            self.expect(site, 200, "Netlify site")
            self.evidence.add("netlify_site", http_status=site.status_code)

        readiness = self.expect(
            self.client.get("/health/ready"),
            200,
            "readiness",
        ).json()
        if readiness["status"] != "ready":
            raise RuntimeError(f"backend readiness is {readiness['status']}")
        self.evidence.add("backend_readiness", dependencies=readiness["dependencies"])

        doctor_headers = self.login(self.doctor_email, self.doctor_password)
        admin_headers = self.login(self.admin_email, self.admin_password)
        self.evidence.add("staff_authentication")

        created_case = self.expect(
            self.client.post(
                "/cases",
                headers=self.keyed(doctor_headers, "case-create"),
                json={"study_code": self.study_code},
            ),
            201,
            "create case",
        ).json()
        case_id = created_case["case_id"]
        self.evidence.add("case_created", case_id=case_id)

        invite = self.expect(
            self.client.post(
                f"/cases/{case_id}/session-invites",
                headers=self.keyed(doctor_headers, "invite-create"),
                json={"expires_in_hours": 24},
            ),
            201,
            "create invite",
        ).json()
        redeemed = self.expect(
            self.client.post(
                "/session-invites/redeem",
                headers={"Idempotency-Key": self.idempotency("invite-redeem")},
                json={
                    "code": invite["code"],
                    "device_binding": f"online-acceptance-{self.run_id}",
                },
            ),
            200,
            "redeem invite",
        ).json()
        session_id = redeemed["session_id"]
        patient_headers = {"X-Session-Token": redeemed["patient_session_token"]}
        self.evidence.add("invite_redeemed", session_id=session_id)

        started = self.expect(
            self.client.post(
                f"/sessions/{session_id}/start",
                headers=self.keyed(doctor_headers, "session-start"),
                json={"consent_confirmed": True, "consent_version": "v1"},
            ),
            200,
            "start session",
        ).json()
        if started["status"] != "active":
            raise RuntimeError("session did not become active")
        self.evidence.add("supervised_session_started")

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
            saved = self.expect(
                self.client.put(
                    f"/sessions/{session_id}/voice-features/{question_key}",
                    headers=self.keyed(doctor_headers, f"q{index}-save"),
                    json={"value": value, "source": "doctor_interview"},
                ),
                200,
                f"save {question_key}",
            ).json()
            if saved["completed_count"] != index:
                raise RuntimeError(f"unexpected completion count for {question_key}")
        self.evidence.add("q1_q8_completed", emotions_count=len(answers["emotions"]))

        self.expect(
            self.client.post(
                f"/cases/{case_id}/extract-features",
                headers=self.keyed(doctor_headers, "feature-extract"),
                json={"session_id": session_id},
            ),
            200,
            "extract features",
        )
        visual = self.expect(
            self.client.get(
                f"/cases/{case_id}/visual-features",
                headers=doctor_headers,
            ),
            200,
            "get visual features",
        ).json()
        self.expect(
            self.client.put(
                f"/cases/{case_id}/visual-features",
                headers=self.keyed(doctor_headers, "visual-confirm"),
                json={
                    "effective_features": visual["effective_features"],
                    "restore_system_result": False,
                    "doctor_confirmed": True,
                },
            ),
            200,
            "confirm visual features",
        )
        self.evidence.add("voice_to_visual_mapping_confirmed")

        initial = self.expect(
            self.client.post(
                f"/cases/{case_id}/avatar-generations",
                headers=self.keyed(doctor_headers, "initial-generate"),
                json={"mode": "initial"},
            ),
            202,
            "create initial generation",
        ).json()
        initial_version_id = initial["version_id"]
        initial = self.wait_for_generation(
            case_id=case_id,
            version_id=initial_version_id,
            doctor_headers=doctor_headers,
        )
        if (
            initial["generation_status"] != "pending_doctor_review"
            or initial["safety_status"] != "passed"
        ):
            raise RuntimeError(f"initial generation failed: {initial}")
        self.evidence.add("initial_generation_safety_passed", version_id=initial_version_id)

        self.expect(
            self.client.post(
                f"/avatar-versions/{initial_version_id}/review",
                headers=self.keyed(doctor_headers, "initial-review"),
                json={"decision": "approve"},
            ),
            200,
            "review initial avatar",
        )
        self.expect(
            self.client.get(
                f"/patient-sessions/{session_id}/avatar",
                headers=patient_headers,
            ),
            409,
            "unapproved authorization boundary",
        )
        self.expect(
            self.client.post(
                f"/avatar-versions/{initial_version_id}/authorize",
                headers=self.keyed(doctor_headers, "initial-authorize"),
                json={"session_id": session_id},
            ),
            200,
            "authorize initial avatar",
        )
        patient_avatar = self.expect(
            self.client.get(
                f"/patient-sessions/{session_id}/avatar",
                headers=patient_headers,
            ),
            200,
            "patient reads authorized avatar",
        ).json()
        if patient_avatar["version_id"] != initial_version_id:
            raise RuntimeError("patient did not receive the authorized version")
        image = httpx.get(patient_avatar["image_url"], timeout=45, follow_redirects=True)
        self.expect(image, 200, "read signed avatar image")
        if image.headers.get("content-type") != "image/png":
            raise RuntimeError("authorized avatar is not PNG")
        self.evidence.add("doctor_review_and_patient_authorization", image_bytes=len(image.content))

        download = self.expect(
            self.client.get(
                f"/cases/{case_id}/avatar-versions/{initial_version_id}/download",
                headers=doctor_headers,
            ),
            200,
            "download approved version",
        )
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            if set(archive.namelist()) != {"avatar.png", "q1-q8.json"}:
                raise RuntimeError("download archive contains unexpected files")
            snapshot = json.loads(archive.read("q1-q8.json"))
            if snapshot["q1_q8"]["voice_gender"] != "male":
                raise RuntimeError("version snapshot changed unexpectedly")
        self.evidence.add("version_download_snapshot")

        safe_adjustment = self.expect(
            self.client.post(
                f"/patient-sessions/{session_id}/adjustment-requests",
                headers=self.keyed(patient_headers, "safe-adjustment"),
                json={"instruction": "希望背景更明亮柔和"},
            ),
            201,
            "submit safe adjustment",
        ).json()
        adjustment_id = safe_adjustment["request_id"]
        self.expect(
            self.client.post(
                f"/adjustment-requests/{adjustment_id}/review",
                headers=self.keyed(doctor_headers, "adjustment-review"),
                json={"decision": "approve_as_is"},
            ),
            200,
            "review safe adjustment",
        )
        adjusted = self.expect(
            self.client.post(
                f"/adjustment-requests/{adjustment_id}/generate",
                headers=self.keyed(doctor_headers, "adjustment-generate"),
            ),
            202,
            "generate adjusted avatar",
        ).json()
        adjusted_version_id = adjusted["version_id"]
        adjusted = self.wait_for_generation(
            case_id=case_id,
            version_id=adjusted_version_id,
            doctor_headers=doctor_headers,
        )
        if adjusted["generation_status"] != "pending_doctor_review":
            raise RuntimeError(f"adjusted generation failed: {adjusted}")
        self.expect(
            self.client.post(
                f"/avatar-versions/{adjusted_version_id}/review",
                headers=self.keyed(doctor_headers, "adjustment-avatar-review"),
                json={"decision": "approve"},
            ),
            200,
            "review adjusted avatar",
        )
        before_authorization = self.expect(
            self.client.get(
                f"/patient-sessions/{session_id}/avatar",
                headers=patient_headers,
            ),
            200,
            "patient retains old avatar",
        ).json()
        if before_authorization["version_id"] != initial_version_id:
            raise RuntimeError("patient saw a new avatar before authorization")
        self.expect(
            self.client.post(
                f"/avatar-versions/{adjusted_version_id}/authorize",
                headers=self.keyed(doctor_headers, "adjustment-authorize"),
                json={"session_id": session_id},
            ),
            200,
            "authorize adjusted avatar",
        )
        self.evidence.add("safe_adjustment_review_generation_authorization")

        blocked = self.expect(
            self.client.post(
                f"/patient-sessions/{session_id}/adjustment-requests",
                headers=self.keyed(patient_headers, "risk-adjustment"),
                json={"instruction": "我现在想自残"},
            ),
            422,
            "block crisis adjustment",
        ).json()
        if blocked["error"]["code"] != "RISK_BLOCKED":
            raise RuntimeError("risk adjustment returned the wrong error code")
        paused = self.expect(
            self.client.get(
                f"/sessions/{session_id}",
                headers=doctor_headers,
            ),
            200,
            "read paused session",
        ).json()
        if paused["status"] != "paused":
            raise RuntimeError("crisis adjustment did not pause the session")
        self.expect(
            self.client.post(
                f"/sessions/{session_id}/resume",
                headers=self.keyed(doctor_headers, "risk-resume"),
                json={"reason": "现场医生已完成安全评估"},
            ),
            200,
            "resume after safety assessment",
        )
        self.evidence.add("risk_block_and_supervised_resume")

        rollback = self.expect(
            self.client.post(
                f"/avatar-versions/{initial_version_id}/rollback",
                headers=self.keyed(doctor_headers, "version-rollback"),
                json={"session_id": session_id},
            ),
            200,
            "rollback version",
        ).json()
        if rollback["generation_status"] != "pending_doctor_review":
            raise RuntimeError("rollback bypassed re-review")
        self.expect(
            self.client.get(
                f"/patient-sessions/{session_id}/avatar",
                headers=patient_headers,
            ),
            409,
            "hide avatar during rollback review",
        )
        self.expect(
            self.client.post(
                f"/avatar-versions/{initial_version_id}/review",
                headers=self.keyed(doctor_headers, "rollback-review"),
                json={"decision": "approve"},
            ),
            200,
            "review rollback version",
        )
        self.expect(
            self.client.post(
                f"/avatar-versions/{initial_version_id}/authorize",
                headers=self.keyed(doctor_headers, "rollback-authorize"),
                json={"session_id": session_id},
            ),
            200,
            "reauthorize rollback version",
        )
        self.expect(
            self.client.post(
                f"/cases/{case_id}/authorization/revoke",
                headers=self.keyed(doctor_headers, "authorization-revoke"),
                json={"session_id": session_id, "reason": "online_acceptance"},
            ),
            200,
            "revoke authorization",
        )
        self.expect(
            self.client.get(
                f"/patient-sessions/{session_id}/avatar",
                headers=patient_headers,
            ),
            409,
            "hide avatar after revoke",
        )
        self.evidence.add("rollback_rereview_reauthorization_and_revoke")

        self.expect(
            self.client.post(
                f"/sessions/{session_id}/stop",
                headers=self.keyed(doctor_headers, "session-stop"),
                json={"reason": "online_acceptance_complete"},
            ),
            200,
            "stop session",
        )
        self.expect(
            self.client.get(
                f"/sessions/{session_id}",
                headers=patient_headers,
            ),
            404,
            "deny patient after session end",
        )
        archived = self.expect(
            self.client.post(
                f"/cases/{case_id}/archive",
                headers=self.keyed(doctor_headers, "case-archive"),
                json={"reason": "online_acceptance"},
            ),
            200,
            "archive case",
        ).json()
        original_due = archived["retention_due_at"]
        restored = self.expect(
            self.client.post(
                f"/admin/cases/{case_id}/restore",
                headers=self.keyed(admin_headers, "case-restore"),
                json={"reason": "online_acceptance_restore"},
            ),
            200,
            "restore archived case",
        ).json()
        if restored["retention_due_at"] != original_due:
            raise RuntimeError("restore changed the original retention deadline")
        rearchived = self.expect(
            self.client.post(
                f"/cases/{case_id}/archive",
                headers=self.keyed(doctor_headers, "case-rearchive"),
                json={"reason": "online_acceptance_rearchive"},
            ),
            200,
            "rearchive restored case",
        ).json()
        if rearchived["retention_due_at"] != original_due:
            raise RuntimeError("rearchive changed the original retention deadline")
        self.evidence.add("session_end_archive_restore_rearchive")

        self.expect(
            self.client.get("/admin/stats", headers=admin_headers),
            200,
            "admin aggregate stats",
        )
        audits = self.expect(
            self.client.get("/admin/audit-logs", headers=admin_headers),
            200,
            "admin redacted audits",
        ).json()
        serialized_audits = json.dumps(audits, ensure_ascii=False)
        if self.study_code in serialized_audits or "我现在想自残" in serialized_audits:
            raise RuntimeError("admin audit response leaked restricted content")
        self.evidence.add("admin_aggregate_and_redacted_audit")
        return self.evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the complete supervised Avatar workflow against a deployed API."
    )
    parser.add_argument("--api-base", required=True, help="Public API base ending in /api")
    parser.add_argument("--site-url", help="Optional Netlify site URL to verify")
    parser.add_argument("--doctor-email", default="doctor@example.com")
    parser.add_argument("--doctor-password", required=True)
    parser.add_argument("--admin-email", default="admin@example.com")
    parser.add_argument("--admin-password", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    acceptance = OnlineAcceptance(
        api_base=args.api_base,
        site_url=args.site_url,
        doctor_email=args.doctor_email,
        doctor_password=args.doctor_password,
        admin_email=args.admin_email,
        admin_password=args.admin_password,
    )
    try:
        evidence = acceptance.run()
    finally:
        acceptance.close()
    print(json.dumps(evidence.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
