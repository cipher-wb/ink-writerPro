"""Tests for mine_hook_patterns.py — schema validation, coverage, and correctness."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

from mine_hook_patterns import (
    CLIFF_PATTERNS,
    GENRE_HOOK_TEMPLATES,
    HOOK_TYPES,
    MID_PATTERNS,
    OPEN_PATTERNS,
    POSITION_TYPES,
    build_genre_patterns,
    deduplicate_to_patterns,
    mine_hook_patterns,
    save_patterns,
    scan_chapter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_CHAPTER_CLIFF = (
    "白天发生了很多事情，他心里很不安。\n" * 10
    + "究竟是谁在幕后操纵这一切？\n"
    + "然而，一切才刚刚开始。\n"
)

FIXTURE_CHAPTER_OPEN = (
    "砰！\n"
    "一声巨响从远处传来，震得窗户嗡嗡作响。\n"
    + "他匆忙从床上跳起来，四处张望了一番，确认没有危险之后才稍稍放松了下来。\n" * 8
    + "接下来的事情让人意想不到，他根本没有料到会发生这样的变故。\n" * 5
)

FIXTURE_CHAPTER_MID = (
    "清晨的阳光洒在院子里。\n" * 5
    + "不对！他突然脸色大变，一股杀意从身后涌来。\n"
    + "他猛然回头，看到了一双冰冷的眼睛。\n"
    + "普通的叙述继续着。\n" * 10
    + "故事在平静中结束了。\n"
)


@pytest.fixture()
def fixture_corpus(tmp_path: Path) -> Path:
    """Build a minimal fixture corpus for testing."""
    book_dir = tmp_path / "test_book"
    ch_dir = book_dir / "chapters"
    ch_dir.mkdir(parents=True)

    manifest = {
        "book_id": "test001",
        "title": "测试小说",
        "author": "测试作者",
        "source": "test",
        "genre": "玄幻",
        "chapters_count": 3,
        "license_note": "test fixture",
    }
    (book_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    (ch_dir / "ch001.txt").write_text(FIXTURE_CHAPTER_OPEN, encoding="utf-8")
    (ch_dir / "ch002.txt").write_text(FIXTURE_CHAPTER_MID, encoding="utf-8")
    (ch_dir / "ch003.txt").write_text(FIXTURE_CHAPTER_CLIFF, encoding="utf-8")

    return tmp_path


# ---------------------------------------------------------------------------
# Pattern definition tests
# ---------------------------------------------------------------------------


class TestPatternDefinitions:
    def test_cliff_patterns_nonempty(self):
        assert len(CLIFF_PATTERNS) > 0

    def test_open_patterns_nonempty(self):
        assert len(OPEN_PATTERNS) > 0

    def test_mid_patterns_nonempty(self):
        assert len(MID_PATTERNS) > 0

    def test_all_cliff_types_valid(self):
        for regex, hook_type, pw, desc in CLIFF_PATTERNS:
            assert hook_type in HOOK_TYPES, f"Invalid type '{hook_type}' in cliff pattern: {desc}"
            assert pw >= 1
            re.compile(regex)

    def test_all_open_types_valid(self):
        for regex, hook_type, pw, desc in OPEN_PATTERNS:
            assert hook_type in HOOK_TYPES, f"Invalid type '{hook_type}' in open pattern: {desc}"
            assert pw >= 1
            re.compile(regex)

    def test_all_mid_types_valid(self):
        for regex, hook_type, pw, desc in MID_PATTERNS:
            assert hook_type in HOOK_TYPES, f"Invalid type '{hook_type}' in mid pattern: {desc}"
            assert pw >= 1
            re.compile(regex)

    def test_all_regexes_compile(self):
        all_patterns = CLIFF_PATTERNS + OPEN_PATTERNS + MID_PATTERNS
        for regex, _, _, desc in all_patterns:
            try:
                re.compile(regex)
            except re.error as e:
                pytest.fail(f"Regex failed for '{desc}': {regex} → {e}")

    def test_genre_templates_cover_all_types(self):
        for genre, templates in GENRE_HOOK_TEMPLATES.items():
            types_seen = {t["type"] for t in templates}
            assert len(types_seen) >= 3, f"Genre '{genre}' covers too few types: {types_seen}"


# ---------------------------------------------------------------------------
# scan_chapter tests
# ---------------------------------------------------------------------------


class TestScanChapter:
    def test_cliff_chapter_finds_hooks(self):
        results = scan_chapter(FIXTURE_CHAPTER_CLIFF, 3, "测试小说")
        cliff_results = [r for r in results if r["position"] == "cliff"]
        assert len(cliff_results) > 0

    def test_open_chapter_finds_hooks(self):
        results = scan_chapter(FIXTURE_CHAPTER_OPEN, 1, "测试小说")
        open_results = [r for r in results if r["position"] == "open"]
        assert len(open_results) > 0

    def test_mid_chapter_finds_hooks(self):
        results = scan_chapter(FIXTURE_CHAPTER_MID, 2, "测试小说")
        mid_results = [r for r in results if r["position"] == "mid"]
        assert len(mid_results) > 0

    def test_empty_text_returns_empty(self):
        results = scan_chapter("", 1, "空")
        assert results == []

    def test_result_schema(self):
        results = scan_chapter(FIXTURE_CHAPTER_CLIFF, 1, "测试")
        required_keys = {
            "regex", "hook_type", "position", "payoff_window_chapters",
            "description", "matched_text", "snippet", "source_ref",
        }
        for r in results:
            assert required_keys.issubset(r.keys()), f"Missing keys: {required_keys - r.keys()}"
            assert r["hook_type"] in HOOK_TYPES
            assert r["position"] in POSITION_TYPES

    def test_source_ref_format(self):
        results = scan_chapter(FIXTURE_CHAPTER_CLIFF, 5, "我的小说")
        for r in results:
            assert r["source_ref"] == "我的小说/ch005"


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------


class TestDeduplication:
    def test_dedup_merges_same_pattern(self):
        raw = [
            {
                "regex": r"突然[，,]", "hook_type": "crisis", "position": "cliff",
                "payoff_window_chapters": 1, "description": "突然转折",
                "matched_text": "突然，", "snippet": "突然，发生了",
                "source_ref": "book1/ch001",
            },
            {
                "regex": r"突然[，,]", "hook_type": "crisis", "position": "cliff",
                "payoff_window_chapters": 1, "description": "突然转折",
                "matched_text": "突然,", "snippet": "突然,来了",
                "source_ref": "book2/ch005",
            },
        ]
        patterns = deduplicate_to_patterns(raw)
        assert len(patterns) == 1
        assert patterns[0]["example_count"] == 2

    def test_dedup_keeps_different_patterns(self):
        raw = [
            {
                "regex": r"突然[，,]", "hook_type": "crisis", "position": "cliff",
                "payoff_window_chapters": 1, "description": "突然转折",
                "matched_text": "突然，", "snippet": "s1",
                "source_ref": "b1/ch001",
            },
            {
                "regex": r"不可能[！!]", "hook_type": "crisis", "position": "cliff",
                "payoff_window_chapters": 1, "description": "不可能",
                "matched_text": "不可能！", "snippet": "s2",
                "source_ref": "b1/ch002",
            },
        ]
        patterns = deduplicate_to_patterns(raw)
        assert len(patterns) == 2

    def test_dedup_limits_examples(self):
        raw = [
            {
                "regex": r"x", "hook_type": "crisis", "position": "cliff",
                "payoff_window_chapters": 1, "description": "test",
                "matched_text": f"x{i}", "snippet": f"s{i}",
                "source_ref": f"b/ch{i:03d}",
            }
            for i in range(10)
        ]
        patterns = deduplicate_to_patterns(raw)
        assert len(patterns) == 1
        assert len(patterns[0]["examples"]) <= 3
        assert len(patterns[0]["source_refs"]) <= 5


# ---------------------------------------------------------------------------
# Genre patterns tests
# ---------------------------------------------------------------------------


class TestGenrePatterns:
    def test_genre_patterns_nonempty(self):
        patterns = build_genre_patterns()
        assert len(patterns) > 0

    def test_genre_pattern_schema(self):
        required_keys = {
            "id", "type", "position", "trigger_template",
            "trigger_description", "payoff_window_chapters", "genre",
        }
        for p in build_genre_patterns():
            assert required_keys.issubset(p.keys()), f"Missing: {required_keys - p.keys()}"
            assert p["type"] in HOOK_TYPES


# ---------------------------------------------------------------------------
# Full pipeline tests (fixture corpus)
# ---------------------------------------------------------------------------


class TestMinePipeline:
    def test_mine_on_fixture(self, fixture_corpus: Path):
        data = mine_hook_patterns(corpus_dir=fixture_corpus, max_chapters_per_book=3)
        assert data["stats"]["total_patterns"] >= 1
        assert data["stats"]["books_scanned"] == 1
        assert data["stats"]["chapters_scanned"] == 3

    def test_output_schema(self, fixture_corpus: Path):
        data = mine_hook_patterns(corpus_dir=fixture_corpus)
        assert "version" in data
        assert "stats" in data
        assert "patterns" in data
        assert isinstance(data["patterns"], list)

        for p in data["patterns"]:
            assert "id" in p
            assert "type" in p
            assert p["type"] in HOOK_TYPES
            assert "position" in p
            assert "trigger_template" in p
            assert "payoff_window_chapters" in p

    def test_every_type_has_patterns(self, fixture_corpus: Path):
        data = mine_hook_patterns(corpus_dir=fixture_corpus)
        types_seen = {p["type"] for p in data["patterns"]}
        for ht in HOOK_TYPES:
            assert ht in types_seen, f"No patterns for type '{ht}'"

    def test_save_and_load(self, fixture_corpus: Path, tmp_path: Path):
        data = mine_hook_patterns(corpus_dir=fixture_corpus)
        out = tmp_path / "out" / "hook_patterns.json"
        save_patterns(data, out)

        assert out.exists()
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["stats"]["total_patterns"] == data["stats"]["total_patterns"]

    def test_corpus_not_found_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            mine_hook_patterns(corpus_dir=tmp_path / "nonexistent")


# ---------------------------------------------------------------------------
# Live corpus test (skipped if no reference corpus)
# ---------------------------------------------------------------------------

LIVE_CORPUS = Path(__file__).resolve().parents[2] / "benchmark" / "reference_corpus"


@pytest.mark.skipif(
    not LIVE_CORPUS.exists(),
    reason="Live reference corpus not available",
)
class TestLiveCorpus:
    def test_live_mine_produces_200_plus(self):
        data = mine_hook_patterns(corpus_dir=LIVE_CORPUS)
        assert data["stats"]["total_patterns"] >= 200

    def test_live_all_types_present(self):
        data = mine_hook_patterns(corpus_dir=LIVE_CORPUS)
        types_seen = {p["type"] for p in data["patterns"]}
        for ht in HOOK_TYPES:
            assert ht in types_seen

    def test_live_all_positions_present(self):
        data = mine_hook_patterns(corpus_dir=LIVE_CORPUS)
        positions_seen = {p["position"] for p in data["patterns"]}
        for pos in POSITION_TYPES:
            assert pos in positions_seen

    def test_live_pattern_ids_unique(self):
        data = mine_hook_patterns(corpus_dir=LIVE_CORPUS)
        ids = [p["id"] for p in data["patterns"]]
        assert len(ids) == len(set(ids)), "Duplicate pattern IDs found"

    def test_live_nonempty_per_type(self):
        data = mine_hook_patterns(corpus_dir=LIVE_CORPUS)
        by_type = data["stats"]["by_type"]
        for ht in HOOK_TYPES:
            assert by_type.get(ht, 0) > 0, f"Type '{ht}' has 0 patterns"
