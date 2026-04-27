"""PRD US-007: directness-checker D6/D7 维度测试。

验证:
  1. D6 嵌套深度: 爆款短句 → green；长嵌套从句 → red
  2. D7 修饰链长: 爆款短句 → green；长修饰链 → red
  3. D1-D5 回归不受影响
  4. metrics_raw 包含 D6/D7 字段 + D7_modifier_max_chain
"""

from __future__ import annotations

import textwrap

import pytest
from ink_writer.prose.directness_checker import (
    DIMENSION_KEYS,
    _calc_d6_nesting_depth,
    _calc_d7_modifier_chain_length,
    run_directness_check,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Fixture 1: 爆款短句 — 短句，少逗号，极少修饰
_EXPLOSIVE_SHORT = textwrap.dedent(
    """
    他推开门。
    屋子里没人。
    桌上摆着三封信。
    "你来了。"老人抬起头。
    他拉开椅子坐下。
    伸手摸了一下信封的封口。
    "这封是林老板寄的。"老人慢慢开口。
    他没有立刻回答。
    他把信封翻了个面。
    看了看邮戳的日期。
    "我去一趟苏州。"
    他站起来把剑扛上肩。
    "三天内回来。"
    老人点了点头。
    """
).strip()

# Fixture 2: 长嵌套从句 — 逗号密集，多层嵌套
_NESTED_CLAUSES = textwrap.dedent(
    """
    他走进房间，看见桌子上摆着三封信，分别是林老板寄来的账目清单、王掌柜送来的货物清单、以及一封没有署名的密信，每一封都压在茶杯下面，整整齐齐地排成一排。

    老人抬起头，看着他的脸，似乎想要从他的表情里读出什么，却发现自己什么也读不出来，于是叹了口气，把茶杯慢慢推到他面前，用沙哑的声音说了句什么话。

    他拉开椅子，坐下来，先看了看最上面那封信的封口，又翻了翻下面两封信的邮戳日期，发现日期都对不上，眉头不由得皱了起来。

    风吹过院子，吹动了窗台上的落叶，吹动了桌上那几封信的边角，也吹动了他额前垂下来的几缕头发，他伸手按住信封，静静地等着风停下来。
    """
).strip()

# Fixture 3: 长修饰链 — 多层"的"修饰
_LONG_MODIFIER_CHAINS = textwrap.dedent(
    """
    古老的破旧的褪色的木门缓缓打开了，门后是一间幽暗的潮湿的散发着霉味的石室。

    那个高大的强壮的沉默的男人转过身来，他的深邃的锐利的冰冷的眼睛扫过房间里的每一个人。

    她伸手抚摸着那本泛黄的厚重的记载着古老秘密的羊皮书，指尖传来的粗糙的干燥的温度让她想起祖母的温暖的笑脸。

    远处的苍茫的无尽的灰暗的天空下，孤独的破败的被遗忘的城堡矗立在荒芜的寂静的冰封的大地上。
    """
).strip()


# ---------------------------------------------------------------------------
# D6: nesting depth
# ---------------------------------------------------------------------------

class TestD6NestingDepth:
    def test_explosive_short_nesting_low(self) -> None:
        """爆款短句: 嵌套深度应很低 (< 1.5 → green)。"""
        depth = _calc_d6_nesting_depth(_EXPLOSIVE_SHORT)
        assert depth < 1.5, f"爆款短句 nesting depth={depth} 应 < 1.5"

    def test_nested_clauses_nesting_high(self) -> None:
        """长嵌套从句: 嵌套深度应较高 (≥ 2.0)。"""
        depth = _calc_d6_nesting_depth(_NESTED_CLAUSES)
        assert depth >= 2.0, f"嵌套从句 nesting depth={depth} 应 ≥ 2.0"

    def test_empty_text_returns_zero(self) -> None:
        assert _calc_d6_nesting_depth("") == 0.0

    def test_single_sentence_no_commas(self) -> None:
        """单句无逗号 → depth = 1。"""
        depth = _calc_d6_nesting_depth("他走进房间。")
        assert depth == 1.0

    def test_single_sentence_with_commas(self) -> None:
        """单句有 2 个逗号 → 3 子句 → depth = 3。"""
        depth = _calc_d6_nesting_depth("他走进房间，看见桌上摆着三封信，然后又退了出去。")
        assert depth == 3.0

    def test_run_directness_check_d6_green(self) -> None:
        """爆款短句 → D6 应为 green。"""
        report = run_directness_check(
            _EXPLOSIVE_SHORT, chapter_no=1, scene_mode=None
        )
        assert not report.skipped
        d6 = next(d for d in report.dimensions if d.key == "D6_nesting_depth")
        assert d6.rating == "green", (
            f"爆款短句 D6 应为 green, got {d6.rating}: {d6.to_dict()}"
        )

    def test_run_directness_check_d6_red(self) -> None:
        """长嵌套从句 → D6 应为 yellow 或 red。"""
        report = run_directness_check(
            _NESTED_CLAUSES, chapter_no=1, scene_mode=None
        )
        assert not report.skipped
        d6 = next(d for d in report.dimensions if d.key == "D6_nesting_depth")
        assert d6.rating in {"yellow", "red"}, (
            f"嵌套从句 D6 应为 yellow/red, got {d6.rating}: {d6.to_dict()}"
        )

    def test_d6_issue_generated_when_not_green(self) -> None:
        """D6 非 green 时应生成 issue。"""
        report = run_directness_check(
            _NESTED_CLAUSES, chapter_no=1, scene_mode=None
        )
        d6_issues = [i for i in report.issues if i.dimension == "D6_nesting_depth"]
        d6 = next(d for d in report.dimensions if d.key == "D6_nesting_depth")
        if d6.rating != "green":
            assert d6_issues, f"D6 {d6.rating} 应生成 issue"
            for issue in d6_issues:
                assert issue.line_range[0] >= 1
                assert "嵌套" in issue.description
                assert issue.evidence.get("excerpt")


# ---------------------------------------------------------------------------
# D7: modifier chain length
# ---------------------------------------------------------------------------

class TestD7ModifierChainLength:
    def test_explosive_short_modifier_low(self) -> None:
        """爆款短句: 修饰链长应很低 (< 1.5 → green)。"""
        mean_chain, _ = _calc_d7_modifier_chain_length(_EXPLOSIVE_SHORT)
        assert mean_chain < 1.5, f"爆款短句 modifier mean={mean_chain} 应 < 1.5"

    def test_long_modifier_chains_high(self) -> None:
        """长修饰链: mean chain length 应 ≥ 2.0。"""
        mean_chain, max_chain = _calc_d7_modifier_chain_length(_LONG_MODIFIER_CHAINS)
        assert mean_chain >= 2.0, (
            f"长修饰链 mean={mean_chain} 应 ≥ 2.0"
        )
        assert max_chain >= 3, (
            f"长修饰链 max_chain={max_chain} 应 ≥ 3"
        )

    def test_empty_text_returns_zero(self) -> None:
        mean_chain, max_chain = _calc_d7_modifier_chain_length("")
        assert mean_chain == 0.0
        assert max_chain == 0

    def test_no_modifier_chains(self) -> None:
        """无'的'修饰的文本 → 0。"""
        mean_chain, max_chain = _calc_d7_modifier_chain_length("他走进房间坐下打开信纸")
        assert mean_chain == 0.0
        assert max_chain == 0

    def test_single_modifier_level(self) -> None:
        """单层修饰 '高大的树' → chain length = 1。"""
        mean_chain, max_chain = _calc_d7_modifier_chain_length("高大的树站在院子里。")
        assert mean_chain == 1.0
        assert max_chain == 1

    def test_triple_modifier_level(self) -> None:
        """三层修饰 '古老的破旧的褪色的木门' → chain length = 3。"""
        mean_chain, max_chain = _calc_d7_modifier_chain_length(
            "古老的破旧的褪色的木门缓缓打开了。"
        )
        assert mean_chain == 3.0
        assert max_chain == 3

    def test_run_directness_check_d7_green(self) -> None:
        """爆款短句 → D7 应为 green。"""
        report = run_directness_check(
            _EXPLOSIVE_SHORT, chapter_no=1, scene_mode=None
        )
        assert not report.skipped
        d7 = next(d for d in report.dimensions if d.key == "D7_modifier_chain_length")
        assert d7.rating == "green", (
            f"爆款短句 D7 应为 green, got {d7.rating}: {d7.to_dict()}"
        )

    def test_run_directness_check_d7_red(self) -> None:
        """长修饰链 → D7 应为 yellow 或 red。"""
        report = run_directness_check(
            _LONG_MODIFIER_CHAINS, chapter_no=1, scene_mode=None
        )
        assert not report.skipped
        d7 = next(d for d in report.dimensions if d.key == "D7_modifier_chain_length")
        assert d7.rating in {"yellow", "red"}, (
            f"长修饰链 D7 应为 yellow/red, got {d7.rating}: {d7.to_dict()}"
        )

    def test_d7_issue_generated_when_not_green(self) -> None:
        """D7 非 green 时应生成 issue。"""
        report = run_directness_check(
            _LONG_MODIFIER_CHAINS, chapter_no=1, scene_mode=None
        )
        d7_issues = [i for i in report.issues if i.dimension == "D7_modifier_chain_length"]
        d7 = next(d for d in report.dimensions if d.key == "D7_modifier_chain_length")
        if d7.rating != "green":
            assert d7_issues, f"D7 {d7.rating} 应生成 issue"
            for issue in d7_issues:
                assert issue.line_range[0] >= 1
                assert "修饰链" in issue.description
                assert issue.evidence.get("excerpt")


# ---------------------------------------------------------------------------
# D1-D5 regression: existing dimensions unaffected
# ---------------------------------------------------------------------------

class TestD1D5Regression:
    """AC: 原 D1-D5 单测保持通过 — 验证 D1-D5 仍在 dimension 列表中。"""

    def test_d1_d5_keys_still_present(self) -> None:
        expected_d1_d5 = frozenset({
            "D1_rhetoric_density",
            "D2_adj_verb_ratio",
            "D3_abstract_per_100_chars",
            "D4_sent_len_median",
            "D5_empty_paragraphs",
        })
        actual = frozenset(DIMENSION_KEYS)
        assert expected_d1_d5.issubset(actual), (
            f"D1-D5 keys missing from DIMENSION_KEYS: {expected_d1_d5 - actual}"
        )

    def test_seven_dimensions_total(self) -> None:
        assert len(DIMENSION_KEYS) == 7

    def test_explosive_short_all_dimensions_scored(self) -> None:
        """爆款短句: 7 维度都打分。"""
        report = run_directness_check(
            _EXPLOSIVE_SHORT, chapter_no=1, scene_mode=None
        )
        assert not report.skipped
        assert len(report.dimensions) == 7
        keys = {d.key for d in report.dimensions}
        assert "D6_nesting_depth" in keys
        assert "D7_modifier_chain_length" in keys

    def test_metrics_raw_contains_d6_d7(self) -> None:
        """metrics_raw 包含 D6/D7 字段。"""
        report = run_directness_check(
            _EXPLOSIVE_SHORT, chapter_no=1, scene_mode=None
        )
        raw = report.metrics_raw
        assert "D6_nesting_depth" in raw
        assert "D7_modifier_chain_length" in raw
        assert "D7_modifier_max_chain" in raw
        assert raw["D7_modifier_max_chain"] >= 0
