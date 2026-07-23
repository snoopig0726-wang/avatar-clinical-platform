from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.feature_mapping.deterministic_mapper import (
    MAPPING_VERSION,
    map_voice_to_visual,
)
from app.adapters.feature_mapping.prompt_builder import VoiceFeatures
from app.config.settings import Settings
from app.domain.enums import (
    AdjustmentStatus,
    AuthorizationStatus,
    CaseStatus,
    GenerationMode,
    GenerationStatus,
    InviteStatus,
    SessionStatus,
)
from app.models.entities import (
    AdjustmentRequest,
    AvatarVersion,
    ClinicalCase,
    PatientSession,
    SessionAvatarAuthorization,
    SessionInvite,
    SoundDescription,
    StaffUser,
    VisualFeature,
)
from app.schemas.features import QUESTION_KEYS
from app.security.crypto import (
    derive_invite_code,
    derive_patient_token,
    encrypt_sensitive_text,
    hash_secret,
    normalize_invite_code,
)
from app.services.core import utc_now

EXAMPLE_STUDY_CODES = ("DEMO-VOICE-001", "DEMO-VOICE-002", "DEMO-VOICE-003")


def _new_invite(
    *,
    case_id: UUID,
    doctor_id: UUID,
    status: InviteStatus,
    settings: Settings,
    now,
) -> tuple[SessionInvite, str]:
    invite_id = uuid4()
    code = derive_invite_code(invite_id, settings.secret_key)
    return (
        SessionInvite(
            invite_id=invite_id,
            case_id=case_id,
            issuing_doctor_id=doctor_id,
            code_hash=hash_secret(
                normalize_invite_code(code), settings.secret_key, "session-invite-code"
            ),
            code_mask=f"****-{code[-4:]}",
            status=status,
            created_at=now,
            expires_at=now + timedelta(hours=24),
            redeemed_at=now if status != InviteStatus.ISSUED else None,
        ),
        code,
    )


def _new_patient_session(
    *,
    case_id: UUID,
    invite_id: UUID,
    doctor_id: UUID,
    status: SessionStatus,
    settings: Settings,
    now,
) -> PatientSession:
    session_id = uuid4()
    token = derive_patient_token(session_id, settings.secret_key)
    started = status == SessionStatus.ACTIVE
    return PatientSession(
        session_id=session_id,
        case_id=case_id,
        invite_id=invite_id,
        supervising_doctor_id=doctor_id,
        device_binding_hash=hash_secret(
            f"example-device:{session_id}", settings.secret_key, "device-binding"
        ),
        patient_session_token_hash=hash_secret(token, settings.secret_key, "patient-session-token"),
        status=status,
        consent_confirmed_by=doctor_id if started else None,
        consent_confirmed_at=now if started else None,
        consent_version="v1" if started else None,
        created_at=now,
        started_at=now if started else None,
        expires_at=now + timedelta(hours=24),
        last_seen_at=now,
    )


