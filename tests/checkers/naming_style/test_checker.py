"""naming-style-checker 单元测试 — M4 spec §3.3 + Q3。

纯规则 checker，无 LLM 调用 — 不使用 mock_llm_client fixture。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ink_writer.checkers.naming_style import NamingStyleReport, check_naming_style

_BLACKLIST_PAYLOAD: dict[str, Any] = {
    "version": "1.0",
    "exact_blacklist": ["叶凡", "林夜", "陈青山"],
    "char_patterns": {
        "first_char_overused": ["叶", "林", "沈", "陈", "苏"],
        "second_char_overused": ["凡", "夜", "尘", "墨", "辰"],
    },
    "notes": "test fixture",
}


@pytest.fixture
def blacklist_file(tmp_path: Path) -> Path:
    path = tmp_path / "llm_naming_blacklist.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(_BLACKLIST_PAYLOAD, fh, ensure_ascii=False)
    return path


def test_exact_match_zero(blacklist_file: Path) -> None:
    report = check_naming_style(
        character_names=[{"role": "主角", "name": "叶凡"}],
        blacklist_path=blacklist_file,
    )
    assert isinstance(report, NamingStyleReport)
    assert report.score == pytest.approx(0.0)
    assert report.blocked is True
    assert report.per_name_scores[0]["hit_type"] == "exact"
    assert report.per_name_scores[0]["score"] == pytest.approx(0.0)
    assert report.cases_hit == []


def test_double_char_pattern(blacklist_file: Path) -> None:
    # "苏墨"：苏 ∈ first_char_overused 且 墨 ∈ second_char_overused → 双字模式
    report = check_naming_style(
        character_names=[{"role": "主角", "name": "苏墨"}],
        blacklist_path=blacklist_file,
    )
    assert report.score == pytest.approx(0.4)
    assert report.blocked is True  # 0.4 < 0.70
    assert report.per_name_scores[0]["hit_type"] == "double_char"


def test_single_char_pattern(blacklist_file: Path) -> None:
    # "苏星河"：苏 ∈ first_char_overused，河 ∉ second_char_overused → 单字模式
    report = check_naming_style(
        character_names=[{"role": "主角", "name": "苏星河"}],
        blacklist_path=blacklist_file,
    )
    assert report.score == pytest.approx(0.7)
    assert report.blocked is False  # 0.7 >= 0.70
    assert report.per_name_scores[0]["hit_type"] == "single_char"


def test_clean_name_passes(blacklist_file: Path) -> None:
    # "顾望安"：顾 ∉ first，安 ∉ second → clean
    report = check_naming_style(
        character_names=[{"role": "主角", "name": "顾望安"}],
        blacklist_path=blacklist_file,
    )
    assert report.score == pytest.approx(1.0)
    assert report.blocked is False
    assert report.per_name_scores[0]["hit_type"] == "clean"


def test_multiple_names_average(blacklist_file: Path) -> None:
    # 顾望安 (1.0) + 苏星河 (0.7) + 苏墨 (0.4) → mean = 0.7
    report = check_naming_style(
        character_names=[
            {"role": "主角", "name": "顾望安"},
            {"role": "女主", "name": "苏星河"},
            {"role": "反派", "name": "苏墨"},
        ],
        blacklist_path=blacklist_file,
    )
    assert report.score == pytest.approx(0.7)
    assert report.blocked is False  # 0.7 >= 0.70
    assert len(report.per_name_scores) == 3
    hit_types = [item["hit_type"] for item in report.per_name_scores]
    assert hit_types == ["clean", "single_char", "double_char"]


def test_blacklist_missing_blocks(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.json"
    report = check_naming_style(
        character_names=[{"role": "主角", "name": "顾望安"}],
        blacklist_path=missing,
    )
    assert report.score == pytest.approx(0.0)
    assert report.blocked is True
    assert "blacklist_missing" in report.notes
