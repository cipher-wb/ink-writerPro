"""Schema / 完整性测试 — data/market_intelligence/llm_naming_blacklist.json (US-008)。

PRD acceptance：
- exact_blacklist >= 100、char_patterns.first_char_overused >= 20、second_char_overused >= 20
- exact_blacklist 内无重复
- 所有条目均为中文字符（unicode 一 ~ 鿿）
- naming-style-checker 用真词典对 '叶凡' 命中 exact (score=0.0/blocked/hit_type='exact')
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ink_writer.checkers.naming_style import check_naming_style

_BLACKLIST_PATH = Path("data/market_intelligence/llm_naming_blacklist.json")
_CJK_START = "一"
_CJK_END = "鿿"


def _load_blacklist() -> dict:
    with open(_BLACKLIST_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def blacklist() -> dict:
    return _load_blacklist()


def test_blacklist_schema(blacklist: dict) -> None:
    assert blacklist["version"]
    assert blacklist["updated_at"]

    exact = blacklist["exact_blacklist"]
    assert isinstance(exact, list)
    assert len(exact) >= 100, f"expect >= 100, got {len(exact)}"

    patterns = blacklist["char_patterns"]
    first = patterns["first_char_overused"]
    second = patterns["second_char_overused"]
    assert isinstance(first, list) and len(first) >= 20, f"first_char_overused {len(first)}"
    assert isinstance(second, list) and len(second) >= 20, f"second_char_overused {len(second)}"

    must_first = set("叶林陈李沈苏顾韩罗秦楚白王唐萧云夜风凌墨玄九易古")
    must_second = set("凡辰天尘轩夜墨寒风炎渊宇杰豪翔腾霖瀚霸雷煜燃铮翊")
    assert must_first.issubset(set(first)), f"missing firsts: {must_first - set(first)}"
    assert must_second.issubset(set(second)), f"missing seconds: {must_second - set(second)}"


def test_blacklist_no_duplicates(blacklist: dict) -> None:
    exact = blacklist["exact_blacklist"]
    seen: set[str] = set()
    duplicates: list[str] = []
    for name in exact:
        if name in seen:
            duplicates.append(name)
        seen.add(name)
    assert not duplicates, f"duplicate exact entries: {duplicates}"


def test_blacklist_chinese_only(blacklist: dict) -> None:
    def _all_chinese(text: str) -> bool:
        return all(_CJK_START <= ch <= _CJK_END for ch in text)

    bad: list[str] = []
    for name in blacklist["exact_blacklist"]:
        if not _all_chinese(name):
            bad.append(name)
    for ch in blacklist["char_patterns"]["first_char_overused"]:
        if not _all_chinese(ch) or len(ch) != 1:
            bad.append(ch)
    for ch in blacklist["char_patterns"]["second_char_overused"]:
        if not _all_chinese(ch) or len(ch) != 1:
            bad.append(ch)
    assert not bad, f"non-Chinese / non-single-char entries: {bad[:5]}"


def test_naming_style_checker_blocks_yefan_with_real_blacklist() -> None:
    report = check_naming_style(
        character_names=[{"role": "protagonist", "name": "叶凡"}],
        blacklist_path=_BLACKLIST_PATH,
    )
    assert report.score == 0.0
    assert report.blocked is True
    assert len(report.per_name_scores) == 1
    assert report.per_name_scores[0]["hit_type"] == "exact"
    assert report.per_name_scores[0]["name"] == "叶凡"
