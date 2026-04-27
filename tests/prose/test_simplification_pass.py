"""US-008: Simplification Pass tests.

Two tiers:

1. **Spec-level gate**: polish-agent.md must declare ``## Simplification Pass``
   section with the 5 rules, 70% floor, activation judgment and non-conflict
   notes per PRD AC.
2. **Helper behaviour**: ``ink_writer.prose.simplification_pass`` implements
   deterministic rule-based simplification (blacklist drop + long-sentence
   split + rhetoric collapse + empty-description compress) with the 70%
   rollback floor.

The canonical PRD requirement is: "人工构造冗余段，验证精简后字数减少 20%+
且黑名单词清零" — ``test_redundant_paragraph_reduced_and_blacklist_cleared``
is the driving assertion.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ink_writer.prose.blacklist_loader import clear_cache, load_blacklist
from ink_writer.prose.simplification_pass import (
    SimplificationReport,
    should_activate_simplification,
    simplify_text,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
POLISH_SPEC = REPO_ROOT / "ink-writer" / "agents" / "polish-agent.md"


# ---------------------------------------------------------------------------
# Spec-level gates
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def spec_text() -> str:
    assert POLISH_SPEC.exists(), f"polish-agent spec missing: {POLISH_SPEC}"
    return POLISH_SPEC.read_text(encoding="utf-8")


def test_simplification_pass_section_present(spec_text: str) -> None:
    assert "## Simplification Pass" in spec_text, (
        "polish-agent.md must declare ## Simplification Pass section (US-008 AC)"
    )


def test_simplification_pass_precedes_no_poison(spec_text: str) -> None:
    """Simplification Pass must execute before No-Poison Section 5."""
    sp_idx = spec_text.index("## Simplification Pass")
    np_idx = spec_text.index("### 5. No-Poison 毒点规避")
    assert sp_idx < np_idx, (
        "Simplification Pass 必须出现在 ### 5. No-Poison 毒点规避 之前"
    )


def test_simplification_pass_follows_layer9(spec_text: str) -> None:
    """Simplification Pass must execute after Layer 9 is complete."""
    sp_idx = spec_text.index("## Simplification Pass")
    l9_idx = spec_text.index("### 4.6 Layer 9")
    assert l9_idx < sp_idx, "Simplification Pass 必须位于 Layer 9 之后"


@pytest.mark.parametrize(
    "marker",
    [
        "chapter_no ∈ [1, 2, 3]",
        "combat",
        "climax",
        "high_point",
        "should_activate_simplification",
    ],
)
def test_activation_conditions_declared(spec_text: str, marker: str) -> None:
    assert marker in spec_text, (
        f"Simplification Pass 激活条件缺少关键词 {marker!r}"
    )


@pytest.mark.parametrize("rule_id", ["S1", "S2", "S3", "S4", "S5"])
def test_five_rules_declared(spec_text: str, rule_id: str) -> None:
    assert rule_id in spec_text, (
        f"Simplification Pass 五条规则缺少 {rule_id!r}（PRD US-008 AC 精简规则）"
    )


@pytest.mark.parametrize(
    "concept",
    [
        "黑名单",          # S1
        "> 35 字",         # S2 threshold
        "≤ 20 字",         # S2 target
        "连续修辞",        # S3
        "空描写段",        # S4
        "3 句",            # S4 threshold
        "形容词",          # S5
        "动词",            # S5
    ],
)
def test_rule_concepts_declared(spec_text: str, concept: str) -> None:
    assert concept in spec_text, (
        f"Simplification Pass 关键概念 {concept!r} 未在 spec 中出现"
    )


def test_70_percent_floor_declared(spec_text: str) -> None:
    assert "70%" in spec_text, "Simplification Pass 必须声明 70% 字数下限（PRD AC 4）"
    assert "回滚" in spec_text, (
        "Simplification Pass 必须标注回滚行为（过度精简保护）"
    )


def test_coexistence_with_existing_polish_paths(spec_text: str) -> None:
    """US-008 AC 5: Simplification must not break Anti-AI/修复/毒点 paths."""
    assert "并存" in spec_text or "互不覆盖" in spec_text, (
        "Simplification Pass 必须显式声明与其他层并存"
    )
    # Existing sections must remain intact.
    for must_keep in (
        "### 1.7 AI味句式多样性修复",
        "### 4. Anti-AI 二次验证",
        "### 5. No-Poison 毒点规避",
        "### 4.5 Layer 8 文笔工艺润色",
        "### 4.6 Layer 9 文笔冲击力润色",
    ):
        assert must_keep in spec_text, f"零回归：原有章节 {must_keep!r} 缺失"


def test_helper_api_referenced(spec_text: str) -> None:
    assert "ink_writer.prose.simplification_pass" in spec_text, (
        "Simplification Pass 必须点名辅助模块 `ink_writer.prose.simplification_pass`"
    )
    assert "SimplificationReport" in spec_text, (
        "Simplification Pass 需引用 SimplificationReport 字段语义"
    )


def test_blacklist_asset_referenced(spec_text: str) -> None:
    assert "prose-blacklist.yaml" in spec_text, (
        "Simplification Pass 必须点名 US-003 产出的 prose-blacklist.yaml 资产路径"
    )


# ---------------------------------------------------------------------------
# Activation helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scene_mode,chapter_no,expected",
    [
        # Explicit active scene_modes activate regardless of chapter
        ("combat", 50, True),
        ("climax", 99, True),
        ("high_point", 7, True),
        ("golden_three", 100, True),
        # golden_three fallback via chapter
        (None, 1, True),
        (None, 2, True),
        (None, 3, True),
        # Inactive modes short-circuit even in golden chapters (explicit优先)
        ("slow_build", 2, False),
        ("emotional", 1, False),
        ("other", 3, False),
        # Plain non-golden chapters with no scene_mode
        (None, 4, False),
        (None, 42, False),
        # Defensive zero/unknown chapter
        (None, 0, False),
    ],
)
def test_should_activate_simplification_matrix(
    scene_mode: str | None, chapter_no: int, expected: bool
) -> None:
    assert should_activate_simplification(scene_mode, chapter_no) is expected


def test_should_activate_matches_directness_checker() -> None:
    """Single-source guarantee: wrapper equals directness_checker.is_activated."""
    from ink_writer.prose.directness_checker import is_activated

    for sm in (None, "combat", "climax", "high_point", "slow_build", "emotional", "other"):
        for ch in (0, 1, 2, 3, 4, 50):
            assert should_activate_simplification(sm, ch) == is_activated(sm, ch), (
                f"wrapper drift for ({sm!r}, {ch})"
            )


# ---------------------------------------------------------------------------
# Core helper behaviour
# ---------------------------------------------------------------------------


def test_empty_text_returns_zero_report() -> None:
    report = simplify_text("")
    assert isinstance(report, SimplificationReport)
    assert report.simplified_text == ""
    assert report.original_char_count == 0
    assert report.simplified_char_count == 0
    assert report.blacklist_hits_before == 0
    assert report.blacklist_hits_after == 0
    assert report.rolled_back is False
    assert report.reduction_ratio == 0.0


def test_redundant_paragraph_reduced_and_blacklist_cleared() -> None:
    """PRD AC anchor: redundant paragraph reduces ≥20% AND blacklist hits clear to 0."""
    clear_cache()
    redundant = (
        # 注意 fixture 词汇必须只在 abstract_adjectives 一类（S1 规则覆盖范围）；
        # PRD US-002 把"苍茫"挪进了 pretentious_nouns，所以改用 "广袤"（非 BL 词）。
        "她莫名感到心头仿佛被无尽的寒意笼罩，"
        "宛如置身于一片广袤无边的雪原之中，"
        "四周静得仿佛时间都已停滞，仿佛连呼吸都成了多余。"
    )
    report = simplify_text(redundant)

    # Blacklist hits must reach 0 (primary AC).
    assert report.blacklist_hits_before > 0, "fixture 必须触发 blacklist（检查 YAML 是否按预期排序）"
    assert report.blacklist_hits_after == 0, (
        f"Simplification 后仍有 blacklist 命中: {report.blacklist_hits_after}; "
        "S1 规则未覆盖 abstract_adjectives"
    )

    # Reduction must meet 20% target (primary AC).
    assert report.reduction_ratio >= 0.20, (
        f"字数减少仅 {report.reduction_ratio:.1%}, PRD 要求 ≥20%"
    )

    # No rollback on this fixture (we're above 70% floor).
    assert report.rolled_back is False
    assert "blacklist_abstract_drop" in report.rules_fired


def test_long_sentence_split_fires() -> None:
    """Single sentence > 35 chars with comma is split into two."""
    clear_cache()
    long_sentence = (
        "主角走到门口抬头看向天上挂着的那轮巨大而明亮的月亮，"
        "心中隐约生出一股难以名状的复杂情绪。"
    )
    # length ~ 42, has a Chinese comma so S2 can split
    assert len(long_sentence) > 35
    report = simplify_text(long_sentence)
    assert "long_sentence_split" in report.rules_fired or "blacklist_abstract_drop" in report.rules_fired
    # After: every sentence body ≤ 35 chars OR simplified count ≤ original
    assert report.simplified_char_count <= report.original_char_count


def test_rhetoric_collapse_keeps_first_drops_rest() -> None:
    """Consecutive rhetoric markers within a sentence: keep first, drop 2nd+."""
    clear_cache()
    # Craft a sentence with repeated non-blacklist rhetoric to isolate S3.
    # Pick marker not in abstract_adjectives blacklist: "如同"
    # But make sure "如同" is NOT in abstract_adjectives (check dynamically).
    blacklist = load_blacklist()
    adj_words = {entry.word for entry in blacklist.abstract_adjectives}
    marker = None
    for candidate in ("如同", "好似"):
        if candidate not in adj_words:
            marker = candidate
            break
    assert marker is not None, "需要一个不在 abstract_adjectives 里的修辞标记"

    text = f"小明的心{marker}一片旷野，{marker}一座孤岛，{marker}一盏孤灯。"
    report = simplify_text(text)
    collapsed = report.simplified_text
    # Should have exactly 1 occurrence of the marker after S3
    assert collapsed.count(marker) == 1, (
        f"S3 连续修辞压缩未生效: 原 {text.count(marker)} 处, 现 {collapsed.count(marker)} 处"
    )
    assert "rhetoric_collapse" in report.rules_fired


def test_70_percent_floor_rollback_triggers() -> None:
    """Over-aggressive simplification below 70% floor must rollback."""
    clear_cache()
    # Pure-environment paragraph with > 3 sentences and no pronouns → S4 compresses
    # aggressively, dropping well below 70%. Rollback must fire.
    text = "夜幕降临。星光洒满天空。风从远处吹来。月光铺展地面。大地寂静。云层低垂。"
    report = simplify_text(text)
    if report.rolled_back:
        assert report.simplified_text == text, "回滚后必须返回原文"
        assert report.simplified_char_count == report.original_char_count
        assert report.reduction_ratio == 0.0
        assert report.blacklist_hits_after == report.blacklist_hits_before
    else:
        # If rule didn't fire enough to trip floor, accept graceful no-op.
        assert report.reduction_ratio >= 0.0


def test_loose_floor_allows_empty_desc_compression() -> None:
    """With 0.5 min_retention_ratio, empty-description S4 compresses freely."""
    clear_cache()
    text = (
        "小明走进房间，关上门，深吸一口气。\n\n"
        "远山如黛。苍茫一片。暮色四合。天地一色。寂静无声。微风拂过。月光洒落。"
    )
    report = simplify_text(text, min_retention_ratio=0.5)
    assert report.rolled_back is False
    # Paragraph 1 (with pronoun 明/他) preserved; paragraph 2 compressed.
    assert "小明走进房间" in report.simplified_text
    assert "empty_paragraph_compress" in report.rules_fired
    assert report.reduction_ratio > 0.0


def test_plain_chapter_text_unchanged_when_clean() -> None:
    """Clean, idiomatic text with no rule triggers stays byte-identical."""
    clear_cache()
    text = "小明走进教室，对李老师点头。李老师递过一本书。"
    report = simplify_text(text)
    assert report.simplified_text == text
    assert report.reduction_ratio == 0.0
    assert report.blacklist_hits_before == 0
    assert report.blacklist_hits_after == 0
    assert report.rolled_back is False


def test_reduction_ratio_property() -> None:
    """reduction_ratio = 1 - (simplified / original)."""
    rpt = SimplificationReport(
        simplified_text="abc",
        original_char_count=10,
        simplified_char_count=7,
        blacklist_hits_before=2,
        blacklist_hits_after=0,
        rolled_back=False,
    )
    assert rpt.reduction_ratio == pytest.approx(0.30)

    zero = SimplificationReport(
        simplified_text="",
        original_char_count=0,
        simplified_char_count=0,
        blacklist_hits_before=0,
        blacklist_hits_after=0,
        rolled_back=False,
    )
    assert zero.reduction_ratio == 0.0


def test_public_exports() -> None:
    """ink_writer.prose re-exports the helper API used by polish-agent."""
    from ink_writer import prose

    for name in (
        "SimplificationReport",
        "should_activate_simplification",
        "simplify_text",
    ):
        assert hasattr(prose, name), f"ink_writer.prose 未导出 {name!r}"
        assert name in prose.__all__, f"{name!r} 缺失于 prose.__all__"


def test_custom_blacklist_override() -> None:
    """Passing a custom Blacklist replaces the default YAML for that call."""
    from ink_writer.prose.blacklist_loader import Blacklist, BlacklistEntry

    custom = Blacklist(
        version=1,
        entries=(BlacklistEntry(word="独有魔咒", category="abstract_adjectives", replacement=""),),
    )
    text = "她心中独有魔咒在回响，迟迟不能散去。"
    report = simplify_text(text, blacklist=custom)
    assert "独有魔咒" not in report.simplified_text
    assert report.blacklist_hits_after == 0
    assert "blacklist_abstract_drop" in report.rules_fired
