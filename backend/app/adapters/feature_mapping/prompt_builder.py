from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.domain.enums import GenerationMode
from app.services.text_normalization import normalize_multilingual_text

PROMPT_TEMPLATE_VERSION = "voice-to-appearance-v1.1"


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
    r"想死|不想活|轻生|自尽|结束生命|不要醒来|青筋|眼球突出|牢笼|废墟|阴暗小巷|"
    r"纹身|名人|患者本人|身份证|住址|手机号|邮箱|suicid(?:e|al)|want to die|"
    r"do not want to live|don't want to live|end my life|kill myself|never wake up)",
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
        if _FORBIDDEN_VISUAL_CONTENT.search(normalize_multilingual_text(normalized)):
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


PORTRAIT_CONTRACT = """## 固定肖像契约

- 输出一张 1024×1024 的 1:1 PNG；单人、虚构、非身份化、写实胸像。
- 正面或不超过 15° 的轻微侧脸，眼平视角，人物居中。
- 使用浅暖灰或医疗纸白纯色背景、柔和均匀漫射光。
- 使用米白、浅灰或浅雾蓝纯色上衣；无首饰、文字、logo 或水印。
- 不把声音映射为种族、具体身份、职业、疾病、人格结论或患者本人长相。
"""


SYSTEM_PROMPT = f"""Prompt template version: {PROMPT_TEMPLATE_VERSION}

你是“幻听患者个性化 Avatar 系统”的受控人像生成提示词执行器。只生成一名虚构、
非身份化、低刺激的人类写实头像。

{PORTRAIT_CONTRACT}

## 执行方式

医生已经完成 Q1–Q8 检查、受控声音到视觉转换和最终视觉特征确认。
effective_visual_features 是唯一可执行的视觉蓝图，必须按基础结构 → 面部信号 →
声音质感 → 画面调制 → 安全保留信号的顺序渲染。每项医生确认后的视觉特征都必须
保留一项可见、克制且安全的信号，不得用中性化抹去已完成安全转换的特征。

Q1–Q8 来源快照仅用于来源追溯和约束一致性，不得越过医生确认结果重新推断、强化或
增加视觉特征。情绪只能影响眉、眼、唇的局部状态，最多呈现两组可见面部信号；
其余已选情绪只能作为相容的轻度气质。语速只能调节微张力，不能覆盖情绪方向。
强大感和恶意感只能调节已确认的主体比例、明暗与距离感，不能制造黑衣、低机位、
压迫姿态、威胁凝视或强阴影。愤怒或命令式存在时不得出现任何笑容。

儿童、老年和高冲突组合必须使用已确认特征中的低刺激安全等价信号，而不是删除字段
含义。医生覆盖只能修改对应视觉维度，不能突破固定肖像契约或永久禁止项。

## 永久禁止

绝不生成真实人物复刻、身份信息、医疗诊断暗示、武器、伤口、血迹、自伤或攻击动作、
暴力场景、恶魔、鬼怪、尖牙尖角、恐怖鬼脸、夸张瞪眼、青筋、面部扭曲、纹身、
黑暗牢笼、废墟、阴暗小巷、多人、文字或水印。

只生成图片，不输出解释文字。"""


def build_prompt_messages(payload: ConfirmedGenerationInput | dict) -> dict[str, str]:
    data = (
        payload
        if isinstance(payload, ConfirmedGenerationInput)
        else ConfirmedGenerationInput.model_validate(payload)
    )
    source_snapshot = data.voice_features.model_dump(mode="json")
    visual_snapshot = data.effective_visual_features.model_dump(mode="json")
    user_prompt = f"""请执行一次受控的人像生成，只生成图片，不输出解释文字。

生成模式：{data.generation_mode.value}

Q1-Q8 来源快照：
```json
{json.dumps(source_snapshot, ensure_ascii=False, indent=2)}
```

医生确认后的最终视觉蓝图：
```json
{json.dumps(visual_snapshot, ensure_ascii=False, indent=2)}
```

严格使用医生确认后的最终视觉蓝图，并依次落实基础结构、局部面部信号、声音质感、
画面调制和安全保留信号。每项已确认视觉特征都要留下至少一个可见、克制且安全的信号。
固定浅色纯色背景、浅色纯色上衣、柔和均匀光影、眼平居中构图；不得添加身份信息、
叙事场景、暴力、伤害、恐怖化或真实人物复刻内容。"""
    return {
        "system": SYSTEM_PROMPT,
        "user": user_prompt,
        "template_version": PROMPT_TEMPLATE_VERSION,
    }
