from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.feature_mapping.prompt_builder import EffectiveVisualFeatures


class QuestionKey(StrEnum):
    VOICE_GENDER = "voice_gender"
    AGE_SENSE = "age_sense"
    PITCH_LEVEL = "pitch_level"
    SPEAKING_RATE_LEVEL = "speaking_rate_level"
    TIMBRE = "timbre"
    EMOTIONS = "emotions"
    POWER_LEVEL = "power_level"
    MALICE_LEVEL = "malice_level"


QUESTION_KEYS = [item.value for item in QuestionKey]


class SaveQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any
    source: Literal["doctor_interview"] = "doctor_interview"
    client_updated_at: datetime | None = None


class VoiceFeaturesResponse(BaseModel):
    sound_description_id: UUID | None = None
    case_id: UUID
    session_id: UUID | None = None
    answers: dict[str, Any]
    answered_questions: list[str]
    completed_count: int
    total_count: int = 8
    complete: bool
    updated_at: datetime | None = None


class SaveQuestionResponse(BaseModel):
    question_key: QuestionKey
    value: Any
    completed: bool
    completed_count: int
    updated_at: datetime


class ExtractFeaturesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID


class FeatureExtractionResponse(BaseModel):
    job_id: UUID
    visual_feature_id: UUID
    status: Literal["completed"] = "completed"
    mapping_version: str


class UpdateVisualFeaturesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_features: EffectiveVisualFeatures | None = None
    restore_system_result: bool = False
    doctor_confirmed: bool


class VisualFeaturesResponse(BaseModel):
    visual_feature_id: UUID
    case_id: UUID
    source_sound_description_id: UUID
    system_result: EffectiveVisualFeatures
    doctor_edited: dict[str, str] | None = None
    effective_features: EffectiveVisualFeatures
    controlled_options: dict[str, list[str]]
    mapping_explanation: dict[str, Any] | None = None
    mapping_version: str
    is_doctor_confirmed: bool
    confirmed_at: datetime | None = None
    updated_at: datetime


class VoiceFeatureContractResponse(BaseModel):
    question_order: list[str]
    enums: dict[str, list[str]]
    optional_nullable_questions: list[str]
    emotion_max_length: int = Field(default=6, ge=6, le=6)
    visual_feature_keys: list[str]
    controlled_visual_options: dict[str, list[str]]
    initial_risk_classification: bool = False
