from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AdjustmentStatus
from app.models.entities import AdjustmentRequest
from app.schemas.sessions import AdjustmentUsage

ADJUSTMENT_LIMIT = 3
PENDING_ADJUSTMENT_STATUSES = {
    AdjustmentStatus.PENDING_DOCTOR_REVIEW,
    AdjustmentStatus.APPROVED_AS_IS,
    AdjustmentStatus.APPROVED_EDITED,
    AdjustmentStatus.GENERATING,
}

CONTROLLED_ADJUSTMENT_OPTIONS = [
    "进一步柔化面部表情，保持平静、自然和轻微放松",
    "适度增加人物年龄感，通过面部轮廓、发色与自然年龄特征呈现更年长的外观",
    "适度降低人物年龄感，通过面部轮廓与自然年龄特征呈现更年轻的外观",
    "适度增强令人不安的表情与氛围，同时避免血腥、伤害或极端恐怖元素",
    "适度减弱令人不安的表情与氛围，使画面更温和并保持人物主要特征",
    "降低面部阴影与画面对比度，使用柔和漫射光",
    "适度增强面部阴影与画面对比度，同时保持五官清晰并避免极端视觉刺激",
    "放松眼神与眉眼紧绷感，避免压迫性凝视",
    "保持浅色纯色背景，进一步降低视觉刺激",
    "轻微调整人物占比，保持舒适观察距离和居中构图",
    "根据患者描述调整性别呈现与面部性别特征，不作身份推断并保持自然外观",
    "根据患者明确描述调整肤色、面部结构与文化外观线索，避免刻板化",
    "根据患者描述调整脸型、下颌、颧骨、鼻、嘴或耳等面部结构，保持自然比例",
    "根据患者描述调整皮肤色调与纹理，如苍白、红润、光滑、粗糙、皱纹或雀斑",
    "根据患者描述调整发色、长短、卷直、发型、发际线或面部毛发",
    "根据患者描述调整眼睛颜色、大小、形状、眉形与凝视方向",
    "适度增强愤怒、严厉、冷漠或嘲讽等表情特征，避免极端威胁性呈现",
    "适度减弱愤怒、严厉、冷漠或嘲讽等表情特征，保持人物主要特征",
    "根据患者描述调整悲伤、疲惫、痛苦或哭泣等情绪表情，保持非伤害性呈现",
    "根据患者描述增强微笑、友善、亲切或温柔等表情特征",
    "适度增强权威、强势、支配或压迫感，通过姿态、视线和构图表达，避免暴力暗示",
    "适度减弱权威、支配或压迫感，使角色显得更弱势、平等或可接近",
    "根据患者描述调整非人类、超现实或象征性外观，同时避免血腥、伤害或极端恐怖元素",
    "根据患者描述调整写实度与视觉风格，如写实、插画、剪影或模糊轮廓",
    "根据患者描述调整服装、饰品、面具、眼镜与整体造型，不改变未提及的核心特征",
    "根据患者描述调整背景场景、色彩与氛围，同时保持主体清晰可辨",
]


