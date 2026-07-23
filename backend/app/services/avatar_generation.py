from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.feature_mapping.prompt_builder import (
    PROMPT_TEMPLATE_VERSION,
    ConfirmedGenerationInput,
    EffectiveVisualFeatures,
    VoiceFeatures,
    build_prompt_messages,
)
from app.adapters.image_generation.providers import (
    GeneratedImage,
    ImageGenerationError,
    ImageGenerationProvider,
    get_image_generation_provider,
)
from app.adapters.image_generation.safety import ImageSafetyResult, inspect_generated_image
from app.adapters.image_generation.semantic_safety import (
    SemanticImageSafetyError,
    SemanticImageSafetyProvider,
    SemanticImageSafetyResult,
    get_semantic_image_safety_provider,
)
from app.adapters.storage import get_object_storage
from app.api.errors import ApiError
from app.config.settings import Settings
from app.domain.enums import AdjustmentStatus, GenerationMode, GenerationStatus
from app.models.entities import (
    AdjustmentRequest,
    AvatarVersion,
    ClinicalCase,
    SoundDescription,
    VisualFeature,
)
from app.security.crypto import decrypt_sensitive_text
from app.services.core import utc_now
from app.services.features import sound_answers


@dataclass(frozen=True)
class PromptEnvelope:
    text: str
    sha256: bytes


class ImageGenerationSafetyError(ImageGenerationError):
    def __init__(
        self,
        code: str,
        *,
        retryable: bool = False,
        semantic_result: SemanticImageSafetyResult | None = None,
    ) -> None:
        super().__init__(code, retryable=retryable)
        self.semantic_result = semantic_result


async def generate_with_image_safety_retry(
    provider: ImageGenerationProvider,
    prompt: str,
    semantic_safety_provider: SemanticImageSafetyProvider,
) -> tuple[GeneratedImage, ImageSafetyResult, SemanticImageSafetyResult]:
    """Retry an unsafe or malformed output once, then fail closed."""
    last_code = "IMAGE_SAFETY_FAILED"
    last_semantic_result: SemanticImageSafetyResult | None = None
    for _attempt in range(2):
        generated = await asyncio.to_thread(provider.generate, prompt)
        structural_safety = inspect_generated_image(
            generated.content,
            generated.mime_type,
        )
        if not structural_safety.allowed:
            last_code = structural_safety.code
            continue
        try:
            semantic_safety = await asyncio.to_thread(
                semantic_safety_provider.inspect,
                generated.content,
                generated.mime_type,
            )
        except SemanticImageSafetyError as exc:
            raise ImageGenerationSafetyError(
                exc.code,
                retryable=exc.retryable,
            ) from exc
        if semantic_safety.allowed:
            return generated, structural_safety, semantic_safety
        last_code = semantic_safety.code
        last_semantic_result = semantic_safety
    raise ImageGenerationSafetyError(
        last_code,
        semantic_result=last_semantic_result,
    )


def _voice_features(sound: SoundDescription) -> VoiceFeatures:
    return VoiceFeatures(
        voice_gender=sound.voice_gender,
        age_sense=sound.age_sense,
        pitch_level=sound.pitch_level,
        speaking_rate_level=sound.speaking_rate_level,
        timbre=sound.timbre,
        emotions=sound.emotions,
        power_level=sound.power_level,
        malice_level=sound.malice_level,
    )


def build_generation_prompt(
    sound: SoundDescription,
    visual: VisualFeature,
    mode: GenerationMode,
    controlled_adjustment: str | None = None,
) -> PromptEnvelope:
    messages = build_prompt_messages(
        ConfirmedGenerationInput(
            voice_features=_voice_features(sound),
            effective_visual_features=EffectiveVisualFeatures.model_validate(visual.effective_json),
            generation_mode=mode,
            doctor_confirmed=visual.confirmed_at is not None,
        )
    )
    text = f"{messages['system']}\n\n{messages['user']}"
    if controlled_adjustment:
        text += (
            "\n\n医生审核后的低刺激受控调整指令："
            f"{controlled_adjustment}\n不得使用或推断患者的原始文本。"
        )
    return PromptEnvelope(text=text, sha256=hashlib.sha256(text.encode("utf-8")).digest())


