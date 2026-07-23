"""V1 one-step image-generation prompt for Q1-Q8 voice features.

This module deliberately does not replace the legacy demo prompt in
``app.adapters``.  It is the provider-neutral prompt contract for the target
V1 feature-mapping/image-generation adapter.
"""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


PROMPT_TEMPLATE_VERSION = "voice-to-appearance-v1.0"


class GenerationBlockedError(ValueError):
    """Raised before an image provider call when the risk gate blocks input."""

    def __init__(self, message: str, *, risk_level: str, code: str):
        super().__init__(message)
        self.risk_level = risk_level
        self.code = code


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


class RiskLevel(StrEnum):
    NORMAL = "normal"
    SENSITIVE = "sensitive"
    CRISIS = "crisis"
    HIGH_STIMULUS = "high_stimulus"


class GenerationMode(StrEnum):
    INITIAL = "initial"
    SAME_FEATURES_REGENERATE = "same_features_regenerate"
    FEATURE_UPDATE = "feature_update"


OverrideKey = Literal[
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


class VoiceAppearanceInput(BaseModel):
    """Validated V1 input accepted by the prompt builder."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    voice_gender: VoiceGender
    age_sense: AgeSense
    pitch_level: StrictInt = Field(ge=1, le=5)
    speaking_rate_level: StrictInt | None = Field(default=None, ge=1, le=5)
    timbre: Timbre | None = None
    emotions: list[Emotion] = Field(min_length=1, max_length=6)
    power_level: StrictInt | None = Field(default=None, ge=1, le=5)
    malice_level: StrictInt | None = Field(default=None, ge=1, le=5)
    risk_level: RiskLevel
    doctor_overrides: dict[OverrideKey, str] = Field(default_factory=dict)
    generation_mode: GenerationMode = GenerationMode.INITIAL

    @field_validator("emotions")
    @classmethod
    def unique_emotions(cls, value: list[Emotion]) -> list[Emotion]:
        if len(set(value)) != len(value):
            raise ValueError("emotions must not contain duplicates")
        return value

    @field_validator("doctor_overrides")
    @classmethod
    def safe_doctor_overrides(cls, value: dict[OverrideKey, str]) -> dict[OverrideKey, str]:
        for key, text in value.items():
            if not text.strip():
                raise ValueError(f"doctor_overrides.{key} must not be empty")
            if len(text) > 240:
                raise ValueError(f"doctor_overrides.{key} is too long")
            if _contains_forbidden_override_content(text):
                raise ValueError(f"doctor_overrides.{key} contains forbidden content")
        return value


def validate_voice_appearance_input(payload: VoiceAppearanceInput | dict) -> VoiceAppearanceInput:
    """Validate a request payload before any provider request is made."""

    if isinstance(payload, VoiceAppearanceInput):
        return payload
    return VoiceAppearanceInput.model_validate(payload)


SYSTEM_PROMPT = f"""Prompt template version: {PROMPT_TEMPLATE_VERSION}

你是幻听患者个性化 Avatar 系统的受控人像生成提示词执行器。

你的唯一任务是：根据医生在 V1 Q1–Q8 表单中录入的匿名、结构化声音特征，生成一个虚构的、非身份化的、低刺激的人类写实头像。声音特征只能映射为抽象且可编辑的外貌、表情、眼神、光影和构图维度，不得声称推断真实身份、人格、种族、医学事实或患者本人长相。

## 输出目标

- 只生成一名虚构人类人物，写实头像，1024×1024 正方形 PNG。
- 正面或不超过 15° 的轻微侧脸，人物居中，纯色极简浅色背景。
- 面部细节自然、光影柔和、低刺激、无文字、无 logo、无水印、无额外人物。
- 不生成场景叙事；声音特征只影响面部与受控画面维度。

## 输入字段边界

只使用以下 Q1–Q8 字段：voice_gender、age_sense、pitch_level、speaking_rate_level、timbre、emotions、power_level、malice_level。情绪只能是 anger、indifference、sarcasm、sadness、fear、commanding 六种固定值。不得使用患者自由文本、身份信息、额外情绪、自定义人格或医学描述。

## 基础属性映射

- male：男性基础面部表达，下颌和眉骨可略有结构感、偏粗眉形、常规短发；不得生成刻板或夸张性别特征。
- female：女性基础面部表达，下颌较圆润、眉眼曲线柔和、软组织自然饱满、常规短发或中长发。
- uncertain_mixed：中性面部表达，不强化男性或女性骨骼、发型或色调。
- child：短宽幼态脸、五官集中、短鼻梁、光滑无皱纹、圆润下颌；必须中性、温和、非威胁。
- adolescent：面部略拉长、五官舒展、无明显细纹、轮廓锋利度中等。
- young：均衡成年人比例，皮肤平整，立体感适中。
- middle_aged：轻微眼角纹和法令纹、轻微松弛，不夸大衰老。
- elderly：自然鱼尾纹、法令纹、松弛和眼袋，眉发可稀疏变白；强制暖中性柔光。
- uncertain：青年至中年之间的中性表达，不强化幼态或老化。

## 音调映射 pitch_level 1–5

1 很低：面部宽大厚重、下颌方正、五官舒展偏大、低饱和中性色调；轮廓锋利度不超过 3。
2 偏低：面部圆润宽厚、五官偏大、柔和低对比光影；整体表情冲击力降低一档。
3 中等：标准均衡脸型、正常五官比例、中性柔和光影。
4 偏高：面部纤细狭长、五官小巧、轻微高光提亮；轮廓锋利度不超过 4，禁止尖脸畸形。
5 很高：狭长纤细脸、眉眼紧凑、浅亮柔和冷中性色调；有负面情绪时进一步削弱凶狠观感。

## 语速映射 speaking_rate_level 1–5

1 很慢：面部完全放松、眉眼舒展、嘴唇自然、眼神平缓；紧绷表现锁定最低。
2 偏慢：面部轻微放松、无紧绷感；负面神态冲击力降低。
3 中等：面部肌肉松紧均衡，正常表达。
4 偏快：眉眼轻微收拢、嘴唇微抿、眼神活跃；只增加细碎柔和高光，不制造压迫感。
5 很快：眉头轻收、嘴唇自然闭合、眼神轻微紧绷；降低画面对比度并弱化阴影。

## 音色映射 timbre

- hoarse_rough：较厚的皮肤纹理、哑光柔光、减少锐利高光；不强化锋利轮廓。
- clear_transparent：细腻皮肤、均匀漫射柔光、干净柔和高光、无厚重阴影。
- sharp_piercing：五官纤细小巧、轮廓仅轻微清晰、浅冷低饱和；凶狠表情严格弱化。
- low_rich：宽厚饱满脸型、软组织自然厚重、低饱和中性柔光、五官舒展。
- breathy_weak：人物画面占比偏小、柔光虚化、低对比、无硬阴影。
- nasal：软组织略饱满、鼻翼光影柔和、温润质感、无尖锐面部线条。
- mumbled：面部边缘和光影过渡柔和，不生成清晰锋利轮廓；负面情绪下大幅降低紧绷感。
- heavy_accent：脸型略宽厚、柔和层次光影、无高对比暗角；快语速时进一步降低阴影。
- fine_soft：五官小巧轻薄、立体感较弱、浅亮柔光、无厚重下颌。

音色为单选。高风险或高恶意时清空音色的锋利、厚重和冷调效果。儿童与冷调音色组合时强制暖柔光。

## 固定情绪映射

- anger：眉头轻微收拢、嘴唇轻合、下颌轻微收紧；禁止咬牙、青筋、扭曲和瞪眼。
- indifference：面部平缓、视线轻微放空、肌肉放松；禁止空洞白眼和发黑眼窝。
- sarcasm：单侧嘴角极细微上扬、眼神平淡；禁止坏笑、露齿、蔑视和俯视构图。
- sadness：眉眼小幅柔和下垂、面部松弛；禁止大哭、泪痕、红肿和崩溃。
- fear：眉眼轻微抬起、瞳孔自然小幅放大、柔和紧绷；禁止惊悚瞪眼、惨白、冷汗和扭曲。
- commanding：端正平视、轮廓清晰平缓；禁止压迫凝视、狰狞和居高临下。

多情绪必须中和，不叠加刺激效果。儿童勾选任何负面情绪时只保留非常轻微、温和、幼态的神态。恶意感升高时，负面神态逐级弱化，最多累计弱化两层。

## 强大感与恶意感

未填写的 power_level 或 malice_level 使用 3 作为内部中性基线，但不得把未填写说成明确观察事实。

power_level：1 为小比例、轻薄、浅亮、强虚化；2 为约 50% 画面占比、低立体度；3 为约 60% 居中、均衡立体；4 为约 75% 主体占比、浅层柔和阴影；5 为约 85% 近景、饱满立体和多层浅柔光。禁止硬阴影、暗角、俯视压迫构图。敏感风险最高执行 3，危机不执行生图。

malice_level：1 为暖调、松弛眼神、圆润五官；2 为极淡微冷中性、轻微收敛眼神；3 为轻微偏冷低饱和、浅层眼窝和下颌柔影；4 为浅冷中性、提亮背景并弱化锋利五官；5 仍只能是浅微冷、低饱和、极淡单层阴影和圆润五官。禁止黑暗画面、凶狠凝视和尖锐骨骼。儿童强制为 1，老年高恶意自动降至 2。

power_level ≥ 4 且 malice_level ≥ 4 时，两者均不超过 3，并提亮画面、弱化阴影。存在负面情绪时，恶意感每增加一档就再降低负面神态一层，最多两层。

## 风险与优先级

优先级从高到低：高刺激/危机拦截 > 永久禁止元素 > 儿童/老年年龄安全约束 > 敏感风险柔和降级 > 医生确认特征 > 声音映射细节 > 默认中性基线。

- normal：执行映射，但仍遵守所有禁止元素和低刺激约束。
- sensitive：降低对比度和阴影，弱化冷调、锋利度和负面神态，背景保持浅色。
- crisis/high_stimulus：不得生成图像。调用方必须在进入图像 API 前拦截；如果仍收到此状态，只返回安全占位，不生成任何视觉内容。

医生确认的视觉覆盖项优先于自动映射，但不能突破本节安全边界。不得把医生覆盖项解释为真实身份或医学事实。

## 永久禁止

绝不生成武器、伤口、血迹、攻击动作、自伤动作、暴力场景、恶魔、鬼怪、异兽、尖角、尖牙、利爪、恐怖鬼脸、眼球突出、青筋、面部扭曲、危险符号、纹身、阴暗牢笼、废墟、阴暗小巷、真实人物、名人面孔、患者本人复刻、姓名、身份证、住址或其他身份信息。

最终输出必须是一张低刺激的、单人、虚构、写实头像，不输出解释文字，不加入额外对象或叙事场景。"""


_GENDER_LABELS = {
    VoiceGender.MALE: "男声",
    VoiceGender.FEMALE: "女声",
    VoiceGender.UNCERTAIN_MIXED: "不确定/混合",
}
_AGE_LABELS = {
    AgeSense.CHILD: "儿童",
    AgeSense.ADOLESCENT: "青少年",
    AgeSense.YOUNG: "青年",
    AgeSense.MIDDLE_AGED: "中年",
    AgeSense.ELDERLY: "老年",
    AgeSense.UNCERTAIN: "不确定",
}
_TIMBRE_LABELS = {
    Timbre.HOARSE_ROUGH: "沙哑粗糙",
    Timbre.CLEAR_TRANSPARENT: "清亮通透",
    Timbre.SHARP_PIERCING: "尖锐刺耳",
    Timbre.LOW_RICH: "低沉浑厚",
    Timbre.BREATHY_WEAK: "气声虚弱",
    Timbre.NASAL: "鼻音偏重",
    Timbre.MUMBLED: "口齿含糊",
    Timbre.HEAVY_ACCENT: "厚重口音",
    Timbre.FINE_SOFT: "纤细轻柔",
}
_EMOTION_LABELS = {
    Emotion.ANGER: "愤怒",
    Emotion.INDIFFERENCE: "冷漠",
    Emotion.SARCASM: "嘲讽",
    Emotion.SADNESS: "悲伤",
    Emotion.FEAR: "恐惧",
    Emotion.COMMANDING: "命令式",
}

_PITCH_DETAILS = {
    1: "很低：宽厚方正轮廓、舒展偏大五官、低饱和中性色，锋利度上限 3",
    2: "偏低：圆润宽厚轮廓、偏大五官、柔和低对比光影，表情冲击力降低",
    3: "中等：标准均衡脸型、正常五官比例、中性柔和光影",
    4: "偏高：纤细狭长轮廓、小巧五官、轻微高光，锋利度上限 4",
    5: "很高：狭长纤细脸、紧凑眉眼、浅亮冷中性色，有负面情绪时削弱凶狠感",
}
_RATE_DETAILS = {
    1: "很慢：面部完全放松、眉眼舒展、眼神平缓，紧绷表现最低",
    2: "偏慢：面部轻微放松、无紧绷感，负面神态冲击力降低",
    3: "中等：面部肌肉松紧均衡，正常表达",
    4: "偏快：眉眼微收、嘴唇微抿、眼神活跃，只增加柔和细碎高光",
    5: "很快：眉头轻收、嘴唇自然闭合、眼神轻微紧绷，降低对比度并弱化阴影",
}
_POWER_DETAILS = {
    1: "很弱：约 40% 以内画面占比、轻薄面部、大面积虚化、无暗阴影",
    2: "偏弱：约 50% 画面占比、轻微虚化、浅淡过渡光影",
    3: "中等：约 60% 居中占比、均衡立体、柔和过渡光",
    4: "偏强：约 75% 主体占比、轮廓略加厚、浅层柔和阴影",
    5: "很强：约 85% 近景、饱满立体、多层浅柔光，不使用压迫构图",
}
_MALICE_DETAILS = {
    1: "无恶意：暖调低饱和、松弛眼神、无面部阴影、圆润五官",
    2: "轻微恶意：极淡微冷中性、眼神轻微收敛、极浅柔影",
    3: "中度恶意：轻微偏冷低饱和、浅层眼窝和下颌柔影、轮廓略收紧",
    4: "较强恶意：浅冷中性、背景提亮、弱化锋利五官和负面神态",
    5: "很有恶意：浅微冷低饱和、极淡单层阴影、五官圆润化、全局高亮柔光",
}
_TIMBRE_DETAILS = {
    Timbre.HOARSE_ROUGH: "皮肤纹理略厚、哑光柔光、减少锐利高光",
    Timbre.CLEAR_TRANSPARENT: "细腻皮肤、均匀漫射柔光、干净柔和高光",
    Timbre.SHARP_PIERCING: "纤细小巧五官、轮廓仅轻微清晰、浅冷低饱和",
    Timbre.LOW_RICH: "宽厚饱满脸型、自然厚重软组织、中性柔光",
    Timbre.BREATHY_WEAK: "人物占比偏小、柔光虚化、低对比、无硬阴影",
    Timbre.NASAL: "软组织略饱满、鼻翼柔和光影、温润质感",
    Timbre.MUMBLED: "面部边缘柔和、轮廓不锐利、明暗无硬边界",
    Timbre.HEAVY_ACCENT: "脸型略宽厚、柔和层次光影、无高对比暗角",
    Timbre.FINE_SOFT: "五官小巧轻薄、立体感较弱、浅亮柔光",
}
_EMOTION_DETAILS = {
    Emotion.ANGER: "眉头轻微收拢、嘴唇轻合、下颌轻微收紧；禁止咬牙、青筋、扭曲和瞪眼",
    Emotion.INDIFFERENCE: "面部平缓、视线轻微放空、肌肉放松；禁止空洞白眼和发黑眼窝",
    Emotion.SARCASM: "单侧嘴角极细微上扬、眼神平淡；禁止坏笑、露齿、蔑视和俯视",
    Emotion.SADNESS: "眉眼小幅柔和下垂、面部松弛；禁止大哭、泪痕、红肿和崩溃",
    Emotion.FEAR: "眉眼轻微抬起、瞳孔自然小幅放大、柔和紧绷；禁止惊悚瞪眼、惨白和冷汗",
    Emotion.COMMANDING: "端正平视、轮廓清晰平缓；禁止压迫凝视、狰狞和居高临下",
}


def build_user_prompt(payload: VoiceAppearanceInput | dict) -> str:
    """Build the dynamic user message for a provider supporting system/user messages."""

    data = validate_voice_appearance_input(payload)
    _enforce_risk_gate(data)
    effective_power, effective_malice = _effective_levels(data)

    timbre_text = "未填写：不增加音色专属视觉要求"
    if data.timbre:
        timbre_text = f"{_TIMBRE_LABELS[data.timbre]}：{_TIMBRE_DETAILS[data.timbre]}"
    rate_text = "未填写：不增加语速专属视觉要求"
    if data.speaking_rate_level is not None:
        rate_text = _RATE_DETAILS[data.speaking_rate_level]
    overrides = (
        "无医生覆盖，以系统映射为准。"
        if not data.doctor_overrides
        else json.dumps(data.doctor_overrides, ensure_ascii=False, sort_keys=True)
    )
    emotion_text = "；".join(
        f"{_EMOTION_LABELS[emotion]}：{_EMOTION_DETAILS[emotion]}" for emotion in data.emotions
    )
    input_snapshot = {
        "voice_gender": data.voice_gender,
        "age_sense": data.age_sense,
        "pitch_level": data.pitch_level,
        "speaking_rate_level": data.speaking_rate_level,
        "timbre": data.timbre,
        "emotions": list(data.emotions),
        "power_level": data.power_level,
        "malice_level": data.malice_level,
        "risk_level": data.risk_level,
        "generation_mode": data.generation_mode,
    }
    return f"""请执行一次受控的人像生成，不要输出解释文字。

## 本次结构化输入

```json
{json.dumps(input_snapshot, ensure_ascii=False, indent=2)}
```

## 本次映射要求

- 声音性别：{_GENDER_LABELS[data.voice_gender]}
- 年龄感：{_AGE_LABELS[data.age_sense]}
- 音调：{_PITCH_DETAILS[data.pitch_level]}
- 语速：{rate_text}
- 音色：{timbre_text}
- 固定情绪：{emotion_text}
- 强大感：{effective_power} 档，{_POWER_DETAILS[effective_power]}
- 恶意感：{effective_malice} 档，{_MALICE_DETAILS[effective_malice]}
- 风险等级：{data.risk_level}
- 生成模式：{data.generation_mode}
- 医生确认的视觉覆盖：{overrides}

## 最终执行

将以上要求中和为低刺激的、非身份化的单人写实头像。医生覆盖项只能覆盖对应视觉维度，不能突破安全上限。固定使用正面或不超过 15° 轻微侧脸、人物居中、纯色极简浅色背景、1024×1024 正方形构图。禁止文字、logo、水印、额外人物、负面场景、暴力、伤害、恐怖化、恶魔化、真实人物复刻和身份信息。"""


def build_image_prompt(payload: VoiceAppearanceInput | dict) -> str:
    """Build one provider-neutral prompt string for APIs accepting ``prompt`` only."""

    return f"{SYSTEM_PROMPT}\n\n{build_user_prompt(payload)}"


def build_prompt_messages(payload: VoiceAppearanceInput | dict) -> dict[str, str]:
    """Build messages for providers that expose separate system and user fields."""

    return {"system": SYSTEM_PROMPT, "user": build_user_prompt(payload)}


def _enforce_risk_gate(data: VoiceAppearanceInput) -> None:
    if data.risk_level in {RiskLevel.CRISIS, RiskLevel.HIGH_STIMULUS}:
        raise GenerationBlockedError(
            "风险等级要求拦截本次生图请求，不得调用图像生成 API。",
            risk_level=data.risk_level,
            code="IMAGE_GENERATION_BLOCKED",
        )


def _effective_levels(data: VoiceAppearanceInput) -> tuple[int, int]:
    power = data.power_level or 3
    malice = data.malice_level or 3

    if data.age_sense == AgeSense.CHILD:
        power = min(power, 2)
        malice = 1 if malice >= 2 else malice
    elif data.age_sense == AgeSense.ELDERLY and malice >= 4:
        malice = 2

    if data.risk_level == RiskLevel.SENSITIVE:
        power = min(power, 3)
        malice = min(malice, 3)

    if power >= 4 and malice >= 4:
        power = min(power, 3)
        malice = min(malice, 3)

    return power, malice


_FORBIDDEN_OVERRIDE_RE = re.compile(
    r"(武器|刀|枪|伤口|血迹|自残|自杀|攻击|暴力|恶魔|鬼|怪物|尖角|尖牙|利爪|恐怖|青筋|眼球突出|牢笼|废墟|阴暗小巷|纹身|名人|患者本人|身份证|住址|手机号|邮箱)",
    re.IGNORECASE,
)


def _contains_forbidden_override_content(text: str) -> bool:
    return bool(_FORBIDDEN_OVERRIDE_RE.search(text))
