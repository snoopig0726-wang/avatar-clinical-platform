from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Protocol

from app.config.settings import Settings


class SemanticImageSafetyError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class SemanticImageSafetyResult:
    allowed: bool
    code: str
    provider: str
    model: str
    provider_request_id: str | None = None
    flagged_categories: tuple[str, ...] = ()


class SemanticImageSafetyProvider(Protocol):
    def inspect(self, content: bytes, mime_type: str) -> SemanticImageSafetyResult: ...


class MockSemanticImageSafetyProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self.scenario = settings.mock_semantic_safety_scenario if settings else "pass"

    def inspect(self, content: bytes, mime_type: str) -> SemanticImageSafetyResult:
        del content, mime_type
        if self.scenario == "unavailable":
            raise SemanticImageSafetyError(
                "SEMANTIC_SAFETY_SERVICE_UNAVAILABLE",
                retryable=True,
            )
        if self.scenario == "blocked":
            return SemanticImageSafetyResult(
                allowed=False,
                code="SEMANTIC_MODERATION_BLOCKED",
                provider="mock",
                model="mock-semantic-safety-v1",
                provider_request_id="mock-safety-blocked",
                flagged_categories=("violence/graphic",),
            )
        return SemanticImageSafetyResult(
            allowed=True,
            code="SEMANTIC_SAFETY_PASSED",
            provider="mock",
            model="mock-semantic-safety-v1",
            provider_request_id="mock-safety-passed",
        )


class OpenAISemanticImageSafetyProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.semantic_image_safety_api_key:
            raise SemanticImageSafetyError("SEMANTIC_SAFETY_CREDENTIALS_MISSING")
        from openai import OpenAI

        self.model = settings.semantic_image_safety_model
        self.client = OpenAI(
            api_key=settings.semantic_image_safety_api_key,
            timeout=settings.semantic_image_safety_timeout_seconds,
            max_retries=0,
        )

    def inspect(self, content: bytes, mime_type: str) -> SemanticImageSafetyResult:
        data_url = (
            f"data:{mime_type};base64,"
            f"{base64.b64encode(content).decode('ascii')}"
        )
        try:
            response = self.client.moderations.create(
                model=self.model,
                input=[
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    }
                ],
            )
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status == 429 or (isinstance(status, int) and status >= 500):
                raise SemanticImageSafetyError(
                    "SEMANTIC_SAFETY_SERVICE_UNAVAILABLE",
                    retryable=True,
                ) from exc
            raise SemanticImageSafetyError("SEMANTIC_SAFETY_REQUEST_FAILED") from exc
        if not response.results:
            raise SemanticImageSafetyError("SEMANTIC_SAFETY_EMPTY_RESULT")

        result = response.results[0]
        category_values = result.categories.model_dump(by_alias=True)
        flagged_categories = tuple(
            sorted(name for name, flagged in category_values.items() if flagged)
        )
        return SemanticImageSafetyResult(
            allowed=not result.flagged,
            code=(
                "SEMANTIC_MODERATION_BLOCKED"
                if result.flagged
                else "SEMANTIC_SAFETY_PASSED"
            ),
            provider="openai",
            model=getattr(response, "model", self.model),
            provider_request_id=getattr(response, "id", None),
            flagged_categories=flagged_categories,
        )


def get_semantic_image_safety_provider(
    settings: Settings,
) -> SemanticImageSafetyProvider:
    if settings.semantic_image_safety_provider == "mock":
        return MockSemanticImageSafetyProvider(settings)
    if settings.semantic_image_safety_provider == "openai":
        return OpenAISemanticImageSafetyProvider(settings)
    raise SemanticImageSafetyError("SEMANTIC_SAFETY_PROVIDER_UNSUPPORTED")
