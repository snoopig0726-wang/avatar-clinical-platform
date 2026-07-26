from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.feature_mapping.deterministic_mapper import (
    CONTROLLED_VISUAL_OPTIONS,
    MAPPING_VERSION,
    map_voice_to_visual,
)
from app.adapters.feature_mapping.prompt_builder import (
    AgeSense,
    EffectiveVisualFeatures,
    Emotion,
    Timbre,
    VoiceGender,
)
from app.api.dependencies import AuthenticatedStaff, require_doctor, require_idempotency_key
from app.api.errors import ApiError
from app.api.routes.cases import owned_case_or_404
from app.api.routes.sessions import doctor_session_or_404
from app.database import get_db_session
from app.domain.enums import AuditActorType, SessionStatus
from app.models.entities import SoundDescription, VisualFeature
from app.schemas.features import (
    QUESTION_KEYS,
    ExtractFeaturesRequest,
    FeatureExtractionResponse,
    QuestionKey,
    SaveQuestionRequest,
    SaveQuestionResponse,
    UpdateVisualFeaturesRequest,
    VisualFeaturesResponse,
    VoiceFeatureContractResponse,
    VoiceFeaturesResponse,
)
from app.services.core import add_audit, add_idempotency, find_idempotency, utc_now
from app.services.features import (
    sound_answers,
    sound_to_voice_features,
    validate_question_value,
)

router = APIRouter()


async def latest_sound_description(session: AsyncSession, case_id: UUID) -> SoundDescription | None:
    return await session.scalar(
        select(SoundDescription)
        .where(SoundDescription.case_id == case_id)
        .order_by(SoundDescription.updated_at.desc())
        .limit(1)
    )


async def current_visual_feature(session: AsyncSession, case_id: UUID) -> VisualFeature:
    visual = await session.scalar(
        select(VisualFeature).where(
            VisualFeature.case_id == case_id,
            VisualFeature.is_current.is_(True),
        )
    )
    if visual is None:
        raise ApiError(409, "STATE_CONFLICT", "尚未完成声音到视觉特征映射")
    return visual


def voice_response(case_id: UUID, sound: SoundDescription | None) -> VoiceFeaturesResponse:
    answered = sound.answered_questions if sound else []
    return VoiceFeaturesResponse(
        sound_description_id=sound.sound_description_id if sound else None,
        case_id=case_id,
        session_id=sound.session_id if sound else None,
        answers=sound_answers(sound),
        answered_questions=answered,
        completed_count=len(answered),
        complete=set(answered) == set(QUESTION_KEYS),
        updated_at=sound.updated_at if sound else None,
    )


def visual_response(visual: VisualFeature) -> VisualFeaturesResponse:
    return VisualFeaturesResponse(
        visual_feature_id=visual.visual_feature_id,
        case_id=visual.case_id,
        source_sound_description_id=visual.source_sound_description_id,
        system_result=EffectiveVisualFeatures.model_validate(visual.system_result_json),
        doctor_edited=visual.doctor_edited_json,
        effective_features=EffectiveVisualFeatures.model_validate(visual.effective_json),
        controlled_options=CONTROLLED_VISUAL_OPTIONS,
        mapping_explanation=visual.mapping_explanation,
        mapping_version=visual.mapping_version,
        is_doctor_confirmed=visual.confirmed_at is not None,
        confirmed_at=visual.confirmed_at,
        updated_at=visual.updated_at,
    )


@router.get("/meta/voice-feature-contract", response_model=VoiceFeatureContractResponse)
async def voice_feature_contract() -> VoiceFeatureContractResponse:
    return VoiceFeatureContractResponse(
        question_order=QUESTION_KEYS,
        enums={
            "voice_gender": [item.value for item in VoiceGender],
            "age_sense": [item.value for item in AgeSense],
            "timbre": [item.value for item in Timbre],
            "emotions": [item.value for item in Emotion],
        },
        optional_nullable_questions=[
            "speaking_rate_level",
            "timbre",
            "power_level",
            "malice_level",
        ],
        visual_feature_keys=list(CONTROLLED_VISUAL_OPTIONS),
        controlled_visual_options=CONTROLLED_VISUAL_OPTIONS,
    )