def build_controlled_options(raw_instruction: str) -> list[str]:
    raw = raw_instruction.strip()
    matched: list[str] = []

    directional_groups = (
        (("更老", "再老", "老一点", "年长", "年龄大"), CONTROLLED_ADJUSTMENT_OPTIONS[1]),
        (("更年轻", "年轻一点", "年龄小"), CONTROLLED_ADJUSTMENT_OPTIONS[2]),
        (
            (
                "更可怕",
                "再可怕",
                "可怕一点",
                "更恐怖",
                "再恐怖",
                "恐怖一点",
                "更吓人",
                "更凶",
                "更阴森",
            ),
            CONTROLLED_ADJUSTMENT_OPTIONS[3],
        ),
        (
            ("不那么可怕", "没那么可怕", "不要可怕", "不吓人", "减少恐怖", "温和一点"),
            CONTROLLED_ADJUSTMENT_OPTIONS[4],
        ),
        (("更平静", "再平静", "更放松", "柔和一点", "减少紧张"), CONTROLLED_ADJUSTMENT_OPTIONS[0]),
        (("减少阴影", "阴影少", "更亮", "亮一点", "降低对比"), CONTROLLED_ADJUSTMENT_OPTIONS[5]),
        (("增加阴影", "阴影多", "更暗", "暗一点", "提高对比"), CONTROLLED_ADJUSTMENT_OPTIONS[6]),
        (("放松眼神", "眼神柔和", "眉眼放松"), CONTROLLED_ADJUSTMENT_OPTIONS[7]),
        (("浅色背景", "纯色背景", "背景简单", "背景柔和"), CONTROLLED_ADJUSTMENT_OPTIONS[8]),
        (
            ("远一点", "近一点", "大一点", "小一点", "占比", "构图"),
            CONTROLLED_ADJUSTMENT_OPTIONS[9],
        ),
        (
            ("男性", "女性", "男人", "女人", "男性化", "女性化", "中性", "性别", "雌雄同体"),
            CONTROLLED_ADJUSTMENT_OPTIONS[10],
        ),
        (
            ("族裔", "人种", "民族", "东亚", "南亚", "亚洲", "非洲", "黑人", "白人", "欧洲"),
            CONTROLLED_ADJUSTMENT_OPTIONS[11],
        ),
        (
            (
                "脸型",
                "圆脸",
                "长脸",
                "方脸",
                "瘦脸",
                "胖脸",
                "下巴",
                "下颌",
                "颧骨",
                "鼻子",
                "嘴巴",
                "嘴唇",
                "耳朵",
            ),
            CONTROLLED_ADJUSTMENT_OPTIONS[12],
        ),
        (
            ("肤色", "皮肤", "苍白", "红润", "皱纹", "粗糙", "光滑", "雀斑", "痣", "疤痕"),
            CONTROLLED_ADJUSTMENT_OPTIONS[13],
        ),
        (
            (
                "头发",
                "发型",
                "发色",
                "白发",
                "黑发",
                "长发",
                "短发",
                "卷发",
                "直发",
                "秃",
                "胡子",
                "胡须",
                "发际线",
            ),
            CONTROLLED_ADJUSTMENT_OPTIONS[14],
        ),
        (
            (
                "眼睛",
                "眼珠",
                "瞳孔",
                "眼睛颜色",
                "眼睛大小",
                "眼睛形状",
                "眉毛",
                "眉形",
                "凝视",
                "视线",
            ),
            CONTROLLED_ADJUSTMENT_OPTIONS[15],
        ),
        (
            ("更愤怒", "更生气", "更凶", "更严厉", "更冷漠", "更嘲讽", "更蔑视", "更狰狞"),
            CONTROLLED_ADJUSTMENT_OPTIONS[16],
        ),
        (
            ("不生气", "少一点愤怒", "没那么凶", "不那么严厉", "不冷漠", "不要嘲讽"),
            CONTROLLED_ADJUSTMENT_OPTIONS[17],
        ),
        (
            ("悲伤", "难过", "哭泣", "流泪", "疲惫", "痛苦", "沮丧"),
            CONTROLLED_ADJUSTMENT_OPTIONS[18],
        ),
        (
            ("微笑", "开心", "友善", "亲切", "温柔", "和善"),
            CONTROLLED_ADJUSTMENT_OPTIONS[19],
        ),
        (
            (
                "更强大",
                "更强势",
                "更权威",
                "更有力量",
                "支配",
                "控制感",
                "压迫",
                "高高在上",
                "威严",
                "傲慢",
            ),
            CONTROLLED_ADJUSTMENT_OPTIONS[20],
        ),
        (
            ("弱小", "不强势", "不压迫", "少一点压迫", "更平等", "可接近", "亲近"),
            CONTROLLED_ADJUSTMENT_OPTIONS[21],
        ),
        (
            (
                "非人",
                "怪物",
                "恶魔",
                "鬼",
                "机器人",
                "动物",
                "无脸",
                "面具脸",
                "影子",
                "人影",
                "超自然",
                "象征",
            ),
            CONTROLLED_ADJUSTMENT_OPTIONS[22],
        ),
        (
            ("写实", "真实一点", "卡通", "插画", "剪影", "模糊轮廓", "抽象"),
            CONTROLLED_ADJUSTMENT_OPTIONS[23],
        ),
        (
            ("衣服", "服装", "帽子", "眼镜", "面具", "首饰", "饰品", "制服", "长袍"),
            CONTROLLED_ADJUSTMENT_OPTIONS[24],
        ),
        (
            ("背景", "场景", "室内", "室外", "房间", "街道", "颜色氛围"),
            CONTROLLED_ADJUSTMENT_OPTIONS[25],
        ),
    )
    for phrases, controlled in directional_groups:
        if any(phrase in raw for phrase in phrases) and controlled not in matched:
            matched.append(controlled)

    if not matched:
        safe_raw = raw[:120]
        matched.append(
            f"在非血腥、非伤害且避免极端视觉刺激的边界内，忠实按照患者提出的方向调整：{safe_raw}"
        )

    combined = "；".join(matched)
    if len(combined) > 200:
        safe_raw = raw[:120]
        combined = (
            "在非血腥、非伤害且避免极端视觉刺激的边界内，"
            f"忠实按照患者提出的多个方向调整：{safe_raw}"
        )
    if len(matched) > 1:
        return [combined, *matched]
    return matched


def build_controlled_instruction(raw_instruction: str) -> str:
    return build_controlled_options(raw_instruction)[0]


async def adjustment_usage(session: AsyncSession, session_id: UUID) -> AdjustmentUsage:
    used = await session.scalar(
        select(func.count(AdjustmentRequest.request_id)).where(
            AdjustmentRequest.session_id == session_id,
            AdjustmentRequest.risk_status == "passed",
        )
    )
    pending = await session.scalar(
        select(func.count(AdjustmentRequest.request_id)).where(
            AdjustmentRequest.session_id == session_id,
            AdjustmentRequest.doctor_status.in_(PENDING_ADJUSTMENT_STATUSES),
        )
    )
    return AdjustmentUsage(used=used or 0, limit=ADJUSTMENT_LIMIT, has_pending=bool(pending))
