#!/usr/bin/env python3
"""Tests for scripts/build_reference_corpus.py — validates corpus building, stats, and manifests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# [FIX-11] removed: sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_reference_corpus import (
    analyze_book,
    analyze_chapter_high_points,
    analyze_chapter_hooks,
    build_manifest,
    build_reference_corpus,
    compute_percentiles,
    load_corpus_index,
    select_top_books,
)

BENCHMARK_DIR = REPO_ROOT / "benchmark"
REFERENCE_DIR = BENCHMARK_DIR / "reference_corpus"
REFERENCE_STATS = BENCHMARK_DIR / "reference_stats.json"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_corpus(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal fake corpus for unit tests."""
    corpus_dir = tmp_path / "corpus"
    index_path = tmp_path / "corpus_index.json"

    books = []
    for i in range(35):
        title = f"test_book_{i:03d}"
        book_dir = corpus_dir / title / "chapters"
        book_dir.mkdir(parents=True)

        for ch in range(1, 16):
            text = (
                f"第{ch}章 开头\n"
                "一些正文内容，主角突破了境界，终于成功了！\n"
                "全场震惊，不可能！\n"
                "他碾压了对手，一战成名。\n"
                "然而，下一刻，一道黑影突然出现。\n"
                "究竟发生了什么？\n"
            ) * 10
            (book_dir / f"ch{ch:03d}.txt").write_text(text, encoding="utf-8")

        books.append({
            "book_id": str(1000 + i),
            "title": title,
            "author": f"author_{i}",
            "genre": "玄幻" if i % 2 == 0 else "都市",
            "word_count": 1000000 + i * 10000,
            "collections": 500000 - i * 1000,
            "chapter_count": 15,
            "dir": title,
        })

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(books, f, ensure_ascii=False)

    return index_path, corpus_dir


@pytest.fixture
def hook_text_strong() -> str:
    return (
        "正文内容\n" * 20
        + "突然，一道身影出现。\n"
        + "究竟是谁？\n"
        + "难道是他？\n"
        + "不可能！\n"
    )


@pytest.fixture
def hook_text_weak() -> str:
    return "这是一段普通的叙事。\n" * 30


@pytest.fixture
def high_point_text() -> str:
    return "主角终于突破了，全场震惊，碾压对手，一战成名，觉醒了真正的力量。" * 5


@pytest.fixture
def flat_text() -> str:
    return "他慢慢走在路上，看着远方的天空。天气不错，微风拂面。" * 20


# ---------------------------------------------------------------------------
# Unit tests: analyze functions
# ---------------------------------------------------------------------------

class TestAnalyzeChapterHooks:
    def test_strong_ending_hooks(self, hook_text_strong: str) -> None:
        result = analyze_chapter_hooks(hook_text_strong)
        assert result["end_hooks"] >= 2

    def test_weak_ending_hooks(self, hook_text_weak: str) -> None:
        result = analyze_chapter_hooks(hook_text_weak)
        assert result["end_hooks"] == 0

    def test_opening_hooks(self) -> None:
        text = "痛！\n好痛！\n砰的一声。\n" + "正文\n" * 30
        result = analyze_chapter_hooks(text, is_opening=True)
        assert result["open_hooks"] >= 1

    def test_empty_text(self) -> None:
        result = analyze_chapter_hooks("")
        assert result["end_hooks"] == 0
        assert result["open_hooks"] == 0


class TestAnalyzeChapterHighPoints:
    def test_high_density(self, high_point_text: str) -> None:
        result = analyze_chapter_high_points(high_point_text)
        assert result["high_point_count"] > 0
        assert result["high_point_density"] > 0.0

    def test_flat_chapter(self, flat_text: str) -> None:
        result = analyze_chapter_high_points(flat_text)
        assert result["high_point_density"] < 1.0

    def test_empty_text(self) -> None:
        result = analyze_chapter_high_points("")
        assert result["high_point_count"] == 0
        assert result["high_point_density"] == 0.0


