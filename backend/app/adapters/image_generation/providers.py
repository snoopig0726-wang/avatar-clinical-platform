from __future__ import annotations

import base64
import struct
import time
import zlib
from dataclasses import dataclass
from typing import Protocol

from app.config.settings import Settings


class ImageGenerationError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class GeneratedImage:
    content: bytes
    mime_type: str
    provider_request_id: str | None = None


class ImageGenerationProvider(Protocol):
    def generate(self, prompt: str) -> GeneratedImage: ...


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _mock_portrait_png() -> bytes:
    """Create a deterministic low-stimulus 1024px portrait without extra dependencies."""
    size = 1024
    rows: list[bytes] = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            color = (240, 244, 242)
            if ((x - 512) ** 2) / (210**2) + ((y - 420) ** 2) / (260**2) <= 1:
                color = (211, 179, 155)
            if y > 690 and ((x - 512) ** 2) / (360**2) + ((y - 980) ** 2) / (310**2) <= 1:
                color = (117, 145, 151)
            if 385 < y < 405 and ((x - 445) ** 2 < 22**2 or (x - 579) ** 2 < 22**2):
                color = (70, 78, 76)
            if 550 < y < 565 and 455 < x < 569:
                color = (151, 102, 94)
            row.extend(color)
        rows.append(bytes(row))
    raw = b"".join(rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + _png_chunk(b"IEND", b"")
    )


class MockImageGenerationProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self.scenario = settings.mock_image_scenario if settings else "success"
        self.delay_seconds = settings.mock_image_delay_seconds if settings else 0

    def generate(self, prompt: str) -> GeneratedImage:
        del prompt
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if self.scenario == "temporary_failure":
            raise ImageGenerationError("PROVIDER_TEMPORARY_FAILURE", retryable=True)
        if self.scenario == "moderation_blocked":
            raise ImageGenerationError("PROVIDER_MODERATION_BLOCKED")
        if self.scenario == "invalid_image":
            return GeneratedImage(
                content=b"mock-invalid-image",
                mime_type="image/png",
                provider_request_id="mock-invalid",
            )
        return GeneratedImage(
            content=_mock_portrait_png(),
            mime_type="image/png",
            provider_request_id="mock-local",
        )


class OpenAIImageGenerationProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.model_api_key:
            raise ImageGenerationError("MODEL_CREDENTIALS_MISSING")
        from openai import OpenAI

        self.model = settings.model_name
        self.client = OpenAI(
            api_key=settings.model_api_key,
            timeout=settings.model_timeout_seconds,
            max_retries=0,
        )

    def generate(self, prompt: str) -> GeneratedImage:
        try:
            response = self.client.images.generate(
                model=self.model,
                prompt=prompt,
                size="1024x1024",
                quality="medium",
                output_format="png",
                moderation="auto",
                n=1,
            )
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            error_code = getattr(exc, "code", None)
            if error_code == "moderation_blocked":
                raise ImageGenerationError("PROVIDER_MODERATION_BLOCKED") from exc
            if status == 429 or (isinstance(status, int) and status >= 500):
                raise ImageGenerationError("PROVIDER_TEMPORARY_FAILURE", retryable=True) from exc
            raise ImageGenerationError("PROVIDER_REQUEST_FAILED") from exc
        if not response.data or not response.data[0].b64_json:
            raise ImageGenerationError("PROVIDER_EMPTY_IMAGE")
        try:
            content = base64.b64decode(response.data[0].b64_json, validate=True)
        except ValueError as exc:
            raise ImageGenerationError("PROVIDER_INVALID_IMAGE_ENCODING") from exc
        return GeneratedImage(
            content=content,
            mime_type="image/png",
            provider_request_id=getattr(response, "id", None),
        )


def get_image_generation_provider(settings: Settings) -> ImageGenerationProvider:
    if settings.model_provider == "mock":
        return MockImageGenerationProvider(settings)
    if settings.model_provider == "openai":
        return OpenAIImageGenerationProvider(settings)
    raise ImageGenerationError("MODEL_PROVIDER_UNSUPPORTED")
