from __future__ import annotations

from dataclasses import dataclass

from app.adapters.feature_mapping.prompt_builder import EffectiveVisualFeatures, VoiceFeatures

MAPPING_VERSION = "deterministic-voice-appearance-v1.0"

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
    elif data.age_sense == "elderly" and malice > 2:
        malice = 2
        applied.append("老年安全约束：恶意感最高二档")
    if power >= 4 and malice >= 4:
        power = 3
        malice = 3
        applied.append("高强大感与高恶意感联动：两者降至三档")
    return power, malice, applied


def map_voice_to_visual(data: VoiceFeatures) -> MappingResult:
    gender = {
        "male": "男性基础面部表达，下颌与眉骨仅保留自然结构感",
        "female": "女性基础面部表达，眉眼曲线与下颌保持自然柔和",
        "uncertain_mixed": "中性自然表达，不强化男性或女性骨骼特征",
    }[data.voice_gender]
    age = {
        "child": "温和幼态比例，五官集中且圆润，不呈现威胁感",
        "adolescent": "青少年自然比例，轮廓清晰度适中且无明显细纹",
        "young": "青年成年人均衡比例，皮肤平整且立体感适中",
        "middle_aged": "中年轻度年龄特征，仅保留自然细纹且不夸大衰老",
        "elderly": "老年自然年龄特征，皱纹与松弛保持柔和克制",
        "uncertain": "青年至中年之间的中性年龄表达，不强化幼态或老化",
    }[data.age_sense]
    face_shape = {
        1: "脸型宽厚圆润，下颌方正但边缘柔和，五官舒展",
        2: "脸型略宽厚，五官比例自然，轮廓保持低锋利度",
        3: "标准均衡脸型，正常五官比例，轮廓圆润自然",
        4: "脸型略纤细，五官小巧，禁止尖脸或夸张比例",
        5: "脸型纤细狭长但比例自然，轮廓进一步柔化",
    }[data.pitch_level]
    skin_texture = {
        None: "皮肤纹理自然细腻，柔和高光且无厚重阴影",
        "hoarse_rough": "皮肤纹理略厚且呈柔和哑光，减少锐利高光",
        "clear_transparent": "皮肤纹理细腻通透，使用均匀漫射柔光",
        "sharp_piercing": "皮肤细节轻柔清晰，使用浅亮低饱和质感",
        "low_rich": "软组织自然饱满，皮肤质感温和且低饱和",
        "breathy_weak": "皮肤细节轻柔虚化，保持低对比度",
        "nasal": "皮肤质感温润自然，鼻翼光影保持柔和",
        "mumbled": "面部边缘与皮肤光影平滑过渡，避免清晰硬边",
        "heavy_accent": "皮肤与软组织层次柔和，禁止高对比暗角",
        "fine_soft": "皮肤质感细腻轻薄，立体感保持克制",
    }[data.timbre]

    emotion_labels = {
        "anger": "眉头极轻微收拢",
        "indifference": "面部平缓放松",
        "sarcasm": "单侧嘴角极细微上扬",
        "sadness": "眉眼轻微柔和下垂",
        "fear": "眉眼轻微抬起",
        "commanding": "端正温和平视",
    }
    emotion_text = "、".join(emotion_labels[item] for item in data.emotions)
    if len(data.emotions) > 1:
        emotion_text = f"多种情绪柔和中和，仅保留：{emotion_text}"
    rate_text = {
        None: "不附加语速专属神态",
        1: "面部肌肉充分放松",
        2: "面部轻微放松且无紧绷感",
        3: "面部肌肉松紧均衡",
        4: "眉眼轻微收拢但保持自然",
        5: "只保留极轻微紧绷并降低对比度",
    }[data.speaking_rate_level]
    facial_expression = f"{emotion_text}；{rate_text}；禁止瞪眼、露齿或扭曲"

    power, malice, safety_rules = _effective_levels(data)
    gaze = {
        1: "视线松弛温和，保持自然交流感",
        2: "视线自然平缓，轻微收敛但不形成凝视",
        3: "正面自然平视，眼神清晰且非压迫",
        4: "眼神保持克制，并进一步弱化负面神态",
        5: "眼神保持圆润温和，禁止凶狠或压迫凝视",
    }[malice]
    lighting = {
        1: "暖中性柔光，无明显面部阴影",
        2: "暖中性漫射光，仅保留极浅柔影",
        3: "浅亮中性柔光，低对比且无硬阴影",
        4: "浅冷中性柔光，主动提亮背景并弱化轮廓",
        5: "极浅微冷柔光，阴影限制为单层且非常轻",
    }[malice]
    if data.age_sense in {"child", "elderly"}:
        lighting = "暖中性柔光，面部阴影极浅，保持温和低刺激"
    composition = {
        1: "人物居中且占画面约四成，正面头像，观察距离舒适",
        2: "人物居中且占画面约五成，正面或轻微侧脸",
        3: "人物居中且占画面约六成，正面或不超过十五度侧脸",
        4: "人物居中且占画面约七成，保持柔和空间感",
        5: "人物居中且占画面约八成，禁止近距离压迫构图",
    }[power]
    background = (
        "暖浅米色纯色背景，无图案、文字或叙事场景"
        if data.age_sense in {"child", "elderly"} or malice <= 2
        else "浅灰绿色纯色背景，低饱和、干净且非压迫"
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
