"""US-LR-001: live_review_extracted + genre_acceptance schemas valid."""
from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator, ValidationError


def test_extracted_schema_self_valid(load_schema):
    schema = load_schema("live_review_extracted.schema.json")
    Draft202012Validator.check_schema(schema)


def test_genre_acceptance_schema_self_valid(load_schema):
    schema = load_schema("live_review_genre_acceptance.schema.json")
    Draft202012Validator.check_schema(schema)


def _minimal_extracted() -> dict:
    return {
        "schema_version": "1.0",
        "bvid": "BV12yBoBAEEn",
        "source_path": "/tmp/raw.txt",
        "source_line_total": 1000,
        "extracted_at": "2026-04-27T10:00:00Z",
        "model": "claude-sonnet-4-6",
        "extractor_version": "1.0.0",
        "novel_idx": 0,
        "line_start": 100,
        "line_end": 200,
        "title_guess": "都市重生律师文",
        "title_confidence": 0.7,
        "genre_guess": ["都市"],
        "score": 68,
        "score_raw": "68 吧是吧",
        "score_signal": "explicit_number",
        "verdict": "borderline",
        "overall_comment": "节奏不错但金手指出现太晚",
        "comments": [
            {
                "dimension": "pacing",
                "severity": "negative",
                "content": "开篇拖沓",
                "raw_quote": "拖沓兄弟",
                "raw_line_range": [110, 117],
            }
        ],
    }


def test_extracted_minimal_valid(load_schema):
    schema = load_schema("live_review_extracted.schema.json")
    Draft202012Validator(schema).validate(_minimal_extracted())


def test_extracted_score_null_allowed(load_schema):
    schema = load_schema("live_review_extracted.schema.json")
    data = _minimal_extracted()
    data["score"] = None
    data["score_signal"] = "unknown"
    data["verdict"] = "unknown"
    Draft202012Validator(schema).validate(data)


def test_extracted_invalid_dimension_rejected(load_schema):
    schema = load_schema("live_review_extracted.schema.json")
    data = _minimal_extracted()
    data["comments"][0]["dimension"] = "not_a_real_dim"
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(data)


def test_extracted_score_out_of_range_rejected(load_schema):
    schema = load_schema("live_review_extracted.schema.json")
    data = _minimal_extracted()
    data["score"] = 200
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(data)


def test_extracted_unknown_top_field_rejected(load_schema):
    schema = load_schema("live_review_extracted.schema.json")
    data = _minimal_extracted()
    data["foo"] = "bar"
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(data)


def _minimal_genre_acceptance() -> dict:
    return {
        "schema_version": "1.0",
        "updated_at": "2026-04-27T10:00:00Z",
        "total_novels_analyzed": 1500,
        "min_cases_per_genre": 3,
        "genres": {
            "都市": {
                "case_count": 5,
                "score_mean": 65.0,
                "verdict_pass_rate": 0.6,
                "common_complaints": [],
                "case_ids": ["CASE-LR-2026-0001"],
            }
        },
    }


def test_genre_acceptance_minimal_valid(load_schema):
    schema = load_schema("live_review_genre_acceptance.schema.json")
    Draft202012Validator(schema).validate(_minimal_genre_acceptance())


def test_genre_acceptance_invalid_case_id_rejected(load_schema):
    schema = load_schema("live_review_genre_acceptance.schema.json")
    data = _minimal_genre_acceptance()
    data["genres"]["都市"]["case_ids"] = ["CASE-2026-0001"]  # 非 CASE-LR- 前缀
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(data)