async def seed_example_data(session: AsyncSession, doctor: StaffUser, settings: Settings) -> None:
    existing_codes = set(
        (
            await session.scalars(
                select(ClinicalCase.study_code).where(
                    ClinicalCase.owner_doctor_id == doctor.user_id,
                    ClinicalCase.study_code.in_(EXAMPLE_STUDY_CODES),
                )
            )
        ).all()
    )
    now = utc_now()

    if "DEMO-VOICE-001" not in existing_codes:
        case = ClinicalCase(
            owner_doctor_id=doctor.user_id,
            study_code="DEMO-VOICE-001",
            status=CaseStatus.IN_PROGRESS,
            created_at=now - timedelta(days=2),
            updated_at=now,
        )
        session.add(case)
        await session.flush()
        invite, _ = _new_invite(
            case_id=case.case_id,
            doctor_id=doctor.user_id,
            status=InviteStatus.ACTIVE,
            settings=settings,
            now=now,
        )
        session.add(invite)
        patient_session = _new_patient_session(
            case_id=case.case_id,
            invite_id=invite.invite_id,
            doctor_id=doctor.user_id,
            status=SessionStatus.ACTIVE,
            settings=settings,
            now=now,
        )
        session.add(patient_session)
        await session.flush()
        voice = VoiceFeatures(
            voice_gender="male",
            age_sense="young",
            pitch_level=3,
            speaking_rate_level=2,
            timbre="low_rich",
            emotions=["sadness", "indifference"],
            power_level=3,
            malice_level=1,
        )
        sound = SoundDescription(
            case_id=case.case_id,
            session_id=patient_session.session_id,
            answered_questions=QUESTION_KEYS,
            created_at=now,
            updated_at=now,
            **voice.model_dump(mode="json"),
        )
        session.add(sound)
        await session.flush()
        mapping = map_voice_to_visual(voice)
        session.add(
            VisualFeature(
                case_id=case.case_id,
                source_sound_description_id=sound.sound_description_id,
                system_result_json=mapping.features.model_dump(mode="json"),
                effective_json=mapping.features.model_dump(mode="json"),
                mapping_explanation=mapping.explanation,
                mapping_version=MAPPING_VERSION,
                is_current=True,
                confirmed_by=doctor.user_id,
                confirmed_at=now,
                created_at=now,
                updated_at=now,
            )
        )

    if "DEMO-VOICE-002" not in existing_codes:
        case = ClinicalCase(
            owner_doctor_id=doctor.user_id,
            study_code="DEMO-VOICE-002",
            status=CaseStatus.DRAFT,
            created_at=now - timedelta(days=1),
            updated_at=now - timedelta(minutes=18),
        )
        session.add(case)
        await session.flush()
        invite, _ = _new_invite(
            case_id=case.case_id,
            doctor_id=doctor.user_id,
            status=InviteStatus.REDEEMED_WAITING,
            settings=settings,
            now=now,
        )
        session.add(invite)
        session.add(
            _new_patient_session(
                case_id=case.case_id,
                invite_id=invite.invite_id,
                doctor_id=doctor.user_id,
                status=SessionStatus.WAITING_DOCTOR,
                settings=settings,
                now=now,
            )
        )

    if "DEMO-VOICE-003" not in existing_codes:
        case = ClinicalCase(
            owner_doctor_id=doctor.user_id,
            study_code="DEMO-VOICE-003",
            status=CaseStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )
        session.add(case)
        await session.flush()
        invite, _ = _new_invite(
            case_id=case.case_id,
            doctor_id=doctor.user_id,
            status=InviteStatus.ISSUED,
            settings=settings,
            now=now,
        )
        session.add(invite)

    demo_case = await session.scalar(
        select(ClinicalCase).where(
            ClinicalCase.owner_doctor_id == doctor.user_id,
            ClinicalCase.study_code == "DEMO-VOICE-001",
        )
    )
    if demo_case is not None:
        demo_session = await session.scalar(
            select(PatientSession).where(PatientSession.case_id == demo_case.case_id)
        )
        visual = await session.scalar(
            select(VisualFeature).where(
                VisualFeature.case_id == demo_case.case_id,
                VisualFeature.is_current.is_(True),
            )
        )
        sound = (
            await session.get(SoundDescription, visual.source_sound_description_id)
            if visual is not None
            else None
        )
        version = await session.scalar(
            select(AvatarVersion)
            .where(AvatarVersion.case_id == demo_case.case_id)
            .order_by(AvatarVersion.created_at.desc())
            .limit(1)
        )
        if version is None and visual is not None:
            version = AvatarVersion(
                case_id=demo_case.case_id,
                source_visual_feature_id=visual.visual_feature_id,
                voice_features_snapshot_json=(
                    {
                        "voice_gender": sound.voice_gender,
                        "age_sense": sound.age_sense,
                        "pitch_level": sound.pitch_level,
                        "speaking_rate_level": sound.speaking_rate_level,
                        "timbre": sound.timbre,
                        "emotions": sound.emotions,
                        "power_level": sound.power_level,
                        "malice_level": sound.malice_level,
                    }
                    if sound is not None
                    else None
                ),
                visual_features_snapshot_json={
                    "system_result": dict(visual.system_result_json),
                    "doctor_edited": (
                        dict(visual.doctor_edited_json)
                        if visual.doctor_edited_json is not None
                        else None
                    ),
                    "effective_features": dict(visual.effective_json),
                    "mapping_version": visual.mapping_version,
                    "confirmed_at": (
                        visual.confirmed_at.isoformat() if visual.confirmed_at else None
                    ),
                },
                generation_round=1,
                generation_mode=GenerationMode.INITIAL,
                generation_status=GenerationStatus.APPROVED,
                image_object_key=None,
                provider_kind="mock",
                provider_model="legacy-mock",
                prompt_template_version="legacy-v0",
                prompt_sha256=b"",
                safety_status="passed",
                doctor_review_status="approved",
                is_current_candidate=True,
                created_at=now,
            )
            session.add(version)
            await session.flush()
        if demo_session is not None and version is not None:
            authorization = await session.scalar(
                select(SessionAvatarAuthorization).where(
                    SessionAvatarAuthorization.session_id == demo_session.session_id,
                    SessionAvatarAuthorization.status == AuthorizationStatus.AUTHORIZED,
                )
            )
            if authorization is None:
                session.add(
                    SessionAvatarAuthorization(
                        session_id=demo_session.session_id,
                        version_id=version.version_id,
                        status=AuthorizationStatus.AUTHORIZED,
                        authorized_by=doctor.user_id,
                        authorized_at=now,
                    )
                )
            adjustment = await session.scalar(
                select(AdjustmentRequest).where(
                    AdjustmentRequest.case_id == demo_case.case_id,
                    AdjustmentRequest.sequence_no == 1,
                )
            )
            if adjustment is None:
                session.add(
                    AdjustmentRequest(
                        case_id=demo_case.case_id,
                        session_id=demo_session.session_id,
                        sequence_no=1,
                        submitted_text_encrypted=encrypt_sensitive_text(
                            "希望表情更平静，减少阴影和紧张感", settings.secret_key
                        ),
                        risk_status="passed",
                        risk_rule_version="RISK-V1.0",
                        doctor_status=AdjustmentStatus.PENDING_DOCTOR_REVIEW,
                        submitted_at=now,
                    )
                )

    await session.commit()
