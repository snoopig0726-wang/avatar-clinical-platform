from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.domain.enums import GenerationMode

PROMPT_TEMPLATE_VERSION = "voice-to-appearance-v1.0"


class VoiceGender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    UNCERTAIN_MIXED = "uncertain_mixed"


class AgeSense(StrEnum):
    CHILD = "child"
    ADOLESCENT = "adolescent"
    YOUNG = "young"
    MIDDLE_AGED = "middle_aged"
    ELDERLY = "elderly"
    UNCERTAIN = "uncertain"


class Timbre(StrEnum):
    HOARSE_ROUGH = "hoarse_rough"
    CLEAR_TRANSPARENT = "clear_transparent"
    SHARP_PIERCING = "sharp_piercing"
    LOW_RICH = "low_rich"
    BREATHY_WEAK = "breathy_weak"
    NASAL = "nasal"
    MUMBLED = "mumbled"
    HEAVY_ACCENT = "heavy_accent"
    FINE_SOFT = "fine_soft"


class Emotion(StrEnum):
    ANGER = "anger"
    INDIFFERENCE = "indifference"
    SARCASM = "sarcasm"
    SADNESS = "sadness"
    FEAR = "fear"
    COMMANDING = "commanding"


VisualFeatureKey = Literal[
    "gender_expression",
    "age_expression",
    "face_shape",
    "skin_texture",
    "facial_expression",
    "gaze",
    "lighting",
    "composition",
    "background",
]

_FORBIDDEN_VISUAL_CONTENT = re.compile(
    r"(武器|刀|枪|伤口|血迹|自残|自杀|攻击|暴力|恶魔|鬼|怪物|尖角|尖牙|利爪|恐怖|"
    r"青筋|眼球突出|牢笼|废墟|阴暗小巷|纹身|名人|患者本人|身份证|住址|手机号|邮箱)",
    re.IGNORECASE,
)


class VoiceFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    voice_gender: VoiceGender
    age_sense: AgeSense
    pitch_level: StrictInt = Field(ge=1, le=5)
    speaking_rate_level: StrictInt | None = Field(default=None, ge=1, le=5)
    timbre: Timbre | None = None
    emotions: list[Emotion] = Field(min_length=1, max_length=6)
    power_level: StrictInt | None = Field(default=None, ge=1, le=5)
    malice_level: StrictInt | None = Field(default=None, ge=1, le=5)

    @field_validator("emotions")
    @classmethod
    def unique_emotions(cls, value: list[Emotion]) -> list[Emotion]:
        if len(set(value)) != len(value):
            raise ValueError("emotions must not contain duplicates")
        return value


class EffectiveVisualFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gender_expression: str
    age_expression: str
    face_shape: str
    skin_texture: str
    facial_expression: str
    gaze: str
    lighting: str
    composition: str
    background: str

    @field_validator("*")
    @classmethod
    def controlled_visual_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("visual feature text must not be empty")
        if len(normalized) > 240:
            raise ValueError("visual feature text is too long")
        if _FORBIDDEN_VISUAL_CONTENT.search(normalized):
            raise ValueError("visual feature contains forbidden content")
        return normalized


class ConfirmedGenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_features: VoiceFeatures
    effective_visual_features: EffectiveVisualFeatures
    generation_mode: GenerationMode = GenerationMode.INITIAL
    doctor_confirmed: bool

    @model_validator(mode="after")
    def require_doctor_confirmation(self) -> ConfirmedGenerationInput:
        if not self.doctor_confirmed:
            raise ValueError("doctor confirmation is required before prompt construction")
        return self


SYSTEM_PROMPT = f"""Prompt template version: {PROMPT_TEMPLATE_VERSION}

你是幻听患者个性化 Avatar 系统的受控人像生成执行器。

只生成一名虚构、非身份化、低刺激的人类写实头像。输出为 1024x1024 正方形 PNG，
正面或不超过 15 度轻微侧脸，人物居中，纯色极简浅色背景。不得推断真实身份、人格、
种族或医学事实，不得生成患者本人、名人或其他真实人物。

永久禁止武器、伤口、血迹、自伤、攻击、暴力场景、恶魔、鬼怪、异兽、危险符号、
面部扭曲、压迫性构图、阴暗场景、文字、logo、水印和额外人物。

医生已经完成 Q1-Q8 检查和视觉特征确认。以 effective_visual_features 为最终视觉输入，
Q1-Q8 只用于保持来源可追溯，不得越过医生确认结果重新强化负面特征。多种情绪必须柔和中和。
最终只生成图片，不输出解释文字。"""


def build_prompt_messages(payload: ConfirmedGenerationInput | dict) -> dict[str, str]:
    data = (
        payload
        if isinstance(payload, ConfirmedGenerationInput)
        else ConfirmedGenerationInput.model_validate(payload)
    )
    source_snapshot = data.voice_features.model_dump(mode="json")
    visual_snapshot = data.effective_visual_features.model_dump(mode="json")
    user_prompt = f"""请执行一次受控人像生成。

生成模式：{data.generation_mode.value}

Q1-Q8 来源快照：
```json
{json.dumps(source_snapshot, ensure_ascii=False, indent=2)}
```

医生确认后的最终视觉特征：
```json
{json.dumps(visual_snapshot, ensure_ascii=False, indent=2)}
```

严格使用最终视觉特征生成低刺激单人写实头像。固定浅色纯色背景、柔和光影、人物居中，
不得添加任何身份信息、叙事场景、暴力、伤害、恐怖化或真实人物复刻内容。"""
    return {
        "system": SYSTEM_PROMPT,
        "user": user_prompt,
        "template_version": PROMPT_TEMPLATE_VERSION,
    }
