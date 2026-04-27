"""Tests for PRD US-002 三域 + replacement_map (爆款风装逼词).

Validates that the shipped YAML has the required minima (≥30 词/类), all 90+
words round-trip through :class:`Blacklist`, and ``replacement_map`` supports
bidirectional queries (forward word→replacements + reverse replacement→origins).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ink_writer.prose import blacklist_loader
from ink_writer.prose.blacklist_loader import (
    Blacklist,
    ReplacementMap,
    clear_cache,
    load_blacklist,
    load_pretentious_adverbs,
    load_pretentious_nouns,
    load_pretentious_verbs,
    load_replacement_map,
)

yaml = pytest.importorskip("yaml")


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    clear_cache()


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Shipped YAML 验收门槛（PRD US-002）
# ---------------------------------------------------------------------------


def test_shipped_yaml_has_three_pretentious_domains_at_30_each() -> None:
    bundle = load_blacklist()
    assert isinstance(bundle, Blacklist)
    assert len(bundle.pretentious_verbs) >= 30, "PRD US-002: ≥30 verbs"
    assert len(bundle.pretentious_nouns) >= 30, "PRD US-002: ≥30 nouns"
    assert len(bundle.pretentious_adverbs) >= 30, "PRD US-002: ≥30 adverbs"
    # 90+ 总数
    new_total = (
        len(bundle.pretentious_verbs)
        + len(bundle.pretentious_nouns)
        + len(bundle.pretentious_adverbs)
    )
    assert new_total >= 90, f"PRD US-002: 三域合计 ≥90，实测 {new_total}"


def test_shipped_yaml_seed_words_present() -> None:
    """PRD US-002 example seeds 必须落在词表里。"""
    bundle = load_blacklist()
    verb_words = {e.word for e in bundle.pretentious_verbs}
    noun_words = {e.word for e in bundle.pretentious_nouns}
    adv_words = {e.word for e in bundle.pretentious_adverbs}

    # PRD AC 列出的种子词
    for w in ("凝视", "伫立", "驻足", "凝望", "审视", "睥睨", "俯瞰", "仰望", "瞥见", "扫视"):
        assert w in verb_words, f"verb 种子词 {w!r} 缺失"
    for w in ("宿命", "苍茫", "沧桑", "孤寂", "静谧", "缱绻", "旖旎"):
        assert w in noun_words, f"noun 种子词 {w!r} 缺失"
    for w in ("缓缓", "徐徐", "悄然", "淡然", "默然", "怅然", "兀自", "兀然"):
        assert w in adv_words, f"adverb 种子词 {w!r} 缺失"


def test_each_new_entry_has_replacement_hint() -> None:
    """新三域所有条目都必须带 replacement 教学性提示。"""
    bundle = load_blacklist()
    for cat in ("pretentious_verbs", "pretentious_nouns", "pretentious_adverbs"):
        for entry in (e for e in bundle.entries if e.category == cat):
            assert entry.word, f"{cat} 出现空 word"
            assert entry.replacement, f"{cat}/{entry.word} 缺 replacement"


def test_no_word_collisions_across_pretentious_categories() -> None:
    """三个新域之间互斥：一个词只能进一个新域。"""
    bundle = load_blacklist()
    verb_words = {e.word for e in bundle.pretentious_verbs}
    noun_words = {e.word for e in bundle.pretentious_nouns}
    adv_words = {e.word for e in bundle.pretentious_adverbs}
    assert verb_words & noun_words == set(), "verbs 与 nouns 不应重叠"
    assert verb_words & adv_words == set(), "verbs 与 adverbs 不应重叠"
    assert noun_words & adv_words == set(), "nouns 与 adverbs 不应重叠"


# ---------------------------------------------------------------------------
# Convenience 模块函数
# ---------------------------------------------------------------------------


def test_module_helpers_match_blacklist_attrs() -> None:
    bundle = load_blacklist()
    assert load_pretentious_verbs() == bundle.pretentious_verbs
    assert load_pretentious_nouns() == bundle.pretentious_nouns
    assert load_pretentious_adverbs() == bundle.pretentious_adverbs


def test_module_helpers_accept_custom_path(tmp_path: Path) -> None:
    target = tmp_path / "bl.yaml"
    _write_yaml(
        target,
        {
            "version": 2,
            "pretentious_verbs": [{"word": "凝视", "replacement": "盯着"}],
            "pretentious_nouns": [{"word": "宿命", "replacement": "命"}],
            "pretentious_adverbs": [{"word": "缓缓", "replacement": "慢慢"}],
        },
    )
    assert [e.word for e in load_pretentious_verbs(target)] == ["凝视"]
    assert [e.word for e in load_pretentious_nouns(target)] == ["宿命"]
    assert [e.word for e in load_pretentious_adverbs(target)] == ["缓缓"]


def test_helpers_on_missing_file_return_empty(tmp_path: Path) -> None:
    nope = tmp_path / "nope.yaml"
    assert load_pretentious_verbs(nope) == ()
    assert load_pretentious_nouns(nope) == ()
    assert load_pretentious_adverbs(nope) == ()
    assert load_replacement_map(nope) == ReplacementMap()


# ---------------------------------------------------------------------------
# replacement_map 双向查询
# ---------------------------------------------------------------------------


def test_shipped_replacement_map_covers_all_pretentious_domains() -> None:
    """replacement_map 必须涵盖三域 ≥80% 的 word（每域至少几个示例）。"""
    bundle = load_blacklist()
    rmap = bundle.replacement_map

    # 至少 100 条（PRD AC："每个装逼词给出 1-3 个爆款替换" 三域 ~100）
    assert len(rmap) >= 90, f"replacement_map 至少 90 条，实测 {len(rmap)}"

    # 必须涵盖 PRD AC 列出的示例
    assert rmap.lookup("凝视") == ("盯着", "看着", "死盯"), (
        "PRD US-002 文档里直接给的例子必须 1:1 命中"
    )

    # 三域抽样：每域至少有一个 word 进入 forward
    verb_words = {e.word for e in bundle.pretentious_verbs}
    noun_words = {e.word for e in bundle.pretentious_nouns}
    adv_words = {e.word for e in bundle.pretentious_adverbs}
    forward_keys = set(rmap.forward.keys())
    assert forward_keys & verb_words, "rmap 需含至少 1 个 verb"
    assert forward_keys & noun_words, "rmap 需含至少 1 个 noun"
    assert forward_keys & adv_words, "rmap 需含至少 1 个 adverb"


def test_replacement_map_bidirectional_lookup() -> None:
    """forward (word → replacements) 与 reverse (replacement → origins) 必须一致。"""
    bundle = load_blacklist()
    rmap = bundle.replacement_map

    # forward → reverse 双向自洽：lookup 的每个返回值都应在 origins 中包含原词
    for word, replacements in rmap.forward.items():
        assert replacements, f"{word!r} forward replacements 不应为空"
        for rep in replacements:
            origins = rmap.origins(rep)
            assert word in origins, (
                f"reverse 失配：{rep!r} 反查没拿到原词 {word!r}（实测 origins={origins}）"
            )

    # 反查不存在的词返回空 tuple
    assert rmap.lookup("根本不存在的词xx") == ()
    assert rmap.origins("根本不存在的词xx") == ()


def test_replacement_map_origins_groups_synonyms() -> None:
    """单一爆款替换可被多个原词共用：盯着 ← 凝视 + 凝望 + 凝眸。"""
    rmap = load_blacklist().replacement_map
    paying_attention = rmap.origins("盯着")
    # PRD US-002 设计意图：不同装逼词共享同一爆款替换，反查能拿到全部源
    assert "凝视" in paying_attention, "盯着 反查应含 凝视"
    assert len(paying_attention) >= 2, (
        f"盯着 反查至少应 ≥2 个原词（核心爆款替换被多个装逼词共用），实测 {paying_attention}"
    )


def test_replacement_map_words_preserves_yaml_order() -> None:
    """forward.keys() 顺序必须与 YAML 一致（polish-agent 取首项有约定意义）。"""
    rmap = load_blacklist().replacement_map
    words = rmap.words()
    # 首条按 YAML 应是 凝视（rmap section 第一行）
    assert words[0] == "凝视", f"replacement_map 首键应是 凝视，实测 {words[0]!r}"


def test_replacement_map_first_replacement_is_polish_default() -> None:
    """polish-agent simplification_pass 默认取首项；首项必须是最爆款的那个。"""
    rmap = load_blacklist().replacement_map
    # 设计上"首项 = 最爆款"。这里抽样锚定，避免后续误改顺序
    assert rmap.lookup("凝视")[0] == "盯着"
    assert rmap.lookup("缓缓")[0] == "慢慢"
    assert rmap.lookup("宿命")[0] == "命"


# ---------------------------------------------------------------------------
# Custom-path 解析鲁棒性（mirror existing loader 风格）
# ---------------------------------------------------------------------------


def test_load_pretentious_custom_path_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "bl.yaml"
    _write_yaml(
        target,
        {
            "version": 2,
            "pretentious_verbs": [
                {"word": "凝视", "replacement": "盯着"},
                {"word": "伫立", "replacement": "站着"},
            ],
            "pretentious_nouns": [{"word": "宿命", "replacement": "命"}],
            "pretentious_adverbs": [{"word": "缓缓", "replacement": "慢慢"}],
            "replacement_map": {
                "凝视": ["盯着", "看着"],
                "伫立": ["站着"],
                "缓缓": ["慢慢"],
            },
        },
    )
    bundle = load_blacklist(target)
    assert [e.word for e in bundle.pretentious_verbs] == ["凝视", "伫立"]
    assert bundle.replacement_map.lookup("凝视") == ("盯着", "看着")
    assert bundle.replacement_map.origins("看着") == ("凝视",)
    assert bundle.replacement_map.origins("站着") == ("伫立",)


def test_replacement_map_handles_string_value(tmp_path: Path) -> None:
    """单字符串值合法：value 是 str 时视为单元素列表。"""
    target = tmp_path / "bl.yaml"
    _write_yaml(target, {"version": 2, "replacement_map": {"凝视": "盯着"}})
    rmap = load_blacklist(target).replacement_map
    assert rmap.lookup("凝视") == ("盯着",)
    assert rmap.origins("盯着") == ("凝视",)


def test_replacement_map_drops_empty_or_invalid_values(tmp_path: Path) -> None:
    target = tmp_path / "bl.yaml"
    _write_yaml(
        target,
        {
            "version": 2,
            "replacement_map": {
                "凝视": ["盯着", "", None, "看着"],
                "空词": [],
                "": ["X"],  # 空 key 应丢弃
                "无效值": 42,  # 非 list/str
            },
        },
    )
    rmap = load_blacklist(target).replacement_map
    assert rmap.lookup("凝视") == ("盯着", "看着")
    assert rmap.lookup("空词") == ()
    assert "" not in rmap.forward
    assert "无效值" not in rmap.forward


def test_replacement_map_non_dict_section_returns_empty(tmp_path: Path) -> None:
    """replacement_map 不是 dict 时 → 空 ReplacementMap，不抛异常。"""
    target = tmp_path / "bl.yaml"
    _write_yaml(target, {"version": 2, "replacement_map": ["not", "a", "dict"]})
    rmap = load_blacklist(target).replacement_map
    assert isinstance(rmap, ReplacementMap)
    assert len(rmap) == 0


def test_replacement_map_missing_section_returns_empty(tmp_path: Path) -> None:
    target = tmp_path / "bl.yaml"
    _write_yaml(target, {"version": 2, "abstract_adjectives": [{"word": "莫名", "replacement": "x"}]})
    rmap = load_blacklist(target).replacement_map
    assert isinstance(rmap, ReplacementMap)
    assert len(rmap) == 0
    assert not rmap


# ---------------------------------------------------------------------------
# 公开 API 完备性
# ---------------------------------------------------------------------------


def test_module_exposes_us002_public_api() -> None:
    exported = set(dir(blacklist_loader))
    required = {
        "ReplacementMap",
        "load_pretentious_verbs",
        "load_pretentious_nouns",
        "load_pretentious_adverbs",
        "load_replacement_map",
    }
    missing = required - exported
    assert not missing, f"loader 缺公开符号：{missing}"


def test_categories_constant_includes_three_new_domains() -> None:
    from ink_writer.prose.blacklist_loader import CATEGORIES
    for cat in ("pretentious_verbs", "pretentious_nouns", "pretentious_adverbs"):
        assert cat in CATEGORIES, f"CATEGORIES 应含 {cat}"


def test_blacklist_match_includes_new_categories() -> None:
    """``Blacklist.match()`` 现在能命中三域装逼词。"""
    bundle = load_blacklist()
    sample = "他凝视着远方的苍茫大地，缓缓抬手。"
    hits = bundle.match(sample)
    categories_hit = {entry.category for entry, _ in hits}
    assert "pretentious_verbs" in categories_hit
    assert "pretentious_nouns" in categories_hit
    assert "pretentious_adverbs" in categories_hit


# ---------------------------------------------------------------------------
# ReplacementMap 数据类基本契约
# ---------------------------------------------------------------------------


def test_replacement_map_default_is_empty() -> None:
    rm = ReplacementMap()
    assert len(rm) == 0
    assert not rm
    assert rm.lookup("anything") == ()
    assert rm.origins("anything") == ()
    assert rm.words() == ()


def test_replacement_map_equality() -> None:
    a = ReplacementMap(forward={"x": ("y",)}, reverse={"y": ("x",)})
    b = ReplacementMap(forward={"x": ("y",)}, reverse={"y": ("x",)})
    c = ReplacementMap(forward={"x": ("z",)}, reverse={"z": ("x",)})
    assert a == b
    assert a != c
