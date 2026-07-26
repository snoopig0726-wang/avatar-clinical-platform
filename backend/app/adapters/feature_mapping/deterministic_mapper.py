from __future__ import annotations

from dataclasses import dataclass

from app.adapters.feature_mapping.prompt_builder import EffectiveVisualFeatures, VoiceFeatures

MAPPING_VERSION = "deterministic-voice-appearance-v1.1"

CONTROLLED_VISUAL_OPTIONS: dict[str, list[str]] = {
    "gender_expression": [
        "中性自然表达，不强化性别刻板特征",
        "男性基础面部表达，轮廓保持自然柔和",
        "女性基础面部表达，眉眼与轮廓保持自然柔和",
    ],
    "age_expression": [
        "弱化年龄特征，保持青年至中年之间的中性表达",
        "保持与声音年龄感一致的轻度年龄特征",
        "进一步柔化年龄细节，不夸大幼态或衰老",
    ],
    "face_shape": [
        "标准均衡脸型，轮廓保持圆润柔和",
        "脸型略宽厚，降低轮廓锋利度",
        "脸型略纤细，禁止尖脸或畸形比例",
    ],
    "skin_texture": [
        "皮肤纹理自然细腻，避免锐利高光",
        "皮肤纹理轻柔哑光，降低细节对比",
        "皮肤质感自然，不强化皱纹或瑕疵",
    ],
    "facial_expression": [
        "保持平静、自然、轻微放松",
        "保留极轻微情绪线索并进行柔和中和",
        "进一步弱化负面神态，禁止夸张表情",
    ],
    "gaze": [
        "视线自然平缓，不形成压迫凝视",
        "正面平视，眼神保持温和清晰",
        "视线轻微放松，避免瞪视或空洞感",
    ],
    "lighting": [
        "柔和漫射光，降低阴影和对比度",
        "暖中性柔光，面部阴影保持极浅",
        "浅亮中性光，禁止硬阴影和暗角",
    ],
    "composition": [
        "人物居中，正面头像，保持舒适观察距离",
        "人物居中，允许不超过十五度轻微侧脸",
        "适度缩小人物占比，避免近距离压迫构图",
    ],
    "background": [
        "浅色纯色背景，干净且非压迫",
        "暖浅灰纯色背景，无图案和叙事场景",
        "浅米色纯色背景，保持低对比度",
    ],
}


@dataclass(frozen=True)
class MappingResult:
    features: EffectiveVisualFeatures
    explanation: dict[str, object]


def _effective_levels(data: VoiceFeatures) -> tuple[int, int, list[str]]:
    power = data.power_level if data.power_level is not None else 3
    malice = data.malice_level if data.malice_level is not None else 3
    applied: list[str] = []
    if data.age_sense == "child":
        power = min(power, 2)
        malice = 1
        applied.append("儿童安全约束：强大感最高二档、恶意感锁定一档")
    elif data.age_sense == "elderly" and malice >= 4:
        malice = 2
        applied.append("老年高恶意安全等价：恶意感降至二档并保留轻微警觉信号")
    if power >= 4 and malice >= 4:
        power = 3
        malice = 3
        applied.append("高强大感与高恶意感联动：两者降至三档并提亮背景、最小化阴影")
    return power, malice, applied


def _resolve_emotion_text(emotions: list[str], *, is_child: bool) -> str:
    emotion_signals = {
        "anger": "愤怒：轻微眉心收拢、自然闭唇、下颌轻收",
        "indifference": "冷漠：平缓面部、轻微放空但自然的视线、放松肌肉",
        "sarcasm": "嘲讽：可辨识但极浅的单侧嘴角变化、平淡眼神",
        "sadness": "悲伤：眉眼小幅柔和下垂、放松面部",
        "fear": "恐惧：内眉轻微上提、自然睁眼和轻度柔和紧张",
        "commanding": "命令式：眼平、头颈端正、自然闭唇和稳定姿态",
    }
    selected = set(emotions)
    signals: list[str] = []
    if {"anger", "commanding"} <= selected:
        signals.append(
            "克制的愤怒/命令式：轻微眉心收拢、自然闭唇、下颌轻收、头颈端正"
        )
        selected -= {"anger", "commanding"}

    priority = ("anger", "fear", "sadness", "sarcasm", "commanding", "indifference")
    for emotion in priority:
        if emotion in selected and len(signals) < 2:
            signals.append(emotion_signals[emotion])

    notes = ["；".join(signals)]
    if len(emotions) > 2:
        notes.append("其余情绪仅作为相容的轻度气质，不增加第三组面部动作")
    if {"anger", "commanding"} & set(emotions):
        notes.append("不得出现任何笑容")
    if is_child:
        notes.append("儿童保护：只保留温和自然的轻微眉眼信号，不表现惊恐、敌意或痛苦")
    return "；".join(notes)


