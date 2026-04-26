"""US-LR-003: LLM extractor — mock 模式 + 错误路径覆盖。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from ink_writer.live_review.extractor import ExtractionError, extract_from_text


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


def test_extract_score_out_of_range_raises():
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

    with pytest.raises(ExtractionError, match="failed schema"):
        extract_from_text(raw, bvid="BV1x", source_path="/x", llm_call=bad_llm)
