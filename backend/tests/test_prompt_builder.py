import pytest
from pydantic import ValidationError

from app.adapters.feature_mapping.prompt_builder import (
    ConfirmedGenerationInput,
    build_prompt_messages,
)


def valid_payload() -> dict:
    return {
        "voice_features": {
            "voice_gender": "uncertain_mixed",
            "age_sense": "young",
            "pitch_level": 3,
            "speaking_rate_level": None,
            "timbre": "clear_transparent",
            "emotions": [
                "anger",
                "indifference",
                "sarcasm",
                "sadness",
                "fear",
                "commanding",
            ],
            "power_level": None,
            "malice_level": None,
        },
        "effective_visual_features": {
            "gender_expression": "中性、自然的性别表达",
            "age_expression": "青年至中年的中性年龄感",
            "face_shape": "轮廓均衡柔和",
            "skin_texture": "自然、细腻的皮肤纹理",
            "facial_expression": "平静、轻微放松",
            "gaze": "视线自然，无压迫感",
            "lighting": "柔和漫射光，低对比度",
            "composition": "正面居中头像",
            "background": "浅灰绿色纯色背景",
        },
        "generation_mode": "initial",
        "doctor_confirmed": True,
    }


def test_all_six_fixed_emotions_are_accepted() -> None:
    data = ConfirmedGenerationInput.model_validate(valid_payload())
    assert len(data.voice_features.emotions) == 6


def test_doctor_confirmation_is_required() -> None:
    payload = valid_payload()
    payload["doctor_confirmed"] = False

    with pytest.raises(ValidationError):
        ConfirmedGenerationInput.model_validate(payload)


def test_prompt_uses_confirmed_visual_features_and_no_risk_classification() -> None:
    messages = build_prompt_messages(valid_payload())

    assert messages["template_version"] == "voice-to-appearance-v1.0"
    assert "医生确认后的最终视觉特征" in messages["user"]
    assert "risk_level" not in messages["user"]


def test_forbidden_doctor_visual_content_is_rejected() -> None:
    payload = valid_payload()
    payload["effective_visual_features"]["background"] = "加入武器和阴暗场景"

    with pytest.raises(ValidationError):
        ConfirmedGenerationInput.model_validate(payload)
