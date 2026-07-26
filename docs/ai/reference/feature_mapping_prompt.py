"""V1.1 controlled prompt builder for Q1–Q8 voice-to-appearance mapping.

The module is provider-neutral: it validates the structured form before an
image-provider call and produces the same visual blueprint used by the
delivery document. The integrated product keeps the doctor-confirmation gate
and accepts all six fixed emotions while rendering at most two visible facial
signal groups. This reference remains independent from the runtime adapter.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


PROMPT_TEMPLATE_VERSION = "voice-to-appearance-v1.1"


class GenerationBlockedError(ValueError):
    """Raised before a provider call when the image-risk gate blocks input."""

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


@dataclass(frozen=True)
class VisualBlueprint:
    """A provider-readable, low-stimulus visual plan derived from Q1–Q8."""

    base_structure: tuple[str, ...]
    face_signals: tuple[str, ...]
    voice_texture: tuple[str, ...]
    scene_modulation: tuple[str, ...]
    safety_retention: tuple[str, ...]
    negative_constraints: tuple[str, ...]


def validate_voice_appearance_input(payload: VoiceAppearanceInput | dict) -> VoiceAppearanceInput:
    """Validate a request payload before any provider request is made."""

    if isinstance(payload, VoiceAppearanceInput):
        return payload
    return VoiceAppearanceInput.model_validate(payload)


PORTRAIT_CONTRACT = """## 固定肖像契约

- 输出一张 1024×1024 的 1:1 PNG；调用方也必须把图片接口的 size 固定为 `1024x1024`。
- 单人、虚构、非身份化、写实胸像；正面或不超过 15° 轻微侧脸，眼平视角，人物居中。
- 使用浅暖灰或医疗纸白纯色背景、柔和均匀漫射光、米白/浅灰/浅雾蓝纯色上衣；无首饰、无文字、无 logo、无水印。
- 不把声音映射为种族、具体身份、职业、疾病、人格结论或患者本人长相。
"""


SYSTEM_PROMPT = f"""Prompt template version: {PROMPT_TEMPLATE_VERSION}

你是“幻听患者个性化 Avatar 系统”的受控人像生成提示词执行器。根据医生录入的匿名 Q1–Q8 结构化声音特征生成一名虚构、非身份化、低刺激的人类写实头像。

{PORTRAIT_CONTRACT}

## 执行方式

调用方会给出“视觉蓝图”。必须按蓝图的分层顺序渲染：基础结构 → 面部信号 → 声音质感 → 画面调制 → 安全保留信号。每个已提供字段至少保留一个可见但克制的视觉信号；不得用“中性化”抹去已被安全转换后的信号。

年龄和声音性别只决定基础结构；情绪只决定眉、眼、唇的局部状态；音调和音色决定比例、质感与轮廓；语速只增加或降低微张力，不能改写情绪方向；强大感与恶意感只调节主体比例、明暗和距离感，不能制造威胁性姿态、黑色服装或压迫性构图。

儿童、老年、敏感风险及高冲突输入须执行蓝图中的“安全保留信号”：以指定的低刺激等价信号替代风险效果，而非删除该字段含义。医生覆盖仅能覆盖相应视觉维度，不能突破安全边界。

## 永久禁止

绝不生成真实人物复刻、身份信息、医疗诊断暗示、武器、伤口、血迹、自伤或攻击动作、暴力场景、恶魔/鬼怪、尖牙尖角、恐怖鬼脸、夸张瞪眼、青筋、面部扭曲、纹身、黑暗牢笼/废墟/阴暗小巷、多人、文字或水印。

