from __future__ import annotations

import hashlib
import hmac
import threading
import time
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.api.errors import ApiError
from app.config.settings import Settings


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: int


LOGIN_POLICY = RateLimitPolicy("staff-login", 10, 300)
DOCTOR_APPLICATION_POLICY = RateLimitPolicy("doctor-application", 5, 3600)
EMAIL_VERIFICATION_POLICY = RateLimitPolicy("email-verification", 10, 600)
INVITE_REDEMPTION_POLICY = RateLimitPolicy("invite-redemption", 10, 600)
PATIENT_ADJUSTMENT_POLICY = RateLimitPolicy("patient-adjustment", 10, 300)

_LUA_INCREMENT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""

_memory_lock = threading.Lock()
_memory_windows: dict[str, tuple[int, float]] = {}


def anonymized_rate_limit_key(
    settings: Settings,
    policy: RateLimitPolicy,
    subject: str,
) -> str:
    digest = hmac.new(
        settings.secret_key.encode("utf-8"),
        subject.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"avatar:rate-limit:{policy.name}:{digest}"


def _memory_increment(key: str, window_seconds: int) -> tuple[int, int]:
    now = time.monotonic()
    with _memory_lock:
        count, expires_at = _memory_windows.get(key, (0, now + window_seconds))
        if expires_at <= now:
            count, expires_at = 0, now + window_seconds
        count += 1
        _memory_windows[key] = (count, expires_at)
    return count, max(1, int(expires_at - now))


def reset_memory_rate_limits() -> None:
    with _memory_lock:
        _memory_windows.clear()


async def enforce_rate_limit(
    settings: Settings,
    policy: RateLimitPolicy,
    subject: str,
) -> None:
    if not settings.rate_limit_enabled:
        return
    key = anonymized_rate_limit_key(settings, policy, subject)
    try:
        client = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        try:
            result = await client.eval(
                _LUA_INCREMENT,
                1,
                key,
                policy.window_seconds,
            )
            count, retry_after = int(result[0]), max(1, int(result[1]))
        finally:
            await client.aclose()
    except (RedisError, OSError):
        if settings.app_env.lower() in {"production", "prod"}:
            raise ApiError(
                503,
                "DEPENDENCY_UNAVAILABLE",
                "请求保护服务暂时不可用，请稍后重试",
            ) from None
        count, retry_after = _memory_increment(key, policy.window_seconds)

    if count > policy.limit:
        raise ApiError(
            429,
            "RATE_LIMITED",
            "请求过于频繁，请稍后重试",
            details={"retry_after_seconds": retry_after},
            headers={"Retry-After": str(retry_after)},
        )
