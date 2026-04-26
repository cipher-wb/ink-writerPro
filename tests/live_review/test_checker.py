"""US-LR-012 Tests for run_live_review_checker — chapter 评分 + violations + cases_hit。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_CHAPTER = FIXTURES_DIR / "sample_chapter_violating.txt"
MOCK_CHECKER_RESPONSE = FIXTURES_DIR / "mock_live_review_checker_response.json"


@pytest.fixture
def chapter_text() -> str:
    return SAMPLE_CHAPTER.read_text(encoding="utf-8")


@pytest.fixture
def mock_response() -> dict:
    return json.loads(MOCK_CHECKER_RESPONSE.read_text(encoding="utf-8"))


@pytest.fixture
def enabled_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "live-review.yaml"
    cfg.write_text(
        "enabled: true\ninject_into:\n  init: true\n  review: true\n",
        encoding="utf-8",
    )
    return cfg


def test_checker_with_mock_returns_full_structure(
    chapter_text: str, mock_response: dict, enabled_config: Path
) -> None:
    """mock_response 注入 → 返回字段齐全（score/dimensions/violations/cases_hit）。"""
    from ink_writer.live_review.checker import run_live_review_checker

    out = run_live_review_checker(
        chapter_text,
        chapter_no=1,
        genre_tags=["都市", "重生"],
        mock_response=mock_response,
        config_path=enabled_config,
    )
    assert isinstance(out["score"], (int, float))
    assert 0 <= out["score"] <= 1
    assert isinstance(out["dimensions"], dict)
    assert len(out["dimensions"]) >= 1
    assert isinstance(out["violations"], list)
    assert len(out["violations"]) == 3
    assert isinstance(out["cases_hit"], list)
    assert len(out["cases_hit"]) == 3
    for v in out["violations"]:
        for field in ("case_id", "dimension", "evidence_quote", "severity"):
            assert field in v, f"violation missing field {field}"


def test_score_below_hard_gate_indicates_block(
    chapter_text: str, mock_response: dict, enabled_config: Path
) -> None:
    """mock score=0.45 < hard_gate 0.65 → 调用方应判定阻断。"""
    from ink_writer.live_review.checker import run_live_review_checker

    out = run_live_review_checker(
        chapter_text,
        chapter_no=10,
        genre_tags=["都市"],
        mock_response=mock_response,
        config_path=enabled_config,
    )
    assert out["score"] == 0.45
    assert out["score"] < 0.65, "score should be below hard_gate_threshold"


def test_score_above_threshold_passes(
    chapter_text: str, enabled_config: Path
) -> None:
    """mock score=0.80 > hard_gate 0.65 → 通行（调用方判定）。"""
    from ink_writer.live_review.checker import run_live_review_checker

    high_mock = {
        "score": 0.80,
        "dimensions": {"opening": 0.85, "pacing": 0.75},
        "violations": [],
        "cases_hit": ["CASE-LR-2026-0010"],
    }
    out = run_live_review_checker(
        chapter_text,
        chapter_no=5,
        genre_tags=["职业流"],
        mock_response=high_mock,
        config_path=enabled_config,
    )
    assert out["score"] == 0.80
    assert out["score"] >= 0.65
    assert out["violations"] == []


def test_checker_disabled_returns_default(
    chapter_text: str, mock_response: dict, tmp_path: Path
) -> None:
    """inject_into.review=false 时 checker 早退（不消费 mock）。"""
    from ink_writer.live_review.checker import run_live_review_checker

    cfg = tmp_path / "live-review.yaml"
    cfg.write_text(
        "enabled: true\ninject_into:\n  init: true\n  review: false\n",
        encoding="utf-8",
    )
    out = run_live_review_checker(
        chapter_text,
        chapter_no=1,
        genre_tags=["都市"],
        mock_response=mock_response,
        config_path=cfg,
    )
    assert out.get("disabled") is True
    assert out["score"] == 1.0
    assert out["violations"] == []
    assert out["cases_hit"] == []


def test_checker_globally_disabled_returns_default(
    chapter_text: str, mock_response: dict, tmp_path: Path
) -> None:
    """enabled=false 全局短路。"""
    from ink_writer.live_review.checker import run_live_review_checker

    cfg = tmp_path / "live-review.yaml"
    cfg.write_text(
        "enabled: false\ninject_into:\n  init: true\n  review: true\n",
        encoding="utf-8",
    )
    out = run_live_review_checker(
        chapter_text,
        chapter_no=1,
        genre_tags=["都市"],
        mock_response=mock_response,
        config_path=cfg,
    )
    assert out.get("disabled") is True
    assert out["score"] == 1.0
