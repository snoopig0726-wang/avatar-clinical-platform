from __future__ import annotations

import pytest

from app.adapters.image_generation.providers import (
    GeneratedImage,
    ImageGenerationError,
    MockImageGenerationProvider,
)
from app.services.avatar_generation import generate_with_image_safety_retry


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
    generated, safety = await generate_with_image_safety_retry(provider, "portrait")
    assert provider.calls == 2
    assert generated.content == safe.content
    assert safety.allowed is True


@pytest.mark.asyncio
async def test_image_safety_fails_closed_after_second_rejection() -> None:
    invalid = GeneratedImage(content=b"not-a-png", mime_type="image/png")
    provider = SequenceProvider([invalid, invalid])
    with pytest.raises(ImageGenerationError) as raised:
        await generate_with_image_safety_retry(provider, "portrait")
    assert provider.calls == 2
    assert raised.value.code == "INVALID_IMAGE_SIZE"