async def _generation_sources(
    session: AsyncSession, version: AvatarVersion, settings: Settings
) -> tuple[SoundDescription, VisualFeature, str | None]:
    visual = await session.get(VisualFeature, version.source_visual_feature_id)
    if visual is None or visual.confirmed_at is None:
        raise ImageGenerationError("CONFIRMED_VISUAL_SOURCE_MISSING")
    sound = await session.get(SoundDescription, visual.source_sound_description_id)
    if sound is None:
        raise ImageGenerationError("VOICE_SOURCE_MISSING")
    controlled: str | None = None
    if version.source_adjustment_request_id:
        adjustment = await session.get(AdjustmentRequest, version.source_adjustment_request_id)
        if adjustment is None or adjustment.reviewed_instruction_encrypted is None:
            raise ImageGenerationError("CONTROLLED_ADJUSTMENT_MISSING")
        controlled = decrypt_sensitive_text(
            adjustment.reviewed_instruction_encrypted, settings.secret_key
        )
    return sound, visual, controlled


async def create_avatar_generation(
    session: AsyncSession,
    *,
    case_id: UUID,
    mode: GenerationMode,
    settings: Settings,
    adjustment: AdjustmentRequest | None = None,
) -> AvatarVersion:
    case = await session.scalar(
        select(ClinicalCase)
        .where(ClinicalCase.case_id == case_id)
        .with_for_update()
    )
    if case is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "病例不存在或无权访问")
    visual = await session.scalar(
        select(VisualFeature).where(
            VisualFeature.case_id == case_id,
            VisualFeature.is_current.is_(True),
        )
    )
    if visual is None or visual.confirmed_at is None:
        raise ApiError(409, "VISUAL_CONFIRMATION_REQUIRED", "请先确认当前视觉特征")
    sound = await session.get(SoundDescription, visual.source_sound_description_id)
    if sound is None:
        raise ApiError(409, "STATE_CONFLICT", "Q1–Q8 来源记录不可用")
    active = await session.scalar(
        select(AvatarVersion).where(
            AvatarVersion.case_id == case_id,
            AvatarVersion.generation_status.in_(
                {
                    GenerationStatus.QUEUED,
                    GenerationStatus.GENERATING,
                    GenerationStatus.CHECKING,
                }
            ),
        )
    )
    if active is not None:
        raise ApiError(409, "GENERATION_ALREADY_RUNNING", "本病例已有生图任务正在处理")
    if mode == GenerationMode.PATIENT_ADJUSTMENT:
        if adjustment is None or adjustment.doctor_status not in {
            AdjustmentStatus.APPROVED_AS_IS,
            AdjustmentStatus.APPROVED_EDITED,
        }:
            raise ApiError(409, "STATE_CONFLICT", "患者调整尚未通过医生审核")
        if adjustment.reviewed_instruction_encrypted is None:
            raise ApiError(409, "STATE_CONFLICT", "受控调整指令不可用")
        controlled = decrypt_sensitive_text(
            adjustment.reviewed_instruction_encrypted, settings.secret_key
        )
    else:
        controlled = None
    prompt = build_generation_prompt(sound, visual, mode, controlled)
    round_no = (
        await session.scalar(
            select(func.coalesce(func.max(AvatarVersion.generation_round), 0)).where(
                AvatarVersion.case_id == case_id
            )
        )
    ) + 1
    await session.execute(
        update(AvatarVersion)
        .where(AvatarVersion.case_id == case_id, AvatarVersion.is_current_candidate.is_(True))
        .values(is_current_candidate=False)
    )
    version = AvatarVersion(
        case_id=case_id,
        source_visual_feature_id=visual.visual_feature_id,
        voice_features_snapshot_json=sound_answers(sound),
        visual_features_snapshot_json={
            "system_result": dict(visual.system_result_json),
            "doctor_edited": (
                dict(visual.doctor_edited_json) if visual.doctor_edited_json is not None else None
            ),
            "effective_features": dict(visual.effective_json),
            "mapping_version": visual.mapping_version,
            "confirmed_at": visual.confirmed_at.isoformat() if visual.confirmed_at else None,
        },
        source_adjustment_request_id=adjustment.request_id if adjustment else None,
        generation_round=round_no,
        generation_mode=mode,
        generation_status=GenerationStatus.QUEUED,
        image_object_key=None,
        provider_kind=settings.model_provider,
        provider_model=(
            settings.model_name if settings.model_provider == "openai" else "mock-avatar-v1"
        ),
        provider_request_id=None,
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        prompt_sha256=prompt.sha256,
        safety_status="pending",
        doctor_review_status="pending",
        is_current_candidate=True,
        created_at=utc_now(),
    )
    session.add(version)
    if adjustment:
        adjustment.doctor_status = AdjustmentStatus.GENERATING
    await session.flush()
    return version