只生成图片，不输出解释文字。"""


_GENDER_DETAILS = {
    VoiceGender.MALE: "男性基础表达：自然略有结构感的下颌与眉形、常规短发；不夸张性别特征。",
    VoiceGender.FEMALE: "女性基础表达：自然柔和的下颌与眉眼曲线、常规短发或中长发；不添加妆容或饰品。",
    VoiceGender.UNCERTAIN_MIXED: "中性基础表达：不强化性别化骨骼、发型或色调。",
}
_AGE_DETAILS = {
    AgeSense.CHILD: "儿童：短宽幼态脸、五官集中、短鼻梁、圆润下颌与无细纹；温和、非威胁。",
    AgeSense.ADOLESCENT: "青少年：略拉长脸型、舒展五官、无明显细纹、适中轮廓。",
    AgeSense.YOUNG: "青年：均衡成年比例、自然平整皮肤、适中立体感。",
    AgeSense.MIDDLE_AGED: "中年：轻微眼角纹、法令纹与自然松弛，不夸大衰老。",
    AgeSense.ELDERLY: "老年：自然鱼尾纹、法令纹、眼袋和可见灰白眉发；始终暖中性柔光。",
    AgeSense.UNCERTAIN: "青年至中年之间的中性基础结构，不强化幼态或老化。",
}
_PITCH_DETAILS = {
    1: "很低：宽厚轮廓、舒展偏大五官、圆钝下颌和低饱和中性色；不生成尖锐轮廓。",
    2: "偏低：圆润宽厚脸型、偏大五官、柔和低对比光影。",
    3: "中等：均衡脸型、正常五官比例、中性柔和光影。",
    4: "偏高：轻度纤细狭长轮廓、小巧五官、干净浅亮高光；不生成尖脸。",
    5: "很高：纤细狭长比例、紧凑但自然的眉眼、浅亮冷中性细节；不生成凶狠或骨感尖锐。",
}
_RATE_DETAILS = {
    1: "很慢：眉眼舒展、闭唇自然、眼神平缓；紧张度最低。",
    2: "偏慢：轻微放松、低张力；不抹去已有情绪信号。",
    3: "中等：面部肌肉松紧均衡。",
    4: "偏快：仅增加轻微眉眼聚焦与自然闭唇，保持低对比。",
    5: "很快：仅增加可辨识的轻度眉间聚焦和闭唇张力，不能覆盖情绪或形成压迫感。",
}
_TIMBRE_DETAILS = {
    Timbre.HOARSE_ROUGH: "沙哑粗糙：轻度可见的哑光皮肤质感、柔化高光；轮廓仍自然清晰。",
    Timbre.CLEAR_TRANSPARENT: "清亮通透：细腻皮肤、均匀漫射柔光、干净的小范围高光。",
    Timbre.SHARP_PIERCING: "尖锐刺耳：较小巧的五官与轻微清晰轮廓、浅冷中性细节；不产生锐利或凶狠感。",
    Timbre.LOW_RICH: "低沉浑厚：可见的宽厚饱满脸型和自然软组织体积、低饱和中性柔光。",
    Timbre.BREATHY_WEAK: "气声虚弱：较小但仍清晰的主体比例、柔和边缘和低对比光；不失焦或病态化。",
    Timbre.NASAL: "鼻音偏重：自然略饱满的软组织与柔和鼻翼光影、温润质感。",
    Timbre.MUMBLED: "口齿含糊：面部边缘与明暗过渡柔和、轮廓不锐利但五官可辨。",
    Timbre.HEAVY_ACCENT: "厚重口音：略宽厚脸型、柔和层次光影、无高对比暗角。",
    Timbre.FINE_SOFT: "纤细轻柔：小巧轻薄五官、较弱体积感和浅亮柔光；不生成幼态化或脆弱化。",
}
_POWER_DETAILS = {
    1: "很弱：约 45% 主体比例、轻薄体积、浅亮柔光。",
    2: "偏弱：约 55% 主体比例、低体积感、浅淡过渡光。",
    3: "中等：约 65% 居中主体比例、均衡立体、柔和过渡光。",
    4: "偏强：约 72% 主体比例、略饱满立体、浅层柔影。",
    5: "很强：约 78% 主体比例、饱满立体与多层浅柔光；始终眼平、非压迫。",
}
_MALICE_DETAILS = {
    1: "无恶意：暖中性低饱和、松弛眼神、圆润自然五官。",
    2: "轻微恶意：明亮微冷中性、轻微收敛的自然眼神、极浅柔影。",
    3: "中度恶意：明亮低饱和冷中性、克制疏离感和闭唇中性表情；不出现黑衣或眼窝阴影。",
    4: "较强恶意：背景更明亮、低饱和冷中性细节、可辨识的警觉但非威胁眼神；服装保持浅色。",
    5: "很有恶意：明亮低饱和中性画面、克制警觉的自然眼神与平直闭唇；不使用黑衣、凝视、阴影眼窝或压迫感。",
}
_EMOTION_DETAILS = {
    Emotion.ANGER: "轻微眉心收拢、自然闭唇、下颌轻收；禁止怒视、咬牙和明显敌意。",
    Emotion.INDIFFERENCE: "平缓面部、轻微放空但自然的视线、放松肌肉；禁止空洞眼神。",
    Emotion.SARCASM: "可辨识但极浅的单侧嘴角变化、平淡眼神；禁止坏笑、露齿或蔑视。",
    Emotion.SADNESS: "眉眼小幅柔和下垂、放松面部；禁止眼泪、红肿或崩溃。",
    Emotion.FEAR: "内眉轻微上提、自然睁眼和轻度柔和紧张；禁止惊悚瞪眼、惨白或冷汗。",
    Emotion.COMMANDING: "眼平、头颈端正、自然闭唇和稳定姿态；禁止压迫凝视或居高临下。",
}
_EMOTION_LABELS = {
    Emotion.ANGER: "愤怒",
    Emotion.INDIFFERENCE: "冷漠",
    Emotion.SARCASM: "嘲讽",
    Emotion.SADNESS: "悲伤",
    Emotion.FEAR: "恐惧",
    Emotion.COMMANDING: "命令式",
}
_NEGATIVE_CONSTRAINTS = (
    "黑色或深色上衣、首饰、复杂场景、低机位、俯视或仰视压迫构图",
    "强阴影、暗角、阴影眼窝、冷暗光、夸张皱眉、露齿、怒视、咬牙",
    "愤怒或命令式与笑容并存、哭泣、病态化、恐怖化眼神、身份识别线索",
    "文字、logo、水印、多人、真实人物复刻、暴力或恐怖元素",
)


def build_visual_blueprint(payload: VoiceAppearanceInput | dict) -> VisualBlueprint:
    """Return the resolved visual plan used to build provider prompts."""

    data = validate_voice_appearance_input(payload)
    _enforce_risk_gate(data)
    effective_power, effective_malice = _effective_levels(data)

    face_signals, emotion_negatives = _resolve_emotion_signals(data.emotions)
    voice_texture = [_PITCH_DETAILS[data.pitch_level]]
    if data.speaking_rate_level is not None:
        voice_texture.append(_RATE_DETAILS[data.speaking_rate_level])
    if data.timbre is not None:
        voice_texture.append(_TIMBRE_DETAILS[data.timbre])

    scene_modulation = [_POWER_DETAILS[effective_power], _MALICE_DETAILS[effective_malice]]
    safety_retention = _safety_retention(data, effective_power, effective_malice)
    return VisualBlueprint(
        base_structure=(_GENDER_DETAILS[data.voice_gender], _AGE_DETAILS[data.age_sense]),
        face_signals=tuple(face_signals),
        voice_texture=tuple(voice_texture),
        scene_modulation=tuple(scene_modulation),
        safety_retention=tuple(safety_retention),
        negative_constraints=tuple(dict.fromkeys((*_NEGATIVE_CONSTRAINTS, *emotion_negatives))),
    )


def build_user_prompt(payload: VoiceAppearanceInput | dict) -> str:
    """Build the dynamic user message for providers with system/user messages."""

    data = validate_voice_appearance_input(payload)
    blueprint = build_visual_blueprint(data)
    effective_power, effective_malice = _effective_levels(data)
    power_origin = (
        "未填写，使用 3 档内部中性基线，不视为医生明确观察事实"
        if data.power_level is None
        else "来自医生填写"
    )
    malice_origin = (
        "未填写，使用 3 档内部中性基线，不视为医生明确观察事实"
        if data.malice_level is None
        else "来自医生填写"
    )
    overrides = (
        "无医生覆盖，以视觉蓝图为准。"
        if not data.doctor_overrides
        else json.dumps(data.doctor_overrides, ensure_ascii=False, sort_keys=True)
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
    return f"""请执行一次受控的人像生成，只生成图片，不输出解释文字。

