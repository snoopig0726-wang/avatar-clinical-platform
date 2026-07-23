from __future__ import annotations

from typing import Any

from app.adapters.feature_mapping.prompt_builder import (
    AgeSense,
    Emotion,
    Timbre,
    VoiceFeatures,
    VoiceGender,
)
from app.api.errors import ApiError
from app.models.entities import SoundDescription
from app.schemas.features import QUESTION_KEYS, QuestionKey


def _validate_level(value: Any, *, nullable: bool) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise ApiError(422, "VALIDATION_ERROR", "滑块值必须是 1–5 的整数")
    return value


def validate_question_value(question_key: QuestionKey, value: Any) -> Any:
    try:
        if question_key == QuestionKey.VOICE_GENDER:
            return VoiceGender(value).value
        if question_key == QuestionKey.AGE_SENSE:
            return AgeSense(value).value
        if question_key == QuestionKey.PITCH_LEVEL:
            return _validate_level(value, nullable=False)
        if question_key == QuestionKey.SPEAKING_RATE_LEVEL:
            return _validate_level(value, nullable=True)
        if question_key == QuestionKey.TIMBRE:
            return None if value is None else Timbre(value).value
        if question_key == QuestionKey.EMOTIONS:
            if not isinstance(value, list) or not 1 <= len(value) <= 6:
                raise ApiError(422, "VALIDATION_ERROR", "情绪必须选择 1–6 项固定选项")
            normalized = [Emotion(item).value for item in value]
            if len(set(normalized)) != len(normalized):
                raise ApiError(422, "VALIDATION_ERROR", "情绪选项不能重复")
            return normalized
        if question_key == QuestionKey.POWER_LEVEL:
            return _validate_level(value, nullable=True)
        if question_key == QuestionKey.MALICE_LEVEL:
            return _validate_level(value, nullable=True)
    except ApiError:
        raise
    except (TypeError, ValueError) as exc:
        raise ApiError(422, "VALIDATION_ERROR", "字段值不在 V1 固定选项中") from exc
    raise ApiError(422, "VALIDATION_ERROR", "未知的 Q1–Q8 字段")


def sound_answers(sound: SoundDescription | None) -> dict[str, Any]:
    return {
        "voice_gender": sound.voice_gender if sound else None,
        "age_sense": sound.age_sense if sound else None,
        "pitch_level": sound.pitch_level if sound else None,
        "speaking_rate_level": sound.speaking_rate_level if sound else None,
        "timbre": sound.timbre if sound else None,
        "emotions": sound.emotions if sound else None,
        "power_level": sound.power_level if sound else None,
        "malice_level": sound.malice_level if sound else None,
    }


def sound_to_voice_features(sound: SoundDescription) -> VoiceFeatures:
    answered = set(sound.answered_questions or [])
    missing = [key for key in QUESTION_KEYS if key not in answered]
    if missing:
        raise ApiError(
            409,
            "STATE_CONFLICT",
            "Q1–Q8 尚未逐题确认完成",
            {"missing_questions": missing},
        )
    try:
        return VoiceFeatures.model_validate(sound_answers(sound))
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", "Q1–Q8 字段组合不符合 V1 约束") from exc
