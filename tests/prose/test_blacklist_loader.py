"""Tests for :mod:`ink_writer.prose.blacklist_loader` (US-003)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from ink_writer.prose import blacklist_loader
from ink_writer.prose.blacklist_loader import (
    CATEGORIES,
    DEFAULT_BLACKLIST_PATH,
    Blacklist,
    BlacklistEntry,
    clear_cache,
    load_blacklist,
)

yaml = pytest.importorskip("yaml")


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    clear_cache()


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Loader happy path
# ---------------------------------------------------------------------------


def test_load_shipped_blacklist_meets_prd_minima() -> None:
    """Ship-level YAML must clear the US-003 验收门槛：50/30/20，总 ≥100。"""
    bundle = load_blacklist()
    assert isinstance(bundle, Blacklist)
    assert bundle.version >= 1
    assert len(bundle.abstract_adjectives) >= 50
    assert len(bundle.empty_phrases) >= 30
    assert len(bundle.pretentious_metaphors) >= 20
    assert len(bundle.entries) >= 100

    # 每条都必须带替代示例——PRD 硬要求（showing 具体词）
    for entry in bundle.entries:
        assert entry.word, "word must be non-empty"
        assert entry.replacement, f"{entry.word!r} missing replacement hint"
        assert entry.category in CATEGORIES


def test_default_path_points_to_ink_writer_assets() -> None:
    """路径常量指向仓内 ink-writer/assets/prose-blacklist.yaml。"""
    assert DEFAULT_BLACKLIST_PATH.name == "prose-blacklist.yaml"
    assert DEFAULT_BLACKLIST_PATH.parent.name == "assets"
    assert DEFAULT_BLACKLIST_PATH.parent.parent.name == "ink-writer"
    assert DEFAULT_BLACKLIST_PATH.exists()


# ---------------------------------------------------------------------------
# Custom path + parsing variants
# ---------------------------------------------------------------------------


def test_load_parses_string_and_dict_entries(tmp_path: Path) -> None:
    target = tmp_path / "bl.yaml"
    _write_yaml(
        target,
        {
            "version": 1,
            "abstract_adjectives": [
                "莫名",  # 裸字符串：replacement 留空但 word 仍然生效
                {"word": "仿佛", "replacement": "删除或换具体动作"},
                {"word": "", "replacement": "空词应丢弃"},
                None,  # 非法项应忽略
                {"replacement": "只有 replacement 无 word 也应忽略"},
            ],
            "empty_phrases": [{"word": "此情此景", "replacement": "直接描写画面"}],
            "pretentious_metaphors": [{"word": "宛如…一般", "replacement": "具体动作类比"}],
        },
    )
    bundle = load_blacklist(target)
    assert [e.word for e in bundle.abstract_adjectives] == ["莫名", "仿佛"]
    assert bundle.abstract_adjectives[0].replacement == ""
    assert bundle.abstract_adjectives[1].replacement == "删除或换具体动作"
    assert [e.word for e in bundle.empty_phrases] == ["此情此景"]
    assert [e.word for e in bundle.pretentious_metaphors] == ["宛如…一般"]


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    bundle = load_blacklist(tmp_path / "nope.yaml")
    assert bundle == Blacklist(version=0, entries=())


def test_invalid_yaml_returns_empty(tmp_path: Path) -> None:
    target = tmp_path / "broken.yaml"
    target.write_text(": : : :\nnot: valid: yaml: ][", encoding="utf-8")
    bundle = load_blacklist(target)
    assert bundle.entries == ()
    assert bundle.version == 0


def test_non_mapping_root_returns_empty(tmp_path: Path) -> None:
    target = tmp_path / "list_root.yaml"
    target.write_text("- a\n- b\n", encoding="utf-8")
    assert load_blacklist(target).entries == ()


def test_unknown_section_is_ignored(tmp_path: Path) -> None:
    """未知 category 不应污染 entries。"""
    target = tmp_path / "extra.yaml"
    _write_yaml(
        target,
        {
            "version": 1,
            "abstract_adjectives": [{"word": "莫名", "replacement": "具体情绪"}],
            "future_category": [{"word": "未来", "replacement": "x"}],
        },
    )
    bundle = load_blacklist(target)
    assert [e.word for e in bundle.entries] == ["莫名"]


def test_non_list_section_is_skipped(tmp_path: Path) -> None:
    target = tmp_path / "bad_section.yaml"
    _write_yaml(target, {"version": 1, "abstract_adjectives": "not-a-list"})
    bundle = load_blacklist(target)
    assert bundle.entries == ()


# ---------------------------------------------------------------------------
# Hot reload behaviour
# ---------------------------------------------------------------------------


def test_reload_picks_up_mutations(tmp_path: Path) -> None:
    target = tmp_path / "bl.yaml"
    _write_yaml(
        target,
        {"version": 1, "abstract_adjectives": [{"word": "莫名", "replacement": "具体"}]},
    )
    first = load_blacklist(target)
    assert [e.word for e in first.entries] == ["莫名"]

    # 覆盖内容并把 mtime 往前推一秒——避开同一时钟刻度的冲突
    _write_yaml(
        target,
        {
            "version": 2,
            "abstract_adjectives": [{"word": "仿佛", "replacement": "删"}],
            "empty_phrases": [{"word": "此情此景", "replacement": "画面"}],
        },
    )
    future_ns = target.stat().st_mtime_ns + 1_000_000_000
    os.utime(target, ns=(future_ns, future_ns))

    second = load_blacklist(target)
    assert second.version == 2
    assert [e.word for e in second.entries] == ["仿佛", "此情此景"]


def test_repeat_load_hits_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """mtime 未变时第二次调用不应重新解析 YAML。"""
    target = tmp_path / "bl.yaml"
    _write_yaml(target, {"version": 1, "abstract_adjectives": [{"word": "莫名", "replacement": "x"}]})
    first = load_blacklist(target)

    import yaml as yaml_mod

    calls = {"n": 0}
    original = yaml_mod.safe_load

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(yaml_mod, "safe_load", spy)
    second = load_blacklist(target)
    assert calls["n"] == 0
    assert second is first


def test_clear_cache_forces_reparse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "bl.yaml"
    _write_yaml(target, {"version": 1, "abstract_adjectives": [{"word": "莫名", "replacement": "x"}]})
    load_blacklist(target)

    import yaml as yaml_mod

    calls = {"n": 0}
    original = yaml_mod.safe_load

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(yaml_mod, "safe_load", spy)
    clear_cache()
    load_blacklist(target)
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# Matching API
# ---------------------------------------------------------------------------


def _make(entries: list[tuple[str, str]]) -> Blacklist:
    """Build Blacklist in-memory for match-level tests (no YAML roundtrip)."""
    mapped = [
        BlacklistEntry(word=w, category=c, replacement="-") for w, c in entries
    ]
    return Blacklist(version=1, entries=tuple(mapped))


def test_match_hits_plain_substrings() -> None:
    bundle = _make(
        [
            ("莫名", "abstract_adjectives"),
            ("此情此景", "empty_phrases"),
            ("消失的词", "abstract_adjectives"),
        ]
    )
    hits = bundle.match("他看着她，心里莫名一紧。此情此景，莫名又涌上。")
    words = {e.word: n for e, n in hits}
    assert words == {"莫名": 2, "此情此景": 1}


def test_match_supports_wildcard_phrase() -> None:
    """`宛如…一般` 要命中两端同时出现的短语——任一缺失都不算。"""
    bundle = _make([("宛如…一般", "pretentious_metaphors")])

    hit = bundle.match("他宛如一尊石像一般立着")
    assert len(hit) == 1
    assert hit[0][1] == 1

    miss = bundle.match("他宛如一尊石像")  # 缺 "一般"
    assert miss == []


def test_match_on_clean_text_returns_empty() -> None:
    bundle = _make([("莫名", "abstract_adjectives"), ("此情此景", "empty_phrases")])
    assert bundle.match("他走到窗前，推开一扇窗。") == []


def test_words_api_flat_and_filtered() -> None:
    bundle = _make(
        [
            ("莫名", "abstract_adjectives"),
            ("此情此景", "empty_phrases"),
            ("宛如…一般", "pretentious_metaphors"),
        ]
    )
    assert set(bundle.words()) == {"莫名", "此情此景", "宛如…一般"}
    assert bundle.words("abstract_adjectives") == ("莫名",)
    assert bundle.words("pretentious_metaphors") == ("宛如…一般",)


def test_words_rejects_unknown_category() -> None:
    bundle = _make([("莫名", "abstract_adjectives")])
    with pytest.raises(ValueError, match="unknown category"):
        bundle.words("not_a_real_category")


# ---------------------------------------------------------------------------
# Integration: shipped YAML + match
# ---------------------------------------------------------------------------


def test_shipped_blacklist_catches_typical_ai_telling_prose() -> None:
    """网文 AI 味样本必须至少命中 3 类黑名单中的每一类。"""
    bundle = load_blacklist()
    sample = (
        "此情此景，他莫名一阵心悸，宛如被什么击中一般，"
        "脸上掠过一丝难以言喻的神色。空气仿佛凝固，"
        "时间仿佛静止了一个世纪。"
    )
    hits = bundle.match(sample)
    categories_hit = {entry.category for entry, _ in hits}
    assert {"abstract_adjectives", "empty_phrases", "pretentious_metaphors"} <= categories_hit


def test_loader_module_exposes_public_api() -> None:
    """__init__ 的公开名单应与文档一致。"""
    exported = set(dir(blacklist_loader))
    assert {"Blacklist", "BlacklistEntry", "load_blacklist", "clear_cache", "CATEGORIES"} <= exported
