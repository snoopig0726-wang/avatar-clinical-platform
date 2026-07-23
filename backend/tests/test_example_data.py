import pytest
from sqlalchemy import func, select

from app.config.settings import Settings
from app.database import get_engine, get_session_factory
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


@pytest.mark.asyncio
async def test_example_dataset_is_idempotent_and_covers_key_states(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'examples.db'}"
    settings = Settings(
        database_url=database_url,
        secret_key="example-test-secret",
        bootstrap_demo_data=True,
        bootstrap_example_data=True,
    )
    await initialize_local_database(settings)
    await initialize_local_database(settings)

    async with get_session_factory(database_url)() as session:
        assert await session.scalar(select(func.count(ClinicalCase.case_id))) == 3
        assert await session.scalar(select(func.count(PatientSession.session_id))) == 2
        assert await session.scalar(select(func.count(SoundDescription.sound_description_id))) == 1
        assert await session.scalar(select(func.count(VisualFeature.visual_feature_id))) == 1
        assert await session.scalar(select(func.count(AvatarVersion.version_id))) == 1
        assert (
            await session.scalar(select(func.count(SessionAvatarAuthorization.authorization_id)))
            == 1
        )
        assert await session.scalar(select(func.count(RiskRule.rule_id))) == 9
        assert await session.scalar(select(func.count(AdjustmentRequest.request_id))) == 1
        codes = set((await session.scalars(select(ClinicalCase.study_code))).all())
        assert codes == {"DEMO-VOICE-001", "DEMO-VOICE-002", "DEMO-VOICE-003"}

    await get_engine(database_url).dispose()
