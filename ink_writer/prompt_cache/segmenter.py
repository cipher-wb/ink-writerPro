"""Prompt segmenter: splits system prompt into cacheable blocks.

Anthropic's prompt cache requires stable content to appear first in the
system prompt, tagged with cache_control: {"type": "ephemeral"}.
This module segments prompts into stable vs volatile blocks and
produces the system parameter format the SDK expects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ink_writer.prompt_cache.config import PromptCacheConfig


class SegmentType(Enum):
    STABLE = "stable"
    VOLATILE = "volatile"


@dataclass
class CacheableMessage:
    """A system prompt block ready for the Anthropic SDK."""
    text: str
    segment_type: SegmentType
    label: str = ""

    def to_sdk_block(self) -> dict[str, Any]:
        block: dict[str, Any] = {"type": "text", "text": self.text}
        if self.segment_type == SegmentType.STABLE:
            block["cache_control"] = {"type": "ephemeral"}
        return block


def segment_system_prompt(
    system_text: str,
    config: PromptCacheConfig | None = None,
    *,
    stable_prefix: str = "",
    volatile_suffix: str = "",
) -> list[CacheableMessage]:
    """Segment a system prompt into cacheable blocks.

    Strategy:
    1. stable_prefix (if provided) → STABLE block with cache_control
    2. system_text → STABLE block with cache_control (base system prompt is stable across calls)
    3. volatile_suffix (if provided) → VOLATILE block (no cache_control)

    Returns list of CacheableMessage ready for SDK consumption.
    """
    if config is None:
        config = PromptCacheConfig()

    segments: list[CacheableMessage] = []

    if stable_prefix:
        segments.append(CacheableMessage(
            text=stable_prefix,
            segment_type=SegmentType.STABLE,
            label="stable_prefix",
        ))

    if system_text:
        segments.append(CacheableMessage(
            text=system_text,
            segment_type=SegmentType.STABLE,
            label="system_prompt",
        ))

    if volatile_suffix:
        segments.append(CacheableMessage(
            text=volatile_suffix,
            segment_type=SegmentType.VOLATILE,
            label="volatile_suffix",
        ))

    return segments


def build_cached_system_param(
    segments: list[CacheableMessage],
) -> list[dict[str, Any]] | str:
    """Convert segments to the Anthropic SDK system parameter format.

    If all segments are simple text without cache_control, returns a plain string.
    Otherwise returns a list of content blocks.
    """
    if not segments:
        return ""

    has_cache = any(s.segment_type == SegmentType.STABLE for s in segments)
    if not has_cache:
        return "\n\n".join(s.text for s in segments)

    return [s.to_sdk_block() for s in segments]


def estimate_tokens(text: str) -> int:
    """Rough token estimate for Chinese+English mixed text.

    Chinese characters ≈ 1.5 tokens each, English words ≈ 1.3 tokens each.
    This is a conservative estimate for cache eligibility checks.
    """
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5 + other_chars * 0.4)
