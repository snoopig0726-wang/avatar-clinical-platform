"""Compatibility reference for the current voice-to-appearance Prompt builder.

The executable source of truth lives in:

    backend/app/adapters/feature_mapping/prompt_builder.py
    backend/app/adapters/feature_mapping/deterministic_mapper.py

This documentation-side module deliberately re-exports the runtime contracts
instead of keeping a second, divergent implementation. In particular:

- Q1-Q8 accepts one to six controlled emotions.
- Q1-Q8 does not require a ``risk_level`` field.
- free-text adjustment risk screening is handled separately by RISK-V1.3.
- Prompt construction requires doctor-confirmed effective visual features.

Do not import this documentation path from production code.
"""

from app.adapters.feature_mapping.deterministic_mapper import (  # noqa: F401
    CONTROLLED_VISUAL_OPTIONS,
    MAPPING_VERSION,
    MappingResult,
    map_voice_to_visual,
)
from app.adapters.feature_mapping.prompt_builder import (  # noqa: F401
    PROMPT_TEMPLATE_VERSION,
    SYSTEM_PROMPT,
    AgeSense,
    ConfirmedGenerationInput,
    EffectiveVisualFeatures,
    Emotion,
    Timbre,
    VoiceFeatures,
    VoiceGender,
    build_prompt_messages,
)

__all__ = [
    "AgeSense",
    "CONTROLLED_VISUAL_OPTIONS",
    "ConfirmedGenerationInput",
    "EffectiveVisualFeatures",
    "Emotion",
    "MAPPING_VERSION",
    "MappingResult",
    "PROMPT_TEMPLATE_VERSION",
    "SYSTEM_PROMPT",
    "Timbre",
    "VoiceFeatures",
    "VoiceGender",
    "build_prompt_messages",
    "map_voice_to_visual",
]