async def process_avatar_generation(
    session: AsyncSession, version_id: UUID, settings: Settings
) -> AvatarVersion:
    version = await session.get(AvatarVersion, version_id)
    if version is None:
        raise ImageGenerationError("GENERATION_NOT_FOUND")
    if version.generation_status not in {GenerationStatus.QUEUED, GenerationStatus.GENERATING}:
        return version
    try:
        sound, visual, controlled = await _generation_sources(session, version, settings)
        prompt = build_generation_prompt(sound, visual, version.generation_mode, controlled)
        if prompt.sha256 != version.prompt_sha256:
            raise ImageGenerationError("GENERATION_INPUT_CHANGED")
        version.generation_status = GenerationStatus.GENERATING
        version.started_at = version.started_at or utc_now()
        await session.commit()
        provider = get_image_generation_provider(settings)
        try:
            semantic_safety_provider = get_semantic_image_safety_provider(settings)
        except SemanticImageSafetyError as exc:
            raise ImageGenerationSafetyError(
                exc.code,
                retryable=exc.retryable,
            ) from exc
        generated, safety, semantic_safety = await generate_with_image_safety_retry(
            provider,
            prompt.text,
            semantic_safety_provider,
        )
        await session.refresh(version)
        if version.generation_status == GenerationStatus.CANCELLED:
            return version
        version.generation_status = GenerationStatus.CHECKING
        await session.commit()
        object_key = f"cases/{version.case_id}/avatars/{version.version_id}.png"
        try:
            storage = get_object_storage(settings)
            await asyncio.to_thread(
                storage.put, object_key, generated.content, generated.mime_type
            )
        except Exception as exc:
            raise ImageGenerationError("STORAGE_TEMPORARY_FAILURE", retryable=True) from exc
        version = await session.scalar(
            select(AvatarVersion)
            .where(AvatarVersion.version_id == version_id)
            .with_for_update()
        )
        if version is None:
            await asyncio.to_thread(storage.delete, object_key)
            raise ImageGenerationError("GENERATION_NOT_FOUND")
        if version.generation_status == GenerationStatus.CANCELLED:
            await asyncio.to_thread(storage.delete, object_key)
            await session.commit()
            return version
        version.image_object_key = object_key
        version.output_mime_type = generated.mime_type
        version.image_width = safety.width
        version.image_height = safety.height
        version.provider_request_id = generated.provider_request_id
        version.semantic_safety_provider = semantic_safety.provider
        version.semantic_safety_model = semantic_safety.model
        version.semantic_safety_request_id = semantic_safety.provider_request_id
        version.semantic_safety_categories_json = list(
            semantic_safety.flagged_categories
        )
        version.safety_status = "passed"
        version.generation_status = GenerationStatus.PENDING_DOCTOR_REVIEW
        version.completed_at = utc_now()
        version.failure_code = None
        await session.commit()
        return version
    except ImageGenerationError as exc:
        await session.rollback()
        version = await session.get(AvatarVersion, version_id)
        if version is None:
            raise
        if version.generation_status == GenerationStatus.CANCELLED:
            return version
        if isinstance(exc, ImageGenerationSafetyError) and exc.semantic_result:
            semantic_result = exc.semantic_result
            version.semantic_safety_provider = semantic_result.provider
            version.semantic_safety_model = semantic_result.model
            version.semantic_safety_request_id = semantic_result.provider_request_id
            version.semantic_safety_categories_json = list(
                semantic_result.flagged_categories
            )
        if exc.retryable:
            version.generation_status = GenerationStatus.QUEUED
            version.failure_code = exc.code
            version.safety_status = "pending"
            await session.commit()
            raise
        await mark_avatar_generation_failed(session, version, exc.code)
        return version


async def mark_avatar_generation_failed(
    session: AsyncSession, version: AvatarVersion, failure_code: str
) -> None:
    version.generation_status = GenerationStatus.FAILED
    version.failure_code = failure_code
    version.safety_status = "blocked" if "MODERATION" in failure_code else "failed"
    version.completed_at = utc_now()
    if version.source_adjustment_request_id:
        adjustment = await session.get(
            AdjustmentRequest, version.source_adjustment_request_id
        )
        if adjustment:
            adjustment.doctor_status = AdjustmentStatus.GENERATION_FAILED
    await session.commit()
