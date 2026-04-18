"""US-028 覆盖率阶梯（30→50）补测：针对覆盖率低的关键模块补集成测试。

目标模块（按覆盖率从低到高）：
1. encoding_validator.py（51%）
2. step3_harness_gate.py（56%）
3. slim_review_bundle.py（59%）

零回归：本测试不改动任何被测模块，仅读取公共 API。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "ink-writer" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# encoding_validator
# ---------------------------------------------------------------------------


class TestEncodingValidator:
    def test_find_mojibake_empty_on_clean_text(self) -> None:
        from encoding_validator import find_mojibake

        assert find_mojibake("正常的中文内容，没有乱码。") == []
        assert find_mojibake("") == []

    def test_find_mojibake_detects_single_replacement(self) -> None:
        from encoding_validator import find_mojibake

        text = "前面正常\ufffd后面正常"
        issues = find_mojibake(text)
        assert len(issues) == 1
        assert issues[0]["count"] == 1
        assert issues[0]["line"] == 1
        assert "前面" in issues[0]["context_before"]
        assert "后面" in issues[0]["context_after"]

    def test_find_mojibake_merges_consecutive_chars(self) -> None:
        from encoding_validator import find_mojibake

        # 三个连续的 U+FFFD（单个中文字符被完全破坏时的典型模式）
        text = "A\ufffd\ufffd\ufffdB"
        issues = find_mojibake(text)
        assert len(issues) == 1
        assert issues[0]["count"] == 3
        assert issues[0]["column"] == 2

    def test_find_mojibake_multiline(self) -> None:
        from encoding_validator import find_mojibake

        text = "line1\nline2\ufffd\nline3"
        issues = find_mojibake(text)
        assert len(issues) == 1
        assert issues[0]["line"] == 2

    def test_find_mojibake_multiple_occurrences(self) -> None:
        from encoding_validator import find_mojibake

        text = "abc\ufffddef\ufffd\ufffdghi"
        issues = find_mojibake(text)
        assert len(issues) == 2
        assert issues[0]["count"] == 1
        assert issues[1]["count"] == 2


# ---------------------------------------------------------------------------
# slim_review_bundle
# ---------------------------------------------------------------------------


class TestSlimReviewBundle:
    def _full_bundle(self) -> dict:
        return {
            "chapter": 7,
            "project_root": "/tmp/proj",
            "chapter_file": "chapters/7/draft.md",
            "chapter_file_name": "draft.md",
            "chapter_char_count": 3200,
            "absolute_paths": {"x": 1},
            "allowed_read_files": ["a", "b"],
            "review_policy": {"threshold": 60},
            "chapter_text": "正文内容……",
            "scene_context": {"x": 1},
            "setting_snapshots": {"y": 2},
            "core_context": {"z": 3},
            "nonsense_extra": "should be dropped for anti-detection",
        }

    def test_slim_bundle_preserves_meta_and_profile(self) -> None:
        from slim_review_bundle import META_FIELDS, slim_bundle

        full = self._full_bundle()
        slim = slim_bundle(full, "anti-detection-checker")
        # META 全保留
        for f in META_FIELDS:
            assert f in slim
        # anti-detection profile：仅需 chapter_text（不含 scene_context）
        assert "chapter_text" in slim
        assert "nonsense_extra" not in slim

    def test_slim_bundle_logic_checker_includes_all_fields(self) -> None:
        from slim_review_bundle import slim_bundle

        slim = slim_bundle(self._full_bundle(), "logic-checker")
        for f in ("chapter_text", "scene_context", "setting_snapshots", "core_context"):
            assert f in slim

    def test_slim_bundle_extra_fields_merged(self) -> None:
        from slim_review_bundle import slim_bundle

        extras = {"precheck_results": {"ok": True}}
        slim = slim_bundle(self._full_bundle(), "logic-checker", extra_fields=extras)
        assert slim["precheck_results"] == {"ok": True}

    def test_slim_bundle_unknown_checker_raises(self) -> None:
        from slim_review_bundle import slim_bundle

        with pytest.raises(ValueError):
            slim_bundle(self._full_bundle(), "no-such-checker")

    def test_generate_slim_bundles_writes_files(self, tmp_path: Path) -> None:
        from slim_review_bundle import generate_slim_bundles

        bundle_path = tmp_path / "full.json"
        bundle_path.write_text(
            json.dumps(self._full_bundle(), ensure_ascii=False), encoding="utf-8"
        )
        outdir = tmp_path / "slim"
        result = generate_slim_bundles(
            bundle_path,
            ["anti-detection-checker", "logic-checker"],
            outdir,
        )
        assert set(result.keys()) == {"anti-detection-checker", "logic-checker"}
        for checker, p in result.items():
            assert p.exists()
            data = json.loads(p.read_text(encoding="utf-8"))
            assert data["chapter"] == 7

    def test_generate_slim_bundles_unknown_checker_falls_back(self, tmp_path: Path) -> None:
        from slim_review_bundle import generate_slim_bundles

        bundle_path = tmp_path / "full.json"
        bundle_path.write_text(
            json.dumps(self._full_bundle(), ensure_ascii=False), encoding="utf-8"
        )
        outdir = tmp_path / "slim"
        result = generate_slim_bundles(bundle_path, ["no-such-checker"], outdir)
        # fallback：未知 checker → 指向原始 bundle
        assert result["no-such-checker"] == bundle_path


# ---------------------------------------------------------------------------
# step3_harness_gate
# ---------------------------------------------------------------------------


def _make_index_db_with_review(
    project_root: Path, chapter: int, payload: dict | None = None, **columns
) -> None:
    db_path = project_root / ".ink" / "index.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_metrics (
                start_chapter INTEGER,
                end_chapter INTEGER,
                overall_score INTEGER,
                dimension_scores TEXT,
                severity_counts TEXT,
                critical_issues TEXT,
                review_payload_json TEXT,
                report_file TEXT,
                notes TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO review_metrics (
                start_chapter, end_chapter, overall_score, dimension_scores,
                severity_counts, critical_issues, review_payload_json,
                report_file, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chapter,
                chapter,
                columns.get("overall_score", 80),
                json.dumps(columns.get("dimension_scores", {})),
                json.dumps(columns.get("severity_counts", {})),
                json.dumps(columns.get("critical_issues", [])),
                json.dumps(payload) if payload is not None else None,
                "",
                "",
            ),
        )
        conn.commit()
    finally:
        conn.close()


class TestStep3HarnessGate:
    def test_missing_data_is_explicit_fail(self, tmp_path: Path) -> None:
        from step3_harness_gate import check_review_gate

        result = check_review_gate(tmp_path, 5)
        assert result["pass"] is False
        assert "no review data" in result["reason"]
        assert result["action"] == "rerun_step3_review"

    def test_index_db_pass_path(self, tmp_path: Path) -> None:
        from step3_harness_gate import check_review_gate

        _make_index_db_with_review(
            tmp_path,
            chapter=5,
            payload={
                "overall_score": 85,
                "severity_counts": {"critical": 0, "high": 1},
                "checker_results": {},
            },
        )
        result = check_review_gate(tmp_path, 5)
        assert result["pass"] is True

    def test_overall_score_below_40_fails(self, tmp_path: Path) -> None:
        from step3_harness_gate import check_review_gate

        _make_index_db_with_review(
            tmp_path,
            chapter=10,
            payload={
                "overall_score": 30,
                "severity_counts": {"critical": 0},
                "checker_results": {},
            },
        )
        result = check_review_gate(tmp_path, 10)
        assert result["pass"] is False
        assert "overall_score" in result["reason"]
        assert result["action"] == "rewrite_step2a"

    def test_critical_threshold_fails(self, tmp_path: Path) -> None:
        from step3_harness_gate import check_review_gate

        _make_index_db_with_review(
            tmp_path,
            chapter=10,
            payload={
                "overall_score": 75,
                "severity_counts": {"critical": 3},
                "checker_results": {},
            },
        )
        result = check_review_gate(tmp_path, 10)
        assert result["pass"] is False
        assert "critical issues" in result["reason"]

    def test_golden_three_high_issue_blocks(self, tmp_path: Path) -> None:
        from step3_harness_gate import check_review_gate

        _make_index_db_with_review(
            tmp_path,
            chapter=2,
            payload={
                "overall_score": 90,
                "severity_counts": {"critical": 0},
                "checker_results": {
                    "golden-three-checker": {
                        "issues": [{"severity": "high", "desc": "开头乏力"}]
                    }
                },
            },
        )
        result = check_review_gate(tmp_path, 2)
        assert result["pass"] is False
        assert "黄金三章" in result["reason"]

    def test_legacy_json_fallback(self, tmp_path: Path) -> None:
        from step3_harness_gate import check_review_gate

        reports_dir = tmp_path / ".ink" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "review_ch0005.json").write_text(
            json.dumps(
                {
                    "start_chapter": 5,
                    "end_chapter": 5,
                    "overall_score": 85,
                    "severity_counts": {"critical": 0},
                    "checker_results": {},
                }
            ),
            encoding="utf-8",
        )
        result = check_review_gate(tmp_path, 5)
        assert result["pass"] is True
