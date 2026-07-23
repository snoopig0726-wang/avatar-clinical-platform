from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.adapters.image_generation.providers import (
    GeneratedImage,
    ImageGenerationError,
    MockImageGenerationProvider,
)
from app.adapters.image_generation.semantic_safety import (
    MockSemanticImageSafetyProvider,
    OpenAISemanticImageSafetyProvider,
)
from app.config.settings import Settings
from app.services.avatar_generation import (
    ImageGenerationSafetyError,
    generate_with_image_safety_retry,
)


class SequenceProvider:
    def __init__(self, outputs: list[GeneratedImage]) -> None:
        self.outputs = outputs
        self.calls = 0

    def generate(self, prompt: str) -> GeneratedImage:
        del prompt
        output = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        return output


@pytest.mark.asyncio
async def test_image_safety_retries_once_then_accepts_safe_output() -> None:
    safe = MockImageGenerationProvider().generate("safe")
    provider = SequenceProvider(
        [
            GeneratedImage(content=b"not-a-png", mime_type="image/png"),
            safe,
        ]
    )
    generated, safety, semantic_safety = await generate_with_image_safety_retry(
        provider,
        "portrait",
        MockSemanticImageSafetyProvider(),
    )
    assert provider.calls == 2
    assert generated.content == safe.content
    assert safety.allowed is True
    assert semantic_safety.allowed is True


@pytest.mark.asyncio
async def test_image_safety_fails_closed_after_second_rejection() -> None:
    invalid = GeneratedImage(content=b"not-a-png", mime_type="image/png")
    provider = SequenceProvider([invalid, invalid])
    with pytest.raises(ImageGenerationError) as raised:
        await generate_with_image_safety_retry(
            provider,
            "portrait",
            MockSemanticImageSafetyProvider(),
        )
    assert provider.calls == 2
    assert raised.value.code == "INVALID_IMAGE_SIZE"


@pytest.mark.parametrize(
    ("scenario", "code", "retryable"),
    [
        ("temporary_failure", "PROVIDER_TEMPORARY_FAILURE", True),
        ("moderation_blocked", "PROVIDER_MODERATION_BLOCKED", False),
    ],
)
def test_mock_provider_can_demonstrate_provider_failures(
    scenario: str, code: str, retryable: bool
) -> None:
    provider = MockImageGenerationProvider(
        Settings(mock_image_scenario=scenario)
    )
    with pytest.raises(ImageGenerationError) as raised:
        provider.generate("portrait")
    assert raised.value.code == code
    assert raised.value.retryable is retryable


@pytest.mark.asyncio
async def test_mock_invalid_image_scenario_fails_closed_after_retry() -> None:
    provider = MockImageGenerationProvider(
        Settings(mock_image_scenario="invalid_image")
    )
    with pytest.raises(ImageGenerationError) as raised:
        await generate_with_image_safety_retry(
            provider,
            "portrait",
            MockSemanticImageSafetyProvider(),
        )
    assert raised.value.code == "INVALID_IMAGE_SIZE"


@pytest.mark.asyncio
async def test_semantic_image_safety_retries_once_then_fails_closed() -> None:
    provider = SequenceProvider(
        [
            MockImageGenerationProvider().generate("first"),
            MockImageGenerationProvider().generate("second"),
        ]
    )
    semantic = MockSemanticImageSafetyProvider(
        Settings(mock_semantic_safety_scenario="blocked")
    )
    with pytest.raises(ImageGenerationError) as raised:
        await generate_with_image_safety_retry(provider, "portrait", semantic)
    assert provider.calls == 2
    assert raised.value.code == "SEMANTIC_MODERATION_BLOCKED"
    assert isinstance(raised.value, ImageGenerationSafetyError)
    assert raised.value.semantic_result is not None
    assert raised.value.semantic_result.flagged_categories == ("violence/graphic",)


@pytest.mark.asyncio
async def test_semantic_image_safety_unavailable_is_retryable_and_fail_closed() -> None:
    provider = SequenceProvider([MockImageGenerationProvider().generate("safe")])
    semantic = MockSemanticImageSafetyProvider(
        Settings(mock_semantic_safety_scenario="unavailable")
    )
    with pytest.raises(ImageGenerationError) as raised:
        await generate_with_image_safety_retry(provider, "portrait", semantic)
    assert provider.calls == 1
    assert raised.value.code == "SEMANTIC_SAFETY_SERVICE_UNAVAILABLE"
    assert raised.value.retryable is True


def test_openai_semantic_image_safety_sends_base64_image_and_maps_categories() -> None:
    captured: dict[str, object] = {}

    class Categories:
        def model_dump(self, *, by_alias: bool) -> dict[str, bool]:
            assert by_alias is True
            return {"violence": True, "violence/graphic": False, "sexual": False}

    class Moderations:
        def create(self, **payload: object) -> SimpleNamespace:
            captured.update(payload)
            return SimpleNamespace(
                id="modr-test",
                model="omni-moderation-latest",
                results=[
                    SimpleNamespace(
                        flagged=True,
                        categories=Categories(),
                    )
                ],
            )

    provider = object.__new__(OpenAISemanticImageSafetyProvider)
    provider.model = "omni-moderation-latest"
    provider.client = SimpleNamespace(moderations=Moderations())
    generated = MockImageGenerationProvider().generate("safe")

    result = provider.inspect(generated.content, generated.mime_type)

    assert result.allowed is False
    assert result.code == "SEMANTIC_MODERATION_BLOCKED"
    assert result.flagged_categories == ("violence",)
    assert captured["model"] == "omni-moderation-latest"
    image_input = captured["input"]
    assert isinstance(image_input, list)
    assert image_input[0]["type"] == "image_url"
    assert image_input[0]["image_url"]["url"].startswith("data:image/png;base64,")