class TestComputePercentiles:
    def test_basic(self) -> None:
        values = list(range(1, 101))
        result = compute_percentiles(values)
        assert result["p25"] == pytest.approx(25.75, abs=0.5)
        assert result["p50"] == pytest.approx(50.5, abs=0.5)
        assert result["p75"] == pytest.approx(75.25, abs=0.5)
        assert result["min"] == 1.0
        assert result["max"] == 100.0

    def test_empty(self) -> None:
        result = compute_percentiles([])
        assert result["p25"] == 0.0
        assert result["p50"] == 0.0
        assert result["p75"] == 0.0

    def test_single(self) -> None:
        result = compute_percentiles([42.0])
        assert result["p25"] == 42.0
        assert result["p50"] == 42.0
        assert result["p75"] == 42.0
        assert result["min"] == 42.0
        assert result["max"] == 42.0

    def test_keys_present(self) -> None:
        result = compute_percentiles([1.0, 2.0, 3.0])
        for key in ("p25", "p50", "p75", "min", "max", "mean"):
            assert key in result


class TestSelectTopBooks:
    def test_selects_by_collections(self) -> None:
        books = [
            {"title": "A", "collections": 100, "chapter_count": 15},
            {"title": "B", "collections": 500, "chapter_count": 15},
            {"title": "C", "collections": 300, "chapter_count": 15},
        ]
        result = select_top_books(books, top_n=2, min_chapters=10)
        assert len(result) == 2
        assert result[0]["title"] == "B"
        assert result[1]["title"] == "C"

    def test_filters_low_chapters(self) -> None:
        books = [
            {"title": "A", "collections": 1000, "chapter_count": 5},
            {"title": "B", "collections": 500, "chapter_count": 15},
        ]
        result = select_top_books(books, top_n=10, min_chapters=10)
        assert len(result) == 1
        assert result[0]["title"] == "B"

    def test_empty(self) -> None:
        assert select_top_books([], top_n=10, min_chapters=5) == []


class TestBuildManifest:
    def test_required_fields(self) -> None:
        book = {
            "book_id": "12345",
            "title": "Test",
            "author": "Author",
            "genre": "玄幻",
            "chapter_count": 30,
            "collections": 100000,
        }
        manifest = build_manifest(book)
        for key in ("book_id", "title", "author", "source", "genre",
                     "chapters_count", "license_note"):
            assert key in manifest
        assert manifest["source"] == "qidian_public_chapters"
        assert "公开" in manifest["license_note"]


# ---------------------------------------------------------------------------
# Integration tests: build_reference_corpus with fake data
# ---------------------------------------------------------------------------

