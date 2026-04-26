"""US-LR-003: LLM extractor — mock 模式 + 错误路径覆盖。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from ink_writer.live_review.extractor import (
    ExtractionError,
    _clamp_numeric_fields,
    extract_from_text,
)


def _load_mock(fixtures_dir: Path) -> list[dict]:
    return json.loads(
        (fixtures_dir / "mock_extract_BV12yBoBAEEn.json").read_text(encoding="utf-8")
    )


def test_extract_with_mock_returns_3_records(fixtures_dir):
    raw = (fixtures_dir / "raw_BV12yBoBAEEn.txt").read_text(encoding="utf-8")
    mock = _load_mock(fixtures_dir)
    records = extract_from_text(
        raw,
        bvid="BV12yBoBAEEn",
        source_path="/tmp/raw.txt",
        mock_response=mock,
    )
    assert len(records) == 3
    assert all(r["bvid"] == "BV12yBoBAEEn" for r in records)
    assert all(r["schema_version"] == "1.0" for r in records)


def test_extract_records_have_full_metadata(fixtures_dir):
    raw = (fixtures_dir / "raw_BV12yBoBAEEn.txt").read_text(encoding="utf-8")
    mock = _load_mock(fixtures_dir)
    records = extract_from_text(
        raw,
        bvid="BV12yBoBAEEn",
        source_path="/abs/path/raw.txt",
        model="claude-sonnet-4-6",
        extractor_version="1.0.0",
        mock_response=mock,
    )
    for r in records:
        assert r["model"] == "claude-sonnet-4-6"
        assert r["extractor_version"] == "1.0.0"
        assert r["source_path"] == "/abs/path/raw.txt"
        assert "extracted_at" in r and r["extracted_at"].endswith("Z")
        assert r["source_line_total"] == raw.count("\n") + 1


def test_extract_records_score_signal_diversity(fixtures_dir):
    """fixture 故意覆盖 explicit_number / sign_phrase / fuzzy 三类。"""
    raw = (fixtures_dir / "raw_BV12yBoBAEEn.txt").read_text(encoding="utf-8")
    records = extract_from_text(
        raw,
        bvid="BV12yBoBAEEn",
        source_path="/x",
        mock_response=_load_mock(fixtures_dir),
    )
    signals = {r["score_signal"] for r in records}
    assert signals == {"explicit_number", "sign_phrase", "fuzzy"}


def test_extract_invalid_json_raises():
    """LLM 返回非 JSON 必须 fail-loud，不 silent fallback。"""
    raw = "x"

    def bad_llm(prompt, text, model):
        return "this is not json {{{ broken"

    with pytest.raises(ExtractionError, match="not valid JSON"):
        extract_from_text(raw, bvid="BV1x", source_path="/x", llm_call=bad_llm)


def test_extract_non_array_raises():
    raw = "x"

    def bad_llm(prompt, text, model):
        return '{"not": "an array"}'

    with pytest.raises(ExtractionError, match="Expected JSON array"):
        extract_from_text(raw, bvid="BV1x", source_path="/x", llm_call=bad_llm)


def test_extract_schema_violation_raises():
    """LLM 漏字段必须 fail-loud。"""
    raw = "x"

    def bad_llm(prompt, text, model):
        return json.dumps([{
            "novel_idx": 0,
        }])

    with pytest.raises(ExtractionError, match="failed schema"):
        extract_from_text(raw, bvid="BV1x", source_path="/x", llm_call=bad_llm)


def test_extract_score_out_of_range_clamps_then_passes():
    """score=999 现在被软 clamp 到 100（自 §M-2 后；旧行为是 fail-loud）。"""
    raw = "x"

    def bad_llm(prompt, text, model):
        return json.dumps([{
            "novel_idx": 0,
            "line_start": 1,
            "line_end": 10,
            "title_guess": "x",
            "title_confidence": 0.5,
            "genre_guess": ["x"],
            "score": 999,
            "score_raw": "x",
            "score_signal": "explicit_number",
            "verdict": "pass",
            "overall_comment": "x",
            "comments": [],
        }])

    records = extract_from_text(raw, bvid="BV1x", source_path="/x", llm_call=bad_llm)
    assert len(records) == 1
    assert records[0]["score"] == 100  # clamped from 999


# === clamp 软容错 单测（修 §M-2 BV1F6 schema fail 'title_confidence=45 > 1.0' 后新增）===


def test_clamp_title_confidence_above_1():
    novel = {"title_confidence": 45}
    _clamp_numeric_fields(novel, novel_idx=0)
    assert novel["title_confidence"] == 1.0


def test_clamp_title_confidence_below_0():
    novel = {"title_confidence": -0.5}
    _clamp_numeric_fields(novel, novel_idx=0)
    assert novel["title_confidence"] == 0.0


def test_clamp_score_above_100():
    novel = {"score": 150}
    _clamp_numeric_fields(novel, novel_idx=0)
    assert novel["score"] == 100


def test_clamp_score_below_0():
    novel = {"score": -10}
    _clamp_numeric_fields(novel, novel_idx=0)
    assert novel["score"] == 0


def test_clamp_keeps_valid_values_unchanged():
    novel = {"title_confidence": 0.85, "score": 68}
    _clamp_numeric_fields(novel, novel_idx=0)
    assert novel["title_confidence"] == 0.85
    assert novel["score"] == 68


def test_clamp_handles_none_score():
    novel = {"score": None}
    _clamp_numeric_fields(novel, novel_idx=0)
    assert novel["score"] is None


def test_extract_with_oversize_title_confidence_clamps_then_passes(fixtures_dir):
    """LLM 误把 score 填进 title_confidence 时 clamp + 校验通过（不再 fail-loud）。"""
    raw = "x"

    def buggy_llm(prompt, text, model):
        return json.dumps([{
            "novel_idx": 0,
            "line_start": 1,
            "line_end": 10,
            "title_guess": "x",
            "title_confidence": 45,  # ← LLM 误填的分数
            "genre_guess": ["x"],
            "score": 45,
            "score_raw": "45 分",
            "score_signal": "explicit_number",
            "verdict": "fail",
            "overall_comment": "x",
            "comments": [],
        }])

    records = extract_from_text(raw, bvid="BV1x", source_path="/x", llm_call=buggy_llm)
    assert len(records) == 1
    assert records[0]["title_confidence"] == 1.0  # clamped
    assert records[0]["score"] == 45  # 未超界，原值保留


def test_clamp_dimension_not_in_enum_fallback_misc():
    novel = {"comments": [{"dimension": "title", "severity": "negative", "content": "x"}]}
    _clamp_numeric_fields(novel, novel_idx=0)
    assert novel["comments"][0]["dimension"] == "misc"


def test_clamp_severity_not_in_enum_fallback_neutral():
    novel = {"comments": [{"dimension": "opening", "severity": "negative_x", "content": "x"}]}
    _clamp_numeric_fields(novel, novel_idx=0)
    assert novel["comments"][0]["severity"] == "neutral"


def test_clamp_score_signal_not_in_enum_fallback_unknown():
    novel = {"score_signal": "weird_value"}
    _clamp_numeric_fields(novel, novel_idx=0)
    assert novel["score_signal"] == "unknown"


def test_clamp_verdict_not_in_enum_fallback_unknown():
    novel = {"verdict": "good"}
    _clamp_numeric_fields(novel, novel_idx=0)
    assert novel["verdict"] == "unknown"


def test_clamp_keeps_valid_enum_values_unchanged():
    novel = {
        "score_signal": "explicit_number",
        "verdict": "pass",
        "comments": [{"dimension": "opening", "severity": "positive", "content": "x"}],
    }
    _clamp_numeric_fields(novel, novel_idx=0)
    assert novel["score_signal"] == "explicit_number"
    assert novel["verdict"] == "pass"
    assert novel["comments"][0]["dimension"] == "opening"
    assert novel["comments"][0]["severity"] == "positive"