@router.get("/cases/{case_id}/voice-features", response_model=VoiceFeaturesResponse)
async def get_voice_features(
    case_id: UUID,
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> VoiceFeaturesResponse:
    await owned_case_or_404(session, case_id, staff.user.user_id)
    return voice_response(case_id, await latest_sound_description(session, case_id))


@router.get(
    "/sessions/{session_id}/voice-features",
    response_model=VoiceFeaturesResponse,
)
async def get_session_voice_features(
    session_id: UUID,
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> VoiceFeaturesResponse:
    patient_session = await doctor_session_or_404(
        session, session_id, staff.user.user_id
    )
    sound = await session.scalar(
        select(SoundDescription).where(SoundDescription.session_id == session_id)
    )
    return voice_response(patient_session.case_id, sound)


@router.put(
    "/sessions/{session_id}/voice-features/{question_key}",
    response_model=SaveQuestionResponse,
)
async def save_voice_feature_question(
    session_id: UUID,
    question_key: QuestionKey,
    payload: SaveQuestionRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> SaveQuestionResponse:
    patient_session = await doctor_session_or_404(session, session_id, staff.user.user_id)
    if patient_session.status != SessionStatus.ACTIVE:
        raise ApiError(409, "STATE_CONFLICT", "只有进行中的监督会话可以录入 Q1–Q8")
    if patient_session.assessment_mode != "new_assessment":
        raise ApiError(
            409,
            "ASSESSMENT_REUSED",
            "本次会话正在沿用上次记录；如需修改，请结束本次会话后在新会话中选择重新评估",
        )
    normalized = validate_question_value(question_key, payload.value)
    scope = f"doctor:{staff.user.user_id}:session:{session_id}"
    request_payload = {"question_key": question_key.value, "value": normalized}
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="save_voice_feature",
        key=idempotency_key,
        payload=request_payload,
    )
    sound = await session.scalar(
        select(SoundDescription).where(SoundDescription.session_id == session_id)
    )
    if existing and sound is not None:
        return SaveQuestionResponse(
            question_key=question_key,
            value=getattr(sound, question_key.value),
            completed=question_key.value in sound.answered_questions,
            completed_count=len(sound.answered_questions),
            updated_at=sound.updated_at,
        )

    now = utc_now()
    if sound is None:
        sound = SoundDescription(
            case_id=patient_session.case_id,
            session_id=session_id,
            answered_questions=[],
            created_at=now,
            updated_at=now,
        )
        session.add(sound)
        await session.flush()
    previous_value = getattr(sound, question_key.value)
    was_answered = question_key.value in (sound.answered_questions or [])
    value_changed = not was_answered or previous_value != normalized
    setattr(sound, question_key.value, normalized)
    answered = set(sound.answered_questions or [])
    answered.add(question_key.value)
    sound.answered_questions = [key for key in QUESTION_KEYS if key in answered]
    sound.updated_at = now
    if value_changed:
        await session.execute(
            update(VisualFeature)
            .where(
                VisualFeature.case_id == patient_session.case_id,
                VisualFeature.is_current.is_(True),
            )
            .values(is_current=False, updated_at=now)
        )
    add_idempotency(
        session,
        actor_scope=scope,
        operation="save_voice_feature",
        key=idempotency_key,
        payload=request_payload,
        resource_id=sound.sound_description_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=patient_session.case_id,
        session_id=session_id,
        action="voice_feature.saved",
        metadata={"question_key": question_key.value},
    )
    await session.commit()
    return SaveQuestionResponse(
        question_key=question_key,
        value=normalized,
        completed=True,
        completed_count=len(sound.answered_questions),
        updated_at=now,
    )


@router.post("/cases/{case_id}/extract-features", response_model=FeatureExtractionResponse)
async def extract_visual_features(
    case_id: UUID,
    payload: ExtractFeaturesRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> FeatureExtractionResponse:
    await owned_case_or_404(
        session, case_id, staff.user.user_id, for_update=True
    )
    patient_session = await doctor_session_or_404(session, payload.session_id, staff.user.user_id)
    if patient_session.case_id != case_id or patient_session.status != SessionStatus.ACTIVE:
        raise ApiError(409, "STATE_CONFLICT", "当前会话不能执行视觉特征映射")
    scope = f"doctor:{staff.user.user_id}:case:{case_id}"
    request_payload = payload.model_dump(mode="json")
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="extract_visual_features",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing and existing.resource_id:
        visual = await session.get(VisualFeature, existing.resource_id)
        if visual is None:
            raise ApiError(409, "STATE_CONFLICT", "映射结果已不可用")
        return FeatureExtractionResponse(
            job_id=visual.visual_feature_id,
            visual_feature_id=visual.visual_feature_id,
            mapping_version=visual.mapping_version,
        )
    sound = await session.scalar(
        select(SoundDescription).where(SoundDescription.session_id == payload.session_id)
    )
    if sound is None:
        raise ApiError(409, "STATE_CONFLICT", "Q1–Q8 尚未开始录入")
    if set(sound.answered_questions or []) != set(QUESTION_KEYS):
        raise ApiError(409, "STATE_CONFLICT", "请先完成全部 Q1–Q8，再生成视觉映射")
    mapping = map_voice_to_visual(sound_to_voice_features(sound))
    now = utc_now()
    await session.execute(
        update(VisualFeature)
        .where(VisualFeature.case_id == case_id, VisualFeature.is_current.is_(True))
        .values(is_current=False, updated_at=now)
    )
    visual = VisualFeature(
        case_id=case_id,
        source_sound_description_id=sound.sound_description_id,
        system_result_json=mapping.features.model_dump(mode="json"),
        effective_json=mapping.features.model_dump(mode="json"),
        mapping_explanation=mapping.explanation,
        mapping_version=MAPPING_VERSION,
        is_current=True,
        created_at=now,
        updated_at=now,
    )
    session.add(visual)
    await session.flush()
    add_idempotency(
        session,
        actor_scope=scope,
        operation="extract_visual_features",
        key=idempotency_key,
        payload=request_payload,
        resource_id=visual.visual_feature_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=case_id,
        session_id=payload.session_id,
        action="visual_features.extracted",
        metadata={"mapping_version": MAPPING_VERSION},
    )
    await session.commit()
    return FeatureExtractionResponse(
        job_id=visual.visual_feature_id,
        visual_feature_id=visual.visual_feature_id,
        mapping_version=MAPPING_VERSION,
    )


@router.get("/cases/{case_id}/visual-features", response_model=VisualFeaturesResponse)
async def get_visual_features(
    case_id: UUID,
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> VisualFeaturesResponse:
    await owned_case_or_404(session, case_id, staff.user.user_id)
    return visual_response(await current_visual_feature(session, case_id))


@router.put("/cases/{case_id}/visual-features", response_model=VisualFeaturesResponse)
async def update_visual_features(
    case_id: UUID,
    payload: UpdateVisualFeaturesRequest,
    idempotency_key: str = Depends(require_idempotency_key),
    staff: AuthenticatedStaff = Depends(require_doctor),
    session: AsyncSession = Depends(get_db_session),
) -> VisualFeaturesResponse:
    await owned_case_or_404(
        session, case_id, staff.user.user_id, for_update=True
    )
    visual = await current_visual_feature(session, case_id)
    scope = f"doctor:{staff.user.user_id}:case:{case_id}"
    request_payload = payload.model_dump(mode="json")
    existing = await find_idempotency(
        session,
        actor_scope=scope,
        operation="confirm_visual_features",
        key=idempotency_key,
        payload=request_payload,
    )
    if existing:
        return visual_response(visual)
    if not payload.doctor_confirmed:
        raise ApiError(422, "VALIDATION_ERROR", "医生必须确认视觉特征后才能继续")
    system_result = EffectiveVisualFeatures.model_validate(visual.system_result_json)
    if payload.restore_system_result:
        effective = system_result
        edited: dict[str, str] | None = None
    else:
        if payload.effective_features is None:
            raise ApiError(422, "VALIDATION_ERROR", "必须提供九项有效视觉特征")
        effective = payload.effective_features
        candidate = effective.model_dump(mode="json")
        system_values = system_result.model_dump(mode="json")
        edited = {}
        for key, value in candidate.items():
            if value == system_values[key]:
                continue
            if value not in CONTROLLED_VISUAL_OPTIONS[key]:
                raise ApiError(422, "VALIDATION_ERROR", f"{key} 只能选择受控视觉选项")
            edited[key] = value
        if not edited:
            edited = None
    now = utc_now()
    visual.doctor_edited_json = edited
    visual.effective_json = effective.model_dump(mode="json")
    visual.confirmed_by = staff.user.user_id
    visual.confirmed_at = now
    visual.updated_at = now
    add_idempotency(
        session,
        actor_scope=scope,
        operation="confirm_visual_features",
        key=idempotency_key,
        payload=request_payload,
        resource_id=visual.visual_feature_id,
    )
    add_audit(
        session,
        actor_type=AuditActorType.DOCTOR,
        actor_user_id=staff.user.user_id,
        case_id=case_id,
        action="visual_features.confirmed",
        metadata={"modified_keys": sorted((edited or {}).keys())},
    )
    await session.commit()
    return visual_response(visual)