## 本次结构化输入

```json
{json.dumps(input_snapshot, ensure_ascii=False, indent=2)}
```

## 视觉蓝图

- 基础结构：{_join(blueprint.base_structure)}
- 面部信号（最多两组局部可见信号）：{_join(blueprint.face_signals)}
- 声音质感：{_join(blueprint.voice_texture)}
- 画面调制：{_join(blueprint.scene_modulation)}
- 安全保留信号：{_join(blueprint.safety_retention)}
- 负向约束：{_join(blueprint.negative_constraints)}

## 执行参数与覆盖

- 有效强大感：{effective_power} 档（{power_origin}）；有效恶意感：{effective_malice} 档（{malice_origin}）。
- 医生确认的视觉覆盖：{overrides}
- 风险等级：{data.risk_level}；生成模式：{data.generation_mode}。
- 先严格满足固定肖像契约，再按视觉蓝图渲染。每项已提供的表单特征都要保留至少一个可见、克制且安全的信号；禁止用中性化抹去这些信号。"""


def build_image_prompt(payload: VoiceAppearanceInput | dict) -> str:
    """Build one provider-neutral prompt string for APIs accepting ``prompt`` only."""

    return f"{SYSTEM_PROMPT}\n\n{build_user_prompt(payload)}"


def build_prompt_messages(payload: VoiceAppearanceInput | dict) -> dict[str, str]:
    """Build messages for providers that expose separate system and user fields."""

    return {"system": SYSTEM_PROMPT, "user": build_user_prompt(payload)}


def _resolve_emotion_signals(emotions: list[Emotion]) -> tuple[list[str], list[str]]:
    """Resolve up to two compatible, observable facial-signal groups."""

    selected = set(emotions)
    signals: list[str] = []
    negatives: list[str] = []
    if Emotion.ANGER in selected and Emotion.COMMANDING in selected:
        signals.append("克制的愤怒/命令式：轻微眉心收拢、自然闭唇、下颌轻收、头颈端正。")
        negatives.append("愤怒或命令式时不得出现任何笑容")
        selected -= {Emotion.ANGER, Emotion.COMMANDING}

    priority = (
        Emotion.ANGER,
        Emotion.FEAR,
        Emotion.SADNESS,
        Emotion.SARCASM,
        Emotion.COMMANDING,
        Emotion.INDIFFERENCE,
    )
    for emotion in priority:
        if emotion in selected and len(signals) < 2:
            signals.append(f"{_EMOTION_LABELS[emotion]}：{_EMOTION_DETAILS[emotion]}")
            if emotion in {Emotion.ANGER, Emotion.COMMANDING}:
                negatives.append("愤怒或命令式时不得出现任何笑容")

    if len(emotions) > 2:
        signals.append("其余情绪仅作为与前述信号相容的轻度气质，不增加第三组夸张面部动作。")
    return signals, negatives


def _safety_retention(
    data: VoiceAppearanceInput, effective_power: int, effective_malice: int
) -> list[str]:
    notes = ["始终保留浅色服装、明亮背景、眼平构图和柔和均匀光线。"]
    raw_power = data.power_level or 3
    raw_malice = data.malice_level or 3

    if data.age_sense == AgeSense.CHILD:
        notes.append(
            "儿童保护：保留温和幼态结构；负面情绪只保留轻微、自然的眉眼信号，不表现惊恐、敌意或痛苦。"
        )
    if data.age_sense == AgeSense.ELDERLY and raw_malice >= 4:
        notes.append(
            "老年高恶意安全等价：保留明亮低饱和冷中性与轻微警觉眼神，不使用冷暗光、尖锐骨相或攻击性表情。"
        )
    if raw_power >= 4 and raw_malice >= 4:
        notes.append(
            "高强大感与高恶意安全等价：保留稳定、饱满但非压迫的胸像比例和克制闭唇；背景提亮且阴影最小化。"
        )
    if data.risk_level == RiskLevel.SENSITIVE:
        notes.append(
            "敏感风险柔和化：保留特征含义，但使用更低对比、更浅阴影和更温和的局部表情。"
        )
    if raw_power != effective_power or raw_malice != effective_malice:
        notes.append("已执行安全上限；被限制字段以以上安全等价线索保留，不得清空其映射含义。")
    return notes


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


def _join(values: tuple[str, ...] | list[str]) -> str:
    return "；".join(values)


_FORBIDDEN_OVERRIDE_RE = re.compile(
    r"(武器|刀|枪|伤口|血迹|自残|自杀|攻击|暴力|恶魔|鬼|怪物|尖角|尖牙|利爪|恐怖|青筋|眼球突出|牢笼|废墟|阴暗小巷|纹身|名人|患者本人|身份证|住址|手机号|邮箱)",
    re.IGNORECASE,
)


def _contains_forbidden_override_content(text: str) -> bool:
    return bool(_FORBIDDEN_OVERRIDE_RE.search(text))
