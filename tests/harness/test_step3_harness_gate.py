"""US-005: step3_harness_gate 改读 index.db.review_metrics。

验证：
  1. 从 index.db.review_metrics 读取数据正确（PASS 与 FAIL 分支）
  2. index.db 无记录时 fallback 到 legacy JSON 路径（打 warning）
  3. 两者均无记录时显式 FAIL（不是 silent PASS）
  4. 老 review_payload_json 缺失时基于列组降级
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ink-writer" / "scripts"))

from step3_harness_gate import check_review_gate  # noqa: E402


def _setup_project(tmp_path: Path) -> Path:
    """Create minimal .ink/index.db structure."""
    project_root = tmp_path / "book"
    ink_dir = project_root / ".ink"
    ink_dir.mkdir(parents=True)
    db_path = ink_dir / "index.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE review_metrics (
                start_chapter INTEGER NOT NULL,
                end_chapter INTEGER NOT NULL,
                overall_score REAL DEFAULT 0,
                dimension_scores TEXT,
                severity_counts TEXT,
                critical_issues TEXT,
                report_file TEXT,
                notes TEXT,
                review_payload_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (start_chapter, end_chapter)
            )
            """
        )
    return project_root


def _insert_metrics(project_root: Path, start: int, end: int, *, overall_score: float = 80,
                    severity_counts: dict | None = None, payload: dict | None = None) -> None:
    with sqlite3.connect(str(project_root / ".ink" / "index.db")) as conn:
        conn.execute(
            """
            INSERT INTO review_metrics (start_chapter, end_chapter, overall_score,
                                        severity_counts, review_payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                start,
                end,
                overall_score,
                json.dumps(severity_counts or {}),
                json.dumps(payload) if payload else None,
            ),
        )


def test_no_data_anywhere_fails_explicitly(tmp_path):
    """v5 Blocker fix：无审查数据不再 silent PASS，改为 FAIL + rerun_step3_review。"""
    project_root = _setup_project(tmp_path)
    result = check_review_gate(project_root, chapter_num=5)
    assert result["pass"] is False
    assert "no review data found" in result["reason"]
    assert result["action"] == "rerun_step3_review"


def test_index_db_record_drives_pass(tmp_path):
    """index.db 有正常记录 → PASS。"""
    project_root = _setup_project(tmp_path)
    _insert_metrics(
        project_root, start=1, end=5, overall_score=85,
        severity_counts={"critical": 0, "high": 1}, payload={
            "overall_score": 85, "severity_counts": {"critical": 0}, "checker_results": {}
        }
    )
    result = check_review_gate(project_root, chapter_num=3)
    assert result["pass"] is True, f"expected pass, got {result}"


def test_index_db_critical_fails(tmp_path):
    """index.db 记录 critical >= 3 → FAIL rewrite_step2a。"""
    project_root = _setup_project(tmp_path)
    _insert_metrics(
        project_root, start=10, end=15, overall_score=60,
        severity_counts={"critical": 5},
        payload={"overall_score": 60, "severity_counts": {"critical": 5}, "checker_results": {}},
    )
    result = check_review_gate(project_root, chapter_num=12)
    assert result["pass"] is False
    assert "critical issues=5" in result["reason"]
    assert result["action"] == "rewrite_step2a"


def test_index_db_low_score_fails(tmp_path):
    """overall_score < 40 → FAIL rewrite_step2a。"""
    project_root = _setup_project(tmp_path)
    _insert_metrics(
        project_root, start=20, end=25, overall_score=30,
        severity_counts={"critical": 0},
        payload={"overall_score": 30, "severity_counts": {"critical": 0}, "checker_results": {}},
    )
    result = check_review_gate(project_root, chapter_num=22)
    assert result["pass"] is False
    assert "overall_score=30" in result["reason"]


def test_legacy_json_fallback(tmp_path, caplog):
    """index.db 无记录但 legacy JSON 存在 → 用 JSON 并打 warning。"""
    project_root = _setup_project(tmp_path)  # index.db 存在但无数据
    reports_dir = project_root / ".ink" / "reports"
    reports_dir.mkdir()
    (reports_dir / "review_ch5.json").write_text(
        json.dumps({
            "start_chapter": 1, "end_chapter": 10, "overall_score": 75,
            "severity_counts": {"critical": 0}, "checker_results": {},
        }),
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        result = check_review_gate(project_root, chapter_num=5)
    assert result["pass"] is True
    assert any("legacy JSON path" in record.message for record in caplog.records), (
        "expected legacy path warning"
    )


def test_minimal_payload_without_checker_results(tmp_path):
    """review_payload_json 缺失时基于列组（overall_score/severity_counts）降级判断。"""
    project_root = _setup_project(tmp_path)
    # 故意不给 payload
    _insert_metrics(
        project_root, start=1, end=5, overall_score=85,
        severity_counts={"critical": 0},
    )
    result = check_review_gate(project_root, chapter_num=3)
    # 没有 checker_results，黄金三章 / reader-simulator 规则跳过，score=85 & critical=0 → PASS
    assert result["pass"] is True
