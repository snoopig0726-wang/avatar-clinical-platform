from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config.settings import Settings


def test_production_rejects_local_defaults() -> None:
    with pytest.raises(ValidationError) as raised:
        Settings(app_env="production", _env_file=None)
    message = str(raised.value)
    assert "unsafe production configuration" in message
    assert "SECRET_KEY" in message
    assert "BOOTSTRAP_DEMO_DATA" in message
    assert "MODEL_PROVIDER" in message


def test_production_accepts_explicit_secure_boundaries() -> None:
    settings = Settings(
        app_env="production",
        secret_key="production-secret-with-at-least-thirty-two-characters",
        database_url="postgresql+asyncpg://avatar:secret@postgres/avatar",
        redis_url="rediss://redis.internal:6379/0",
        frontend_origins="https://avatar.example.org",
        expose_api_docs=False,
        auto_create_tables=False,
        bootstrap_demo_data=False,
        bootstrap_example_data=False,
        storage_provider="s3",
        s3_endpoint="https://s3.internal.example.org",
        s3_public_endpoint="https://images.example.org",
        s3_access_key="production-access",
        s3_secret_key="production-storage-secret",
        model_provider="openai",
        model_api_key="configured-through-secret-manager",
        semantic_image_safety_provider="openai",
        semantic_image_safety_api_key="configured-through-secret-manager",
        _env_file=None,
    )
    assert settings.app_env == "production"
