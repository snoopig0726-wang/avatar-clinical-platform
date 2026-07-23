from __future__ import annotations

import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class ImageSafetyResult:
    allowed: bool
    code: str
    width: int | None = None
    height: int | None = None


def inspect_generated_image(content: bytes, mime_type: str) -> ImageSafetyResult:
    """Fail closed on unexpected or malformed output before doctor review."""
    if mime_type != "image/png":
        return ImageSafetyResult(False, "UNSUPPORTED_IMAGE_TYPE")
    if len(content) < 24 or len(content) > 20 * 1024 * 1024:
        return ImageSafetyResult(False, "INVALID_IMAGE_SIZE")
    if content[:8] != b"\x89PNG\r\n\x1a\n" or content[12:16] != b"IHDR":
        return ImageSafetyResult(False, "INVALID_IMAGE_SIGNATURE")
    width, height = struct.unpack(">II", content[16:24])
    if (width, height) != (1024, 1024):
        return ImageSafetyResult(False, "INVALID_IMAGE_DIMENSIONS", width, height)
    return ImageSafetyResult(True, "PASSED", width, height)

