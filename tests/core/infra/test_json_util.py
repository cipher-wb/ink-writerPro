"""Tests for ink_writer.core.infra.json_util — 3-level JSON parse resilience."""

from __future__ import annotations

import pytest
from ink_writer.core.infra.json_util import (
    CheckerJSONParseError,
    parse_llm_json,
    parse_llm_json_array,
    parse_llm_json_object,
)

# ── parse_llm_json: Level 1 — bare JSON ──────────────────────────────


def test_bare_object():
    assert parse_llm_json('{"a": 1}') == {"a": 1}


def test_bare_array():
    assert parse_llm_json('[1, 2, 3]') == [1, 2, 3]


def test_bare_nested():
    assert parse_llm_json('{"a": [1, {"b": 2}]}') == {"a": [1, {"b": 2}]}


# ── parse_llm_json: Level 2 — regex extract from surrounding text ────


def test_prefix_text_object():
    result = parse_llm_json('Here is the result:\n{"x": 1, "y": 2}\nHope this helps.')
    assert result == {"x": 1, "y": 2}


def test_prefix_text_array():
    result = parse_llm_json('Results: [{"id": 1}, {"id": 2}] done.')
    assert result == [{"id": 1}, {"id": 2}]


def test_suffix_only():
    result = parse_llm_json('{"z": 99} trailing garbage')
    assert result == {"z": 99}


# ── parse_llm_json: Level 3 — markdown fence ─────────────────────────


def test_fenced_json_object():
    result = parse_llm_json('```json\n{"key": "value"}\n```')
    assert result == {"key": "value"}


def test_fenced_no_lang_tag():
    result = parse_llm_json('```\n{"a": 1}\n```')
    assert result == {"a": 1}


def test_fenced_json_array():
    result = parse_llm_json('```json\n[{"x": 1}]\n```')
    assert result == [{"x": 1}]


def test_fenced_with_surrounding_text():
    result = parse_llm_json(
        'Sure, here is the JSON:\n```json\n{"score": 0.85}\n```\nLet me know if you need changes.'
    )
    assert result == {"score": 0.85}


# ── parse_llm_json: edge cases ───────────────────────────────────────


def test_whitespace_only_input():
    with pytest.raises(CheckerJSONParseError, match="empty"):
        parse_llm_json("   \n\t  ")


def test_empty_string():
    with pytest.raises(CheckerJSONParseError, match="empty"):
        parse_llm_json("")


def test_non_string_input():
    with pytest.raises(CheckerJSONParseError, match="not a string"):
        parse_llm_json(42)  # type: ignore[arg-type]


def test_non_string_input_none():
    with pytest.raises(CheckerJSONParseError, match="not a string"):
        parse_llm_json(None)  # type: ignore[arg-type]


def test_unparseable_garbage():
    with pytest.raises(CheckerJSONParseError) as exc_info:
        parse_llm_json("this is not json at all, just random words")
    assert "L1:" in str(exc_info.value)


def test_chinese_text():
    with pytest.raises(CheckerJSONParseError) as exc_info:
        parse_llm_json("这是一段完全不是JSON的中文文本")
    assert "L1:" in str(exc_info.value)


def test_error_includes_raw_snippet():
    raw = "x" * 300
    with pytest.raises(CheckerJSONParseError) as exc_info:
        parse_llm_json(raw)
    # snippet is first 200 chars
    assert raw[:200] in str(exc_info.value)


# ── parse_llm_json_array — type guarantee ────────────────────────────


def test_array_valid():
    result = parse_llm_json_array('[{"a": 1}, {"b": 2}]')
    assert result == [{"a": 1}, {"b": 2}]


def test_array_rejects_object():
    with pytest.raises(CheckerJSONParseError, match="expected JSON array, got dict"):
        parse_llm_json_array('{"not": "array"}')


def test_array_rejects_scalar():
    with pytest.raises(CheckerJSONParseError, match="expected JSON array"):
        parse_llm_json_array("42")


# ── parse_llm_json_object — type guarantee ───────────────────────────


def test_object_valid():
    result = parse_llm_json_object('{"x": 1, "y": 2}')
    assert result == {"x": 1, "y": 2}


def test_object_rejects_array():
    with pytest.raises(CheckerJSONParseError, match="expected JSON object, got list"):
        parse_llm_json_object("[1, 2, 3]")


def test_object_rejects_scalar():
    with pytest.raises(CheckerJSONParseError, match="expected JSON object"):
        parse_llm_json_object("null")


# ── Robustness: mixed fence + extra text ─────────────────────────────


def test_fenced_then_extra_text():
    result = parse_llm_json('```json\n{"a": 1}\n```\nSome extra commentary.')
    assert result == {"a": 1}


def test_depth_markers_then_json():
    # LLMs sometimes output "Depth 1: ..." before JSON
    result = parse_llm_json('Depth analysis:\n{"surface": 0.3, "deep": 0.8}')
    assert result == {"surface": 0.3, "deep": 0.8}
