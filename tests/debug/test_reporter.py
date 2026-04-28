"""Tests for reporter dual-view markdown."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ink_writer.debug.config import DebugConfig
from ink_writer.debug.indexer import SCHEMA
from ink_writer.debug.reporter import Reporter


def _seed_db(tmp_path: Path) -> Path:
    debug_dir = tmp_path / ".ink-debug"
    debug_dir.mkdir(parents=True)
    db = debug_dir / "debug.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    now = datetime.now(timezone.utc)
    rows = [
        (now.isoformat(), "r1", None, "p", 1, "layer_c_invariant", "ink-write", "writer",
         "writer.short_word_count", "warn", "len 1000<2200", json.dumps({"length": 1000}), None),
        (now.isoformat(), "r1", None, "p", 1, "layer_c_invariant", "ink-write", "polish",
         "polish.diff_too_small", "warn", "diff 30<50", json.dumps({"diff_chars": 30}), None),
        (now.isoformat(), "r2", None, "p", 2, "layer_c_invariant", "ink-write", "writer",
         "writer.short_word_count", "warn", "len 1500<2200", json.dumps({"length": 1500}), None),
    ]
    conn.executemany(
        "INSERT INTO incidents (ts, run_id, session_id, project, chapter, source, skill, step, "
        "kind, severity, message, evidence_json, trace_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db


def test_report_includes_both_views(tmp_path: Path):
    _seed_db(tmp_path)
    cfg = DebugConfig(project_root=tmp_path)
    md = Reporter(cfg).render(since="1d", run_id=None, severity="info")
    assert "视图 1" in md
    assert "视图 2" in md
    assert "writer.short_word_count" in md
    assert "polish.diff_too_small" in md


def test_report_filter_by_run_id(tmp_path: Path):
    _seed_db(tmp_path)
    cfg = DebugConfig(project_root=tmp_path)
    md = Reporter(cfg).render(since="1d", run_id="r1", severity="info")
    # r2's row should not appear
    assert md.count("writer.short_word_count") <= 2  # r1 only


def test_report_empty_db_says_no_data(tmp_path: Path):
    debug_dir = tmp_path / ".ink-debug"
    debug_dir.mkdir(parents=True)
    db = debug_dir / "debug.db"
    sqlite3.connect(db).executescript(SCHEMA)
    cfg = DebugConfig(project_root=tmp_path)
    md = Reporter(cfg).render(since="1d", run_id=None, severity="info")
    assert "无数据" in md or "no data" in md.lower()
