import pytest
from pydantic import ValidationError

from app.adapters.feature_mapping.deterministic_mapper import map_voice_to_visual
from app.adapters.feature_mapping.prompt_builder import VoiceFeatures


def test_child_high_negative_levels_are_softened_without_risk_classification() -> None:
    result = map_voice_to_visual(
        VoiceFeatures(
            voice_gender="uncertain_mixed",
            age_sense="child",
            pitch_level=5,
            speaking_rate_level=5,
            timbre="sharp_piercing",
            emotions=["anger", "fear"],
            power_level=5,
            malice_level=5,
        )
    )

    assert result.explanation["effective_power_level"] == 2
    assert result.explanation["effective_malice_level"] == 1
    assert result.explanation["initial_risk_classification_performed"] is False
    assert "暖" in result.features.lighting
    assert "禁止" in result.features.facial_expression


def test_emotions_allow_six_but_reject_duplicates() -> None:
    all_emotions = ["anger", "indifference", "sarcasm", "sadness", "fear", "commanding"]
    features = VoiceFeatures(
        voice_gender="female",
        age_sense="young",
        pitch_level=3,
        emotions=all_emotions,
    )
    assert len(features.emotions) == 6

    with pytest.raises(ValidationError):
        VoiceFeatures(
            voice_gender="female",
            age_sense="young",
            pitch_level=3,
            emotions=["fear", "fear"],
        )


def test_six_emotions_render_at_most_two_visible_signal_groups() -> None:
    result = map_voice_to_visual(
        VoiceFeatures(
            voice_gender="female",
            age_sense="young",
            pitch_level=3,
            speaking_rate_level=5,
            emotions=["anger", "indifference", "sarcasm", "sadness", "fear", "commanding"],
            power_level=3,
            malice_level=3,
        )
    )

    expression = result.features.facial_expression
    assert "克制的愤怒/命令式" in expression
    assert "恐惧：" in expression
    assert "第三组面部动作" in expression
    assert "不得出现任何笑容" in expression
    assert "语速不得覆盖情绪方向" in expression
    assert "冷漠：" not in expression
    assert result.explanation["mapping_version"] == "deterministic-voice-appearance-v1.1"


def test_v11_power_proportion_and_elderly_malice_equivalent_are_applied() -> None:
    result = map_voice_to_visual(
        VoiceFeatures(
            voice_gender="uncertain_mixed",
            age_sense="elderly",
            pitch_level=2,
            emotions=["indifference"],
            power_level=5,
            malice_level=5,
        )
    )

    assert result.explanation["effective_power_level"] == 5
    assert result.explanation["effective_malice_level"] == 2
    assert "约 78%" in result.features.composition
    assert "明亮低饱和冷中性柔光" in result.features.lighting
    assert "老年高恶意安全等价" in result.explanation["safety_rules_applied"][0]
