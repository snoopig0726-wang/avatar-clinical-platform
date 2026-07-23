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
    "降低面部阴影与画面对比度，使用柔和漫射光",
    "放松眼神与眉眼紧绷感，避免压迫性凝视",
    "保持浅色纯色背景，进一步降低视觉刺激",
    "轻微调整人物占比，保持舒适观察距离和居中构图",
]


def build_controlled_instruction(raw_instruction: str) -> str:
    keyword_groups = (
        (("平静", "放松", "表情", "紧张"), CONTROLLED_ADJUSTMENT_OPTIONS[0]),
        (("阴影", "亮", "光", "对比"), CONTROLLED_ADJUSTMENT_OPTIONS[1]),
        (("眼神", "视线", "眉眼"), CONTROLLED_ADJUSTMENT_OPTIONS[2]),
        (("背景",), CONTROLLED_ADJUSTMENT_OPTIONS[3]),
        (("远", "近", "大小", "占比", "构图"), CONTROLLED_ADJUSTMENT_OPTIONS[4]),
    )
    for keywords, controlled in keyword_groups:
        if any(keyword in raw_instruction for keyword in keywords):
            return controlled
    return CONTROLLED_ADJUSTMENT_OPTIONS[0]


async def adjustment_usage(session: AsyncSession, case_id: UUID) -> AdjustmentUsage:
    used = await session.scalar(
        select(func.count(AdjustmentRequest.request_id)).where(
            AdjustmentRequest.case_id == case_id,
            AdjustmentRequest.risk_status == "passed",
        )
    )
    pending = await session.scalar(
        select(func.count(AdjustmentRequest.request_id)).where(
            AdjustmentRequest.case_id == case_id,
            AdjustmentRequest.doctor_status.in_(PENDING_ADJUSTMENT_STATUSES),
        )
    )
    return AdjustmentUsage(used=used or 0, limit=ADJUSTMENT_LIMIT, has_pending=bool(pending))
