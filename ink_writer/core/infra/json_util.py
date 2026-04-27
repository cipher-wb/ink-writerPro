"""Shared JSON parse utility for LLM checker output (US-007).

Provides 3-level resilient JSON parsing for LLM responses that may contain:
- Bare JSON
- Markdown-fenced JSON blocks (```json ... ```)
- JSON with surrounding prose / prefixes / suffixes

Raises :class:`CheckerJSONParseError` with the first 200 characters of the
original input on total parse failure.
"""
from __future__ import annotations

import json
import re
from typing import Any


class CheckerJSONParseError(ValueError):
    """Raised when all 3 levels of JSON parsing fail.

    The error message includes the first 200 characters of the original
    LLM output for debugging.
    """

    def __init__(self, raw: str, detail: str = "") -> None:
        snippet = raw[:200] if raw else "(empty)"
        msg = f"CheckerJSONParseError: {detail} — raw[:200] = {snippet!r}"
        super().__init__(msg)
        self.raw = raw
        self.detail = detail


def parse_llm_json(raw: str) -> Any:
    """Parse LLM output with 3-level fallback resilience.

    Level 1: Direct ``json.loads()`` on the trimmed raw string.
    Level 2: Regex extract the first ``{...}`` or ``[...]`` and parse.
    Level 3: Strip markdown fences (`` ```json ... ``` ``), then retry
             Level 2 extraction.

    Args:
        raw: Raw LLM response string.

    Returns:
        Parsed JSON value (typically ``list[dict]`` or ``dict``).

    Raises:
        CheckerJSONParseError: When all 3 levels fail.
    """
    if not isinstance(raw, str):
        raise CheckerJSONParseError(str(raw), "llm response is not a string")

    text = raw.strip()
    if not text:
        raise CheckerJSONParseError(raw, "llm response is empty")

    errors: list[str] = []

    # ── Level 1: direct parse ──────────────────────────────────────
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(f"L1: {exc}")

    # ── Level 2: regex extract first JSON block ────────────────────
    for pattern in [r"\[.*\]", r"\{.*\}"]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError as exc:
                errors.append(f"L2({pattern[:6]}): {exc}")

    # ── Level 3: strip markdown fence, retry Level 2 ────────────────
    fence = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        inner = fence.group(1)
        try:
            return json.loads(inner)
        except json.JSONDecodeError as exc:
            errors.append(f"L3(fence): {exc}")

    # Also try stripping fence markers manually and retrying
    stripped = re.sub(r"^```(?:json)?\s*", "", text)
    stripped = re.sub(r"\s*```\s*$", "", stripped)
    if stripped != text:
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            errors.append(f"L3(strip): {exc}")

    raise CheckerJSONParseError(raw, "; ".join(errors) if errors else "unknown parse failure")


def parse_llm_json_array(raw: str) -> list[dict[str, Any]]:
    """Like :func:`parse_llm_json` but guarantees the result is a list.

    Raises:
        CheckerJSONParseError: If parsing fails or result is not a list.
    """
    result = parse_llm_json(raw)
    if not isinstance(result, list):
        raise CheckerJSONParseError(raw, f"expected JSON array, got {type(result).__name__}")
    return result


def parse_llm_json_object(raw: str) -> dict[str, Any]:
    """Like :func:`parse_llm_json` but guarantees the result is a dict.

    Raises:
        CheckerJSONParseError: If parsing fails or result is not a dict.
    """
    result = parse_llm_json(raw)
    if not isinstance(result, dict):
        raise CheckerJSONParseError(raw, f"expected JSON object, got {type(result).__name__}")
    return result
