from __future__ import annotations

import pytest

from app.api.errors import ApiError
from app.config.settings import Settings
from app.security.rate_limit import (
    RateLimitPolicy,
    anonymized_rate_limit_key,
    enforce_rate_limit,
    reset_memory_rate_limits,
)


@pytest.mark.asyncio
async def test_rate_limit_uses_anonymous_key_and_returns_retry_after() -> None:
    settings = Settings(
        app_env="test",
        redis_url="redis://127.0.0.1:1/0",
        secret_key="rate-limit-test-secret",
        _env_file=None,
    )
    policy = RateLimitPolicy("test-public-entry", 2, 60)
    subject = "127.0.0.1:doctor@example.org"
    key = anonymized_rate_limit_key(settings, policy, subject)
    assert subject not in key
    assert "doctor@example.org" not in key

    reset_memory_rate_limits()
    await enforce_rate_limit(settings, policy, subject)
    await enforce_rate_limit(settings, policy, subject)
    with pytest.raises(ApiError) as raised:
        await enforce_rate_limit(settings, policy, subject)

    assert raised.value.status_code == 429
    assert raised.value.code == "RATE_LIMITED"
    assert int(raised.value.headers["Retry-After"]) >= 1
