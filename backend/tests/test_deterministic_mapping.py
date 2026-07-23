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
