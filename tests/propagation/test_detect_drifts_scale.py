"""US-003 scale test：1000 章 review_metrics fixture 下批量路径 <3s，且与 legacy 路径语义一致。"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import List

import pytest

from ink_writer.propagation import detect_drifts
from ink_writer.propagation.drift_detector import (
    DEFAULT_CRITICAL_ISSUE_LIMIT,
    DEFAULT_MAX_CHAPTERS_PER_SCAN,
    _drifts_from_data,
    _load_records_from_db_batched,
    _load_records_from_db_legacy,
)


NUM_CHAPTERS = 1000


def _build_index_db(tmp_path: Path, num_chapters: int = NUM_CHAPTERS) -> Path:
    """Construct a realistic review_metrics fixture with 1 review row per chapter."""
    ink_dir = tmp_path / ".ink"
    ink_dir.mkdir()
    db_path = ink_dir / "index.db"
    conn = sqlite3.connect(str(db_path))
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
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_review_metrics_end ON review_metrics(end_chapter)"
    )
    rows = []
    for ch in range(1, num_chapters + 1):
        # 每 7 章 1 个 drift，3 章 1 个 consistency 违规，避免全空节点
        critical: List[dict] = []
        checker_payload: dict = {}
        if ch > 5 and ch % 7 == 0:
            critical.append({
                "type": "cross_chapter_conflict",
                "target_chapter": max(1, ch - 5),
                "severity": "high",
                "rule": f"power.level.ch{ch}",
            })
        if ch > 3 and ch % 3 == 0:
            checker_payload["consistency-checker"] = {
                "violations": [
                    {
                        "rule": f"location.state.ch{ch}",
                        "target_chapter": max(1, ch - 2),
                        "severity": "medium",
                    }
                ]
            }
        payload = {"checker_results": checker_payload} if checker_payload else {}
        rows.append(
            (
                ch,
                ch,
                json.dumps(critical) if critical else None,
                json.dumps(payload) if payload else None,
            )
        )
    conn.executemany(
        "INSERT INTO review_metrics(start_chapter, end_chapter, critical_issues, review_payload_json) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db_path


def test_detect_drifts_1000_chapters_completes_under_3s(tmp_path: Path):
    _build_index_db(tmp_path)
    start = time.perf_counter()
    drifts = detect_drifts(tmp_path, (1, NUM_CHAPTERS))
    elapsed = time.perf_counter() - start
    assert elapsed < 3.0, f"1000-chapter batched scan took {elapsed:.2f}s (expected <3s)"
    # Sanity: 每 7 章 1 条 critical + 每 3 章 1 条 consistency，总量在正确量级。
    assert len(drifts) > 400
    # 所有 drift 的 chapter_detected 必须在 [1, 1000] 区间
    for d in drifts:
        assert 1 <= d.chapter_detected <= NUM_CHAPTERS
        assert d.target_chapter < d.chapter_detected


def test_batched_and_legacy_paths_produce_equivalent_drifts(tmp_path: Path):
    """零回归保障：新批量路径与 legacy 路径在同一 fixture 下语义一致。"""
    _build_index_db(tmp_path, num_chapters=200)
    drifts_new = detect_drifts(tmp_path, (1, 200))
    drifts_legacy = detect_drifts(tmp_path, (1, 200), legacy=True)
    # 稳定排序后比较 (chapter_detected, target_chapter, severity, rule_violation)
    def _key(d):
        return (d.chapter_detected, d.target_chapter, d.severity, d.rule_violation)

    assert sorted((_key(d) for d in drifts_new)) == sorted((_key(d) for d in drifts_legacy))


def test_max_chapters_per_scan_controls_batch_size(tmp_path: Path, monkeypatch):
    """验证 max_chapters_per_scan 真实影响 SQL 执行次数。

    使用 sqlite3.Connection.set_trace_callback 计数 review_metrics 查询次数；
    比直接 monkeypatch Cursor 更稳健（Cursor 类在 CPython 3.14 是 immutable）。
    """
    _build_index_db(tmp_path, num_chapters=120)
    exec_count = {"n": 0}

    def tracer(sql):
        if sql and "review_metrics" in sql and "WHERE start_chapter" in sql:
            exec_count["n"] += 1

    import ink_writer.propagation.drift_detector as dd

    real_connect = dd.sqlite3.connect

    def traced_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.set_trace_callback(tracer)
        return conn

    monkeypatch.setattr(dd.sqlite3, "connect", traced_connect)

    # batch=50 → ceil(120/50) = 3 次 SQL
    _load_records_from_db_batched(tmp_path, list(range(1, 121)), max_chapters_per_scan=50)
    assert exec_count["n"] == 3

    exec_count["n"] = 0
    # batch=30 → ceil(120/30) = 4 次 SQL
    _load_records_from_db_batched(tmp_path, list(range(1, 121)), max_chapters_per_scan=30)
    assert exec_count["n"] == 4

    exec_count["n"] = 0
    # legacy 路径 1 章 1 次 → 120 次
    _load_records_from_db_legacy(tmp_path, list(range(1, 121)))
    assert exec_count["n"] == 120


def test_critical_issue_limit_20_early_stop():
    """单章 critical_issues 异常多时，默认 limit=20 只产出前 20 条。"""
    issues = [
        {"type": "cross_chapter_conflict", "target_chapter": i, "severity": "high"}
        for i in range(1, 101)  # 100 条
    ]
    data = {"critical_issues": issues, "checker_results": {}}
    drifts = _drifts_from_data(500, data)
    assert len(drifts) == DEFAULT_CRITICAL_ISSUE_LIMIT == 20


def test_critical_issue_limit_none_preserves_legacy_behaviour():
    """传 critical_limit=None 时保留旧行为（全量处理）。"""
    issues = [
        {"type": "cross_chapter_conflict", "target_chapter": i, "severity": "high"}
        for i in range(1, 51)
    ]
    data = {"critical_issues": issues, "checker_results": {}}
    drifts = _drifts_from_data(500, data, critical_limit=None)
    assert len(drifts) == 50


def test_batched_path_handles_overlapping_ranges(tmp_path: Path):
    """跨章覆盖（start<end）场景：一行覆盖多章时，应赋值到所有落在区间内的章。"""
    ink_dir = tmp_path / ".ink"
    ink_dir.mkdir()
    db_path = ink_dir / "index.db"
    conn = sqlite3.connect(str(db_path))
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
    critical = json.dumps([
        {"type": "cross_chapter_conflict", "target_chapter": 1, "severity": "high", "rule": "spanning"}
    ])
    conn.execute(
        "INSERT INTO review_metrics(start_chapter, end_chapter, critical_issues) VALUES (?, ?, ?)",
        (10, 15, critical),
    )
    conn.commit()
    conn.close()

    drifts = detect_drifts(tmp_path, (10, 15))
    # 10..15 = 6 章，全部覆盖于 (10,15) 行，应产出 6 条 drift
    assert len(drifts) == 6
    assert {d.chapter_detected for d in drifts} == {10, 11, 12, 13, 14, 15}
    assert all(d.target_chapter == 1 for d in drifts)


def test_default_constants_match_acceptance():
    assert DEFAULT_MAX_CHAPTERS_PER_SCAN == 50
    assert DEFAULT_CRITICAL_ISSUE_LIMIT == 20
