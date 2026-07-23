from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.config.settings import get_settings
from app.database import get_session_factory
from app.models import (
    AdjustmentRequest,
    AvatarVersion,
    ClinicalCase,
    PatientSession,
    RiskRule,
    SessionAvatarAuthorization,
    SoundDescription,
    VisualFeature,
)
from app.services.bootstrap import initialize_local_database


async def main() -> None:
    settings = get_settings()
    if not settings.bootstrap_example_data:
        raise SystemExit("BOOTSTRAP_EXAMPLE_DATA must be enabled for this local utility")
    await initialize_local_database(settings)
    async with get_session_factory(settings.database_url)() as session:
        counts = {
            "cases": await session.scalar(select(func.count(ClinicalCase.case_id))),
            "sessions": await session.scalar(select(func.count(PatientSession.session_id))),
            "sound_descriptions": await session.scalar(
                select(func.count(SoundDescription.sound_description_id))
            ),
            "visual_features": await session.scalar(
                select(func.count(VisualFeature.visual_feature_id))
            ),
            "avatar_versions": await session.scalar(select(func.count(AvatarVersion.version_id))),
            "avatar_authorizations": await session.scalar(
                select(func.count(SessionAvatarAuthorization.authorization_id))
            ),
            "risk_rules": await session.scalar(select(func.count(RiskRule.rule_id))),
            "adjustment_requests": await session.scalar(
                select(func.count(AdjustmentRequest.request_id))
            ),
        }
        examples = (
            await session.scalars(
                select(ClinicalCase.study_code)
                .where(ClinicalCase.study_code.like("DEMO-%"))
                .order_by(ClinicalCase.study_code)
            )
        ).all()
    print("Example data ready")
    for key, value in counts.items():
        print(f"{key}: {value}")
    print(f"example_cases: {', '.join(examples)}")


if __name__ == "__main__":
    asyncio.run(main())
