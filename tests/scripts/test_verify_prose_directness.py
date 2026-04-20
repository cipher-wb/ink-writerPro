"""US-011 verification harness unit tests (scripts/verify_prose_directness.py).

Exercises helpers without running the full benchmark corpus scan (which is
heavy — ~15s on CI due to jieba.posseg). Full end-to-end is covered by a
single opt-in smoke test that runs only when the corpus is present.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import verify_prose_directness as vpd  # noqa: E402

# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------


class TestConstants:
    def test_direct_rhetoric_groups_disjoint_and_size_5(self) -> None:
        assert len(vpd.DIRECT_TOP5) == 5
        assert len(vpd.RHETORIC_TOP5) == 5
        assert not set(vpd.DIRECT_TOP5) & set(vpd.RHETORIC_TOP5)

    def test_benchmark_constants_positive(self) -> None:
        assert vpd.BENCHMARK_SENT_LEN_P50 > 0
        assert vpd.BENCHMARK_SENT_LEN_P25 <= vpd.BENCHMARK_SENT_LEN_P50
        assert vpd.BENCHMARK_SENT_LEN_P50 <= vpd.BENCHMARK_SENT_LEN_P75

    def test_ai_heavy_fixture_has_3_paragraphs_and_blacklist_hits(self) -> None:
        """Fixture must keep its engineered shape (3 paras separated by \\n\\n)."""
        assert vpd.AI_HEAVY_FIXTURE.count("\n\n") == 2

        from ink_writer.prose.blacklist_loader import load_blacklist

        hits = sum(cnt for _e, cnt in load_blacklist().match(vpd.AI_HEAVY_FIXTURE))
        assert hits >= 10, f"fixture should trigger ≥10 blacklist hits, got {hits}"


# ---------------------------------------------------------------------------
# M-1 simplification reduction
# ---------------------------------------------------------------------------


class TestM1WordReduction:
    def test_default_fixture_reduces_at_least_20pct(self) -> None:
        result = vpd.measure_m1_word_reduction()
        assert result["passed"] is True
        assert result["reduction_ratio"] >= 0.20
        assert result["blacklist_hits_before"] > result["blacklist_hits_after"]
        assert result["rolled_back"] is False
        assert "blacklist_abstract_drop" in result["rules_fired"]

    def test_tiny_clean_text_reports_no_reduction(self) -> None:
        """A clean short text → reduction_ratio 0, not rolled back, passed=False."""
        result = vpd.measure_m1_word_reduction(fixture_text="他笑了一声。")
        assert result["passed"] is False
        assert result["reduction_ratio"] == 0.0
        assert result["blacklist_hits_before"] == 0


# ---------------------------------------------------------------------------
# M-2 / M-3 / M-4 aggregation helpers (operate on ChapterMetrics fixtures)
# ---------------------------------------------------------------------------


def _mk_metric(
    book: str = "book",
    ch: int = 1,
    *,
    overall: float = 9.0,
    d1: float = 10.0,
    d2: float = 9.5,
    d3: float = 9.0,
    d4_score: float = 8.5,
    d5: float = 9.5,
    sent_len_median: float = 15.0,
    hits: int = 2,
    severity: str = "green",
) -> vpd.ChapterMetrics:
    return vpd.ChapterMetrics(
        book=book,
        chapter_no=ch,
        scene_mode="golden_three",
        char_count=3000,
        overall_score=overall,
        severity=severity,
        dimensions=[
            {"key": "D1_rhetoric_density", "score": d1, "value": 0.02, "rating": "green",
             "direction": "lower_is_better"},
            {"key": "D2_adj_verb_ratio", "score": d2, "value": 0.15, "rating": "green",
             "direction": "lower_is_better"},
            {"key": "D3_abstract_per_100_chars", "score": d3, "value": 0.07, "rating": "green",
             "direction": "lower_is_better"},
            {"key": "D4_sent_len_median", "score": d4_score, "value": sent_len_median,
             "rating": "green", "direction": "mid_is_better"},
            {"key": "D5_empty_paragraphs", "score": d5, "value": 40, "rating": "green",
             "direction": "lower_is_better"},
        ],
        raw_metrics={
            "D1_rhetoric_density": 0.02,
            "D2_adj_verb_ratio": 0.15,
            "D3_abstract_per_100_chars": 0.07,
            "D4_sent_len_median": sent_len_median,
            "D5_empty_paragraphs": 40,
        },
        blacklist_hits=hits,
    )


class TestM2DirectnessAvg:
    def test_passes_when_overall_avg_ge_8(self) -> None:
        scores = [_mk_metric(overall=9.33), _mk_metric(overall=8.5), _mk_metric(overall=8.0)]
        result = vpd.measure_m2_directness_avg(scores)
        assert result["passed"] is True
        assert result["overall_avg"] >= 8.0
        assert result["sample_size"] == 3
        assert set(result["avg_by_dim"].keys()) == set(vpd._ABSOLUTE_METRIC_KEYS)

    def test_fails_when_overall_avg_below_8(self) -> None:
        scores = [_mk_metric(overall=5.0), _mk_metric(overall=6.0)]
        result = vpd.measure_m2_directness_avg(scores)
        assert result["passed"] is False

    def test_empty_input_returns_not_passed(self) -> None:
        result = vpd.measure_m2_directness_avg([])
        assert result["passed"] is False
        assert "reason" in result


class TestM3BlacklistHits:
    def test_passes_when_median_le_3(self) -> None:
        scores = [_mk_metric(hits=0), _mk_metric(hits=2), _mk_metric(hits=3), _mk_metric(hits=5)]
        result = vpd.measure_m3_blacklist_hits(scores)
        assert result["passed"] is True
        assert result["median_hits"] <= 3

    def test_fails_when_median_above_3(self) -> None:
        scores = [_mk_metric(hits=5), _mk_metric(hits=7), _mk_metric(hits=9)]
        result = vpd.measure_m3_blacklist_hits(scores)
        assert result["passed"] is False

    def test_empty_input_returns_not_passed(self) -> None:
        result = vpd.measure_m3_blacklist_hits([])
        assert result["passed"] is False


class TestM4SentLenAlignment:
    def test_passes_in_p25_p75_band(self) -> None:
        scores = [
            _mk_metric(sent_len_median=14.0),
            _mk_metric(sent_len_median=15.0),
            _mk_metric(sent_len_median=16.0),
        ]
        result = vpd.measure_m4_sent_len_alignment(scores)
        assert result["passed"] is True
        assert result["band_low"] == pytest.approx(vpd.BENCHMARK_SENT_LEN_P25, abs=0.01)
        assert result["band_high"] == pytest.approx(vpd.BENCHMARK_SENT_LEN_P75, abs=0.01)

    def test_fails_when_group_median_outside_band(self) -> None:
        scores = [_mk_metric(sent_len_median=25.0)] * 5
        result = vpd.measure_m4_sent_len_alignment(scores)
        assert result["passed"] is False

    def test_empty_input_returns_not_passed(self) -> None:
        result = vpd.measure_m4_sent_len_alignment([])
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# M-5 / M-6 / M-7
# ---------------------------------------------------------------------------


class TestM5Methodology:
    def test_returns_informational_payload(self) -> None:
        result = vpd.measure_m5_methodology()
        assert result["passed"] is None  # 非阻断
        assert result["status"] == "deferred_to_live_run"
        assert "methodology" in result
        assert result["target"] == 0.40


class TestM6SensoryRegression:
    def test_slow_build_retains_sensory_directness_filters(self) -> None:
        """Verify US-007 zero-regression guarantee programmatically."""
        result = vpd.measure_m6_sensory_regression()
        assert result["passed"] is True
        assert result["directness_scene_filtered"] is True
        assert result["slow_build_scene_retained"] is True
        assert result["default_kwargs_retained"] is True


class TestM7SimplicityRecall:
    def test_rules_json_has_simplicity_floor(self) -> None:
        result = vpd.measure_m7_simplicity_recall()
        assert result["passed"] is True
        assert result["simplicity_rules_total"] >= 12
        assert result["recall_floor"] == 5

    def test_missing_rules_json_returns_not_passed(self, tmp_path: Path) -> None:
        result = vpd.measure_m7_simplicity_recall(
            rules_json_path=tmp_path / "nonexistent.json"
        )
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# score_chapter / group helpers
# ---------------------------------------------------------------------------


class TestScoreChapter:
    def test_returns_full_metrics_bundle(self) -> None:
        text = "他推开门走进屋里。外面下着雨。她坐在桌前，抬头看他。"
        cm = vpd.score_chapter(
            text, book="test-book", chapter_no=1, scene_mode="golden_three"
        )
        assert cm.book == "test-book"
        assert cm.chapter_no == 1
        assert cm.severity in {"green", "yellow", "red"}
        assert cm.char_count > 0
        assert len(cm.dimensions) == 5
        assert set(cm.dim_scores().keys()) == set(vpd._ABSOLUTE_METRIC_KEYS)
        assert cm.blacklist_hits >= 0


class TestLoadChapterText:
    def test_missing_book_returns_none(self, tmp_path: Path) -> None:
        assert (
            vpd.load_chapter_text(
                "nonexistent-book", 1, corpus_root=tmp_path
            )
            is None
        )

    def test_round_trip_through_synthetic_corpus(self, tmp_path: Path) -> None:
        book_dir = tmp_path / "我的测试书" / "chapters"
        book_dir.mkdir(parents=True)
        (book_dir / "ch001.txt").write_text("测试正文。", encoding="utf-8")
        text = vpd.load_chapter_text("我的测试书", 1, corpus_root=tmp_path)
        assert text == "测试正文。"


class TestScoreGroup:
    def test_empty_when_no_chapters(self, tmp_path: Path) -> None:
        scores = vpd.score_group(("ghost-book",), (1, 2), corpus_root=tmp_path)
        assert scores == []

    def test_scores_only_existing_chapters(self, tmp_path: Path) -> None:
        book_dir = tmp_path / "有一章的书" / "chapters"
        book_dir.mkdir(parents=True)
        (book_dir / "ch001.txt").write_text(
            "他推门进屋，坐下来。外面开始下雨。她抬头看他一眼。", encoding="utf-8"
        )
        scores = vpd.score_group(
            ("有一章的书",), chapter_nos=(1, 2, 3), corpus_root=tmp_path
        )
        assert len(scores) == 1
        assert scores[0].chapter_no == 1


# ---------------------------------------------------------------------------
# Orchestration + rendering
# ---------------------------------------------------------------------------


class TestRunVerificationWithStubCorpus:
    def test_runs_end_to_end_on_synthetic_corpus(self, tmp_path: Path) -> None:
        """Stub out the corpus so the full pipeline runs in a few hundred ms."""
        corpus = tmp_path / "corpus"
        for book in ("直白书", "华丽书"):
            chap_dir = corpus / book / "chapters"
            chap_dir.mkdir(parents=True)
            (chap_dir / "ch001.txt").write_text(
                "他推门进屋，坐下来。外面下雨了。她抬头看他。",
                encoding="utf-8",
            )
        results = vpd.run_verification(
            direct_books=("直白书",),
            rhetoric_books=("华丽书",),
            chapter_nos=(1,),
            corpus_root=corpus,
        )
        assert results.m1["passed"] is True  # 独立于语料
        assert results.m6["passed"] is True
        assert results.m7["passed"] is True
        assert len(results.direct_chapter_scores) == 1
        assert len(results.rhetoric_chapter_scores) == 1
        assert results.generated_at


class TestRenderMarkdown:
    def test_renders_all_metric_rows_and_gate(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        for book in ("直白书",):
            chap_dir = corpus / book / "chapters"
            chap_dir.mkdir(parents=True)
            (chap_dir / "ch001.txt").write_text(
                "他推门进屋，坐下来。外面下雨了。她抬头看他。", encoding="utf-8"
            )
        results = vpd.run_verification(
            direct_books=("直白书",),
            rhetoric_books=(),
            chapter_nos=(1,),
            corpus_root=corpus,
        )
        md = vpd.render_markdown(results)
        for marker in ("# Prose Directness Verification Report", "| M-1 |",
                       "| M-2 |", "| M-3 |", "| M-4 |", "| M-5 |",
                       "| M-6 |", "| M-7 |", "Release Gate"):
            assert marker in md, f"missing marker in rendered markdown: {marker!r}"

    def test_results_to_json_roundtrips(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        chap_dir = corpus / "A" / "chapters"
        chap_dir.mkdir(parents=True)
        (chap_dir / "ch001.txt").write_text(
            "他推开门走进屋里。外面下着雨。她坐在桌前。", encoding="utf-8"
        )
        results = vpd.run_verification(
            direct_books=("A",), rhetoric_books=(), chapter_nos=(1,),
            corpus_root=corpus,
        )
        payload = vpd.results_to_json(results)
        # Must be JSON-serializable.
        text = json.dumps(payload, ensure_ascii=False)
        assert "m1" in text and "m6" in text and "m7" in text


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


class TestCli:
    def test_parser_defaults_to_benchmark_paths(self) -> None:
        parser = vpd.build_parser()
        ns = parser.parse_args([])
        assert ns.output == vpd.DEFAULT_OUTPUT
        assert ns.json_output == vpd.DEFAULT_JSON_OUTPUT
        assert list(ns.chapters) == [1, 2, 3]

    def test_main_writes_artifacts_when_overridden(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        chap_dir = corpus / "demo-book" / "chapters"
        chap_dir.mkdir(parents=True)
        (chap_dir / "ch001.txt").write_text(
            "他推开门走进屋里。外面下着雨。她坐在桌前。", encoding="utf-8"
        )
        md_path = tmp_path / "out.md"
        json_path = tmp_path / "out.json"
        rc = vpd.main([
            "--corpus", str(corpus),
            "--output", str(md_path),
            "--json-output", str(json_path),
            "--direct-books", "demo-book",
            "--rhetoric-books", "demo-book",
            "--chapters", "1",
        ])
        # rc may be 0 or 1 depending on metric outcomes on synthetic text; we
        # only assert artifacts are produced and valid.
        assert rc in (0, 1)
        assert md_path.exists()
        assert json_path.exists()
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["m1"]["passed"] is True  # fixture-driven


# ---------------------------------------------------------------------------
# Opt-in corpus integration (skipped when benchmark missing)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (vpd.CORPUS_ROOT / vpd.DIRECT_TOP5[0] / "chapters" / "ch001.txt").exists(),
    reason="benchmark/reference_corpus Top-5 book missing locally",
)
class TestFullCorpusSmoke:
    def test_scores_first_direct_chapter_has_high_directness(self) -> None:
        """Single chapter from 最直白 Top-5 should land in green/yellow, never red."""
        book = vpd.DIRECT_TOP5[0]
        text = vpd.load_chapter_text(book, 1)
        assert text is not None
        cm = vpd.score_chapter(
            text, book=book, chapter_no=1, scene_mode="golden_three"
        )
        # 最直白 Top-5 is the aspirational target — overall ≥ 7 is a sanity floor.
        assert cm.overall_score >= 7.0
