"""Tests for 300-chapter benchmark and blind test tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from run_300chapter_benchmark import (
    BenchmarkResult,
    G1Metrics,
    G2Metrics,
    G3Metrics,
    G4Metrics,
    G5Metrics,
    generate_acceptance_report,
)
from build_blind_test import (
    BlindTestConfig,
    BlindTestSet,
    BlindSample,
    build_blind_test,
    generate_blind_test_report,
    RATING_DIMENSIONS,
)


class TestBenchmarkResult:
    def test_all_passed(self):
        result = BenchmarkResult(
            g1=G1Metrics(emotion_similarity=0.85),
            g2=G2Metrics(anti_detection_score=90),
            g3=G3Metrics(circular_deps=0, duplicate_impl=0, dead_code_pct=1.0),
            g4=G4Metrics(ooc_score=3, setting_contradictions=1, plotline_dropped=0),
            g5=G5Metrics(
                avg_chapter_seconds=100, baseline_chapter_seconds=200,
                avg_chapter_tokens=3000, baseline_chapter_tokens=5000,
            ),
        )
        assert result.all_passed

    def test_g1_fail(self):
        g1 = G1Metrics(emotion_similarity=0.5)
        assert not g1.passed

    def test_g2_fail(self):
        g2 = G2Metrics(anti_detection_score=60)
        assert not g2.passed

    def test_g3_fail_circular(self):
        g3 = G3Metrics(circular_deps=1)
        assert not g3.passed

    def test_g4_fail_ooc(self):
        g4 = G4Metrics(ooc_score=10)
        assert not g4.passed

    def test_g5_fail_time(self):
        g5 = G5Metrics(
            avg_chapter_seconds=200, baseline_chapter_seconds=200,
            avg_chapter_tokens=3000, baseline_chapter_tokens=5000,
        )
        assert not g5.passed

    def test_g5_pass_no_baseline(self):
        g5 = G5Metrics(avg_chapter_seconds=100, baseline_chapter_seconds=0)
        assert g5.passed

    def test_to_dict(self):
        result = BenchmarkResult(total_chapters=300, wall_time_s=12345)
        d = result.to_dict()
        assert d["total_chapters"] == 300
        assert "g1_readability" in d
        assert "g5_efficiency" in d

    def test_generate_acceptance_report(self, tmp_path: Path):
        result = BenchmarkResult(
            total_chapters=300,
            wall_time_s=36000,
            g1=G1Metrics(emotion_similarity=0.9),
            g2=G2Metrics(anti_detection_score=88),
            g3=G3Metrics(),
            g4=G4Metrics(),
            g5=G5Metrics(
                avg_chapter_seconds=100, baseline_chapter_seconds=200,
                avg_chapter_tokens=3000, baseline_chapter_tokens=5000,
            ),
        )
        report_path = tmp_path / "v13_acceptance.md"
        generate_acceptance_report(result, report_path)
        assert report_path.exists()
        content = report_path.read_text(encoding="utf-8")
        assert "v13 验收报告" in content
        assert "PASS" in content


class TestBlindTestConfig:
    def test_defaults(self):
        cfg = BlindTestConfig()
        assert cfg.samples_per_source == 10
        assert cfg.min_readers == 5


class TestBlindTestSet:
    def test_manifest(self):
        samples = [
            BlindSample("S001", "generated", "/a/b.md", "S001.md"),
            BlindSample("S002", "reference", "/c/d.md", "S002.md"),
        ]
        ts = BlindTestSet(samples=samples)
        m = ts.to_manifest()
        assert m["total_samples"] == 2
        assert m["generated_count"] == 1
        assert m["reference_count"] == 1

    def test_answer_key(self):
        samples = [
            BlindSample("S001", "generated", "", ""),
            BlindSample("S002", "reference", "", ""),
        ]
        ts = BlindTestSet(samples=samples)
        key = ts.to_answer_key()
        assert key["S001"] == "generated"
        assert key["S002"] == "reference"


class TestBuildBlindTest:
    def test_build_with_files(self, tmp_path: Path):
        project = tmp_path / "novel"
        (project / "正文").mkdir(parents=True)
        for i in range(5):
            (project / "正文" / f"第{i+1:04d}章测试.md").write_text(f"内容{i}")

        corpus = tmp_path / "corpus"
        book = corpus / "book1"
        book.mkdir(parents=True)
        for i in range(5):
            (book / f"ch{i+1}.md").write_text(f"参考{i}")

        output = tmp_path / "blind_test"
        cfg = BlindTestConfig(samples_per_source=3, seed=42)
        result = build_blind_test(project, corpus, output, cfg)

        assert len(result.samples) == 6
        assert (output / "manifest.json").exists()
        assert (output / "answer_key.json").exists()
        assert (output / "rating_sheet.md").exists()

        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["total_samples"] == 6

    def test_build_empty_project(self, tmp_path: Path):
        project = tmp_path / "empty"
        project.mkdir()
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        output = tmp_path / "blind"
        cfg = BlindTestConfig(samples_per_source=3)

        result = build_blind_test(project, corpus, output, cfg)
        assert len(result.samples) == 0


class TestBlindTestReport:
    def test_generate_report(self, tmp_path: Path):
        answer_key = {"S001": "generated", "S002": "reference"}
        ratings = {
            "S001": [
                {"吸引力 (1-10)": 8, "AI 味 (1-10, 10=完全人写)": 7,
                 "人物塑造 (1-10)": 8, "节奏 (1-10)": 7, "情绪感染力 (1-10)": 8},
            ],
            "S002": [
                {"吸引力 (1-10)": 8, "AI 味 (1-10, 10=完全人写)": 8,
                 "人物塑造 (1-10)": 8, "节奏 (1-10)": 8, "情绪感染力 (1-10)": 8},
            ],
        }
        report_path = tmp_path / "report.md"
        result = generate_blind_test_report(ratings, answer_key, report_path)

        assert report_path.exists()
        assert "overall_ratio" in result
        assert result["overall_ratio"] > 0

    def test_report_passed_threshold(self, tmp_path: Path):
        answer_key = {"S001": "generated", "S002": "reference"}
        ratings = {
            "S001": [
                {d: 9.5 for d in RATING_DIMENSIONS},
            ],
            "S002": [
                {d: 10.0 for d in RATING_DIMENSIONS},
            ],
        }
        report_path = tmp_path / "report.md"
        result = generate_blind_test_report(ratings, answer_key, report_path)
        assert result["passed"]  # 9.5/10 = 0.95 ≥ 0.95

    def test_report_failed_threshold(self, tmp_path: Path):
        answer_key = {"S001": "generated", "S002": "reference"}
        ratings = {
            "S001": [{d: 5.0 for d in RATING_DIMENSIONS}],
            "S002": [{d: 10.0 for d in RATING_DIMENSIONS}],
        }
        report_path = tmp_path / "report.md"
        result = generate_blind_test_report(ratings, answer_key, report_path)
        assert not result["passed"]  # 5/10 = 0.5 < 0.95