def map_voice_to_visual(data: VoiceFeatures) -> MappingResult:
    gender = {
        "male": "男性基础表达，下颌与眉形自然略有结构感，常规短发，不夸张性别特征",
        "female": "女性基础表达，下颌与眉眼曲线自然柔和，常规短发或中长发，无妆容与饰品",
        "uncertain_mixed": "中性基础表达，不强化性别化骨骼、发型或色调",
    }[data.voice_gender]
    age = {
        "child": "儿童短宽幼态脸，五官集中、短鼻梁、圆润下颌且无细纹，始终温和非威胁",
        "adolescent": "青少年略拉长脸型、舒展五官、无明显细纹且轮廓适中",
        "young": "青年均衡成年比例、自然平整皮肤与适中立体感",
        "middle_aged": "中年轻微眼角纹、法令纹与自然松弛，不夸大衰老",
        "elderly": "老年自然鱼尾纹、法令纹、眼袋和可见灰白眉发，使用暖中性柔光",
        "uncertain": "青年至中年之间的中性基础结构，不强化幼态或老化",
    }[data.age_sense]
    face_shape = {
        1: "宽厚轮廓、舒展偏大五官与圆钝下颌，禁止尖锐轮廓",
        2: "圆润宽厚脸型、偏大五官与柔和低锋利度轮廓",
        3: "均衡脸型、正常五官比例与圆润自然轮廓",
        4: "轻度纤细狭长轮廓和小巧五官，禁止尖脸或夸张比例",
        5: "纤细狭长比例、紧凑但自然的眉眼，禁止凶狠或骨感尖锐",
    }[data.pitch_level]
    skin_texture = {
        None: "皮肤纹理自然细腻，使用均匀柔和高光且无厚重阴影",
        "hoarse_rough": "轻度可见的哑光皮肤质感并柔化高光",
        "clear_transparent": "细腻皮肤、均匀漫射柔光与干净小范围高光",
        "sharp_piercing": "小巧五官、轻微清晰轮廓与浅冷中性细节，不产生锐利感",
        "low_rich": "宽厚饱满脸型、自然软组织体积与低饱和中性柔光",
        "breathy_weak": "柔和边缘和低对比光，主体仍清晰且不失焦或病态化",
        "nasal": "自然略饱满软组织、柔和鼻翼光影与温润质感",
        "mumbled": "柔和面部边缘与明暗过渡，轮廓不锐利但五官仍可辨",
        "heavy_accent": "略宽厚脸型与柔和层次光影，无高对比暗角",
        "fine_soft": "小巧轻薄五官、较弱体积感与浅亮柔光，不幼态化或脆弱化",
    }[data.timbre]
    rate_text = {
        None: "未填写语速，不附加语速专属信号",
        1: "语速很慢，仅增加舒展低张力",
        2: "语速偏慢，仅增加轻微放松与低张力",
        3: "语速中等，面部肌肉松紧均衡",
        4: "语速偏快，仅增加轻微眉眼聚焦与自然闭唇",
        5: "语速很快，仅增加可辨识的轻度眉间聚焦与闭唇张力",
    }[data.speaking_rate_level]
    emotion_text = _resolve_emotion_text(
        list(data.emotions),
        is_child=data.age_sense == "child",
    )
    facial_expression = (
        f"{emotion_text}；{rate_text}；语速不得覆盖情绪方向；"
        "禁止瞪眼、露齿、咬牙、哭泣或面部扭曲"
    )

    power, malice, safety_rules = _effective_levels(data)
    gaze = {
        1: "视线松弛温和，保持自然交流感",
        2: "视线自然平缓，轻微收敛但不形成凝视",
        3: "正面自然平视，保留克制疏离感且非压迫",
        4: "可辨识的警觉但非威胁眼神，禁止压迫凝视",
        5: "克制警觉的自然眼神与平直闭唇，禁止凶狠凝视",
    }[malice]
    lighting = {
        1: "暖中性低饱和柔光，无明显面部阴影",
        2: "明亮微冷中性漫射光，仅保留极浅柔影",
        3: "明亮低饱和冷中性柔光，低对比且无硬阴影",
        4: "背景更明亮，使用低饱和冷中性细节并最小化阴影",
        5: "明亮低饱和中性画面，禁止冷暗光、阴影眼窝或强阴影",
    }[malice]
    raw_malice = data.malice_level if data.malice_level is not None else 3
    if data.age_sense == "child":
        lighting = "暖中性柔光，面部阴影极浅，保持温和低刺激"
    elif data.age_sense == "elderly" and raw_malice >= 4:
        lighting = (
            "明亮低饱和冷中性柔光，保留轻微警觉信号；"
            "禁止冷暗光、尖锐骨相或威胁性表情"
        )
    elif data.age_sense == "elderly":
        lighting = "暖中性柔光，面部阴影极浅，保持温和低刺激"
    composition = {
        1: "人物居中且占画面约 45%，正面胸像，观察距离舒适",
        2: "人物居中且占画面约 55%，正面或不超过十五度轻微侧脸",
        3: "人物居中且占画面约 65%，眼平、正面或不超过十五度侧脸",
        4: "人物居中且占画面约 72%，保持眼平和柔和空间感",
        5: "人物居中且占画面约 78%，饱满但禁止近距离压迫构图",
    }[power]
    background = (
        "医疗纸白纯色背景，明亮温和，无图案、文字或叙事场景"
        if data.age_sense in {"child", "elderly"} or malice <= 2
        else "浅暖灰纯色背景，低饱和、干净且非压迫"
    )

    features = EffectiveVisualFeatures(
        gender_expression=gender,
        age_expression=age,
        face_shape=face_shape,
        skin_texture=skin_texture,
        facial_expression=facial_expression,
        gaze=gaze,
        lighting=lighting,
        composition=composition,
        background=background,
    )
    return MappingResult(
        features=features,
        explanation={
            "mapping_version": MAPPING_VERSION,
            "effective_power_level": power,
            "effective_malice_level": malice,
            "safety_rules_applied": safety_rules,
            "initial_risk_classification_performed": False,
        },
    )