class TestBuildReferenceCorpus:
    def test_builds_with_fake_corpus(self, sample_corpus: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
        index_path, corpus_dir = sample_corpus
        ref_dir = corpus_dir.parent / "reference_corpus"
        stats_path = corpus_dir.parent / "reference_stats.json"

        import build_reference_corpus as mod
        monkeypatch.setattr(mod, "CORPUS_INDEX", index_path)
        monkeypatch.setattr(mod, "CORPUS_DIR", corpus_dir)
        monkeypatch.setattr(mod, "REFERENCE_DIR", ref_dir)
        monkeypatch.setattr(mod, "REFERENCE_STATS", stats_path)

        stats = build_reference_corpus(top_n=35, min_chapters=5)

        assert stats["corpus_size"] >= 30
        assert stats["books_analyzed"] >= 30
        assert stats_path.exists()

        loaded = json.loads(stats_path.read_text(encoding="utf-8"))
        assert "hook_density" in loaded
        assert "high_point_density" in loaded
        assert "per_book" in loaded
        assert loaded["hook_density"]["p75"] > 0
        assert loaded["high_point_density"]["p75"] > 0

    def test_manifests_created(self, sample_corpus: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
        index_path, corpus_dir = sample_corpus
        ref_dir = corpus_dir.parent / "reference_corpus"
        stats_path = corpus_dir.parent / "reference_stats.json"

        import build_reference_corpus as mod
        monkeypatch.setattr(mod, "CORPUS_INDEX", index_path)
        monkeypatch.setattr(mod, "CORPUS_DIR", corpus_dir)
        monkeypatch.setattr(mod, "REFERENCE_DIR", ref_dir)
        monkeypatch.setattr(mod, "REFERENCE_STATS", stats_path)

        build_reference_corpus(top_n=35, min_chapters=5)

        manifest_count = 0
        for book_dir in ref_dir.iterdir():
            if book_dir.is_dir():
                mf = book_dir / "manifest.json"
                if mf.exists():
                    manifest_count += 1
                    data = json.loads(mf.read_text(encoding="utf-8"))
                    assert "source" in data
                    assert "license_note" in data
                    assert "genre" in data
        assert manifest_count >= 30

    def test_stats_schema(self, sample_corpus: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
        index_path, corpus_dir = sample_corpus
        ref_dir = corpus_dir.parent / "reference_corpus"
        stats_path = corpus_dir.parent / "reference_stats.json"

        import build_reference_corpus as mod
        monkeypatch.setattr(mod, "CORPUS_INDEX", index_path)
        monkeypatch.setattr(mod, "CORPUS_DIR", corpus_dir)
        monkeypatch.setattr(mod, "REFERENCE_DIR", ref_dir)
        monkeypatch.setattr(mod, "REFERENCE_STATS", stats_path)

        stats = build_reference_corpus(top_n=35, min_chapters=5)

        required_top = {"version", "timestamp", "corpus_size", "books_analyzed",
                        "hook_density", "high_point_density", "per_book"}
        assert required_top.issubset(set(stats.keys()))

        for metric_key in ("hook_density", "high_point_density"):
            metric = stats[metric_key]
            for pct in ("p25", "p50", "p75", "min", "max", "mean"):
                assert pct in metric
                assert isinstance(metric[pct], (int, float))

    def test_too_few_books_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        index_path = tmp_path / "corpus_index.json"
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump([
                {"book_id": "1", "title": "A", "author": "x", "genre": "玄幻",
                 "collections": 100, "chapter_count": 5, "dir": "a"}
            ], f)

        import build_reference_corpus as mod
        monkeypatch.setattr(mod, "CORPUS_INDEX", index_path)

        with pytest.raises(ValueError, match="need ≥30"):
            build_reference_corpus(top_n=50, min_chapters=5)

    def test_missing_index_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import build_reference_corpus as mod
        monkeypatch.setattr(mod, "CORPUS_INDEX", tmp_path / "nonexistent.json")

        with pytest.raises(FileNotFoundError):
            build_reference_corpus()


# ---------------------------------------------------------------------------
# Live corpus validation (skipped if no real corpus)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not REFERENCE_DIR.exists() or not any(REFERENCE_DIR.iterdir()),
    reason="Reference corpus not yet built",
)
class TestLiveReferenceCorpus:
    def test_at_least_30_books(self) -> None:
        book_dirs = [d for d in REFERENCE_DIR.iterdir() if d.is_dir()]
        assert len(book_dirs) >= 30

    def test_all_have_manifest(self) -> None:
        for book_dir in REFERENCE_DIR.iterdir():
            if book_dir.is_dir():
                assert (book_dir / "manifest.json").exists(), f"Missing manifest: {book_dir.name}"

    def test_stats_file_valid(self) -> None:
        assert REFERENCE_STATS.exists()
        data = json.loads(REFERENCE_STATS.read_text(encoding="utf-8"))
        assert data["corpus_size"] >= 30
        assert data["hook_density"]["p75"] > 0
        assert data["high_point_density"]["p75"] > 0
