"""US-004 incremental drift-debt cache: 800 章全扫 + 增量扫第 801 章 <5s，CLI
--reset 清空 cache，新增 chapter > last_seen_max 才触发 SQL。"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import List

import pytest

from ink_writer.propagation import detect_drifts
from ink_writer.propagation.drift_detector import (
    DRIFT_DEBTS_DB_REL_PATH,
    _cli_main,
    reset_drift_debts_cache,
)


def _build_index_db(tmp_path: Path, num_chapters: int) -> Path:
    """review_metrics fixture with 1 row per chapter (reused from US-003 scale tests)."""
    ink_dir = tmp_path / ".ink"
    ink_dir.mkdir(exist_ok=True)
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
    rows = []
    for ch in range(1, num_chapters + 1):
        critical: List[dict] = []
        checker_payload: dict = {}
        if ch > 5 and ch % 7 == 0:
            critical.append(
                {
                    "type": "cross_chapter_conflict",
                    "target_chapter": max(1, ch - 5),
                    "severity": "high",
                    "rule": f"power.level.ch{ch}",
                }
            )
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
        "INSERT INTO review_metrics(start_chapter, end_chapter, critical_issues, review_payload_json) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db_path


def _cache_table_schema(project_root: Path) -> List[tuple]:
    db_path = project_root / DRIFT_DEBTS_DB_REL_PATH
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("PRAGMA table_info(drift_debts)").fetchall()
    finally:
        conn.close()
    return rows


def test_cache_schema_matches_prd_spec(tmp_path: Path):
    """Acceptance: CREATE TABLE drift_debts (chapter_id TEXT, debt_type TEXT,
    payload JSON, last_seen INTEGER, PRIMARY KEY(chapter_id, debt_type))."""
    _build_index_db(tmp_path, num_chapters=5)
    detect_drifts(tmp_path, (1, 5), incremental=True)
    schema = _cache_table_schema(tmp_path)
    assert schema, "drift_debts table should exist after incremental scan"
    columns = {row[1]: row for row in schema}  # name -> (cid, name, type, notnull, dflt, pk)
    assert set(columns) == {"chapter_id", "debt_type", "payload", "last_seen"}
    assert columns["chapter_id"][2].upper() == "TEXT"
    assert columns["debt_type"][2].upper() == "TEXT"
    assert columns["payload"][2].upper() == "JSON"
    assert columns["last_seen"][2].upper() == "INTEGER"
    # Both chapter_id and debt_type are part of the composite PK.
    pk_cols = {row[1] for row in schema if row[5] > 0}
    assert pk_cols == {"chapter_id", "debt_type"}


def test_incremental_skips_already_scanned_chapters(tmp_path: Path, monkeypatch):
    """Second call with same range triggers 0 SELECT on review_metrics."""
    _build_index_db(tmp_path, num_chapters=40)

    exec_count = {"review_metrics": 0}

    def tracer(sql: str) -> None:
        if sql and "review_metrics" in sql and "WHERE start_chapter" in sql:
            exec_count["review_metrics"] += 1

    import ink_writer.propagation.drift_detector as dd

    real_connect = dd.sqlite3.connect

    def traced_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.set_trace_callback(tracer)
        return conn

    monkeypatch.setattr(dd.sqlite3, "connect", traced_connect)

    drifts_first = detect_drifts(tmp_path, (1, 40), incremental=True)
    first_queries = exec_count["review_metrics"]
    assert first_queries >= 1, "first incremental scan must hit review_metrics"

    exec_count["review_metrics"] = 0
    drifts_second = detect_drifts(tmp_path, (1, 40), incremental=True)
    assert exec_count["review_metrics"] == 0, (
        "second incremental call over already-seen range must not re-query review_metrics; "
        f"got {exec_count['review_metrics']} queries"
    )

    def _key(d):
        return (d.chapter_detected, d.target_chapter, d.severity, d.rule_violation)

    assert sorted(_key(d) for d in drifts_first) == sorted(_key(d) for d in drifts_second)


def test_incremental_800_plus_801_total_under_5s(tmp_path: Path):
    """Acceptance: 800 章全扫一次 + 增量扫第 801 章，总时间 <5s。"""
    _build_index_db(tmp_path, num_chapters=801)

    t0 = time.perf_counter()
    first_batch = detect_drifts(tmp_path, (1, 800), incremental=True)
    t_first = time.perf_counter() - t0
    assert len(first_batch) > 300, (
        "1..800 scan should surface at least a few hundred drifts with the US-003 fixture"
    )

    t1 = time.perf_counter()
    second_batch = detect_drifts(tmp_path, (1, 801), incremental=True)
    t_second = time.perf_counter() - t1

    total = t_first + t_second
    assert total < 5.0, (
        f"800 full + incremental 801 scan took {total:.2f}s (first={t_first:.2f}s, "
        f"incr={t_second:.2f}s); expected <5s"
    )
    # Second batch ⊇ first batch (cache accumulates).
    assert len(second_batch) >= len(first_batch)


def test_incremental_new_chapter_adds_only_new_drifts(tmp_path: Path):
    _build_index_db(tmp_path, num_chapters=14)
    first = detect_drifts(tmp_path, (1, 7), incremental=True)
    first_ids = {d.debt_id for d in first}

    # Extend the corpus: chapter 14 has a ch%7==0 drift, so rescanning 1..14 should add it.
    second = detect_drifts(tmp_path, (1, 14), incremental=True)
    second_ids = {d.debt_id for d in second}
    new_only = second_ids - first_ids
    assert new_only, "extending range to a drifty chapter must introduce new debt_ids"
    # All new debts belong to chapters > 7 (the previous watermark).
    new_chapters = {d.chapter_detected for d in second if d.debt_id in new_only}
    assert all(c > 7 for c in new_chapters), (
        f"new drifts must come from chapters > previous watermark, got {sorted(new_chapters)}"
    )


def test_incremental_empty_range_bumps_watermark(tmp_path: Path, monkeypatch):
    """Re-calling with same range should no-op even when the new scan yields 0 drifts."""
    tmp_path.joinpath(".ink").mkdir(exist_ok=True)
    # No review_metrics rows — scan returns [] but watermark should still latch.
    detect_drifts(tmp_path, (1, 10), incremental=True)

    exec_count = {"review_metrics": 0}

    def tracer(sql: str) -> None:
        if sql and "review_metrics" in sql:
            exec_count["review_metrics"] += 1

    import ink_writer.propagation.drift_detector as dd

    real_connect = dd.sqlite3.connect

    def traced_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.set_trace_callback(tracer)
        return conn

    monkeypatch.setattr(dd.sqlite3, "connect", traced_connect)

    detect_drifts(tmp_path, (1, 10), incremental=True)
    assert exec_count["review_metrics"] == 0, (
        "empty-scan watermark must persist so repeat calls skip review_metrics"
    )


def test_reset_cli_clears_cache(tmp_path: Path, capsys):
    _build_index_db(tmp_path, num_chapters=10)
    detect_drifts(tmp_path, (1, 10), incremental=True)
    db_path = tmp_path / DRIFT_DEBTS_DB_REL_PATH
    assert db_path.exists()

    exit_code = _cli_main(["--reset", "--project-root", str(tmp_path)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "cleared" in captured.out.lower()

    # Next scan should go through again.
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert "drift_debts" not in tables, (
        "--reset should drop the drift_debts table (reset_drift_debts_cache uses DROP TABLE)"
    )


def test_reset_without_cache_returns_zero_and_friendly_message(tmp_path: Path, capsys):
    exit_code = _cli_main(["--reset", "--project-root", str(tmp_path)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "no drift_debts cache" in captured.out.lower()


def test_reset_helper_returns_false_when_no_cache(tmp_path: Path):
    assert reset_drift_debts_cache(tmp_path) is False


def test_non_incremental_path_does_not_touch_cache(tmp_path: Path):
    """Green/零回归：legacy detect_drifts() semantics unchanged, no cache file created."""
    _build_index_db(tmp_path, num_chapters=10)
    detect_drifts(tmp_path, (1, 10))  # incremental=False default
    assert not (tmp_path / DRIFT_DEBTS_DB_REL_PATH).exists(), (
        "non-incremental call must not write drift_debts.db (zero regression)"
    )
