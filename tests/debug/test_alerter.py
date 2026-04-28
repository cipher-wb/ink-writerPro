"""Tests for alerter."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ink_writer.debug.alerter import Alerter
from ink_writer.debug.config import DebugConfig
from ink_writer.debug.indexer import SCHEMA


def _seed(tmp_path: Path, severities: list[str]) -> None:
    debug_dir = tmp_path / ".ink-debug"
    debug_dir.mkdir(parents=True)
    db = debug_dir / "debug.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    rows = [
        ("2026-04-28T00:00:00Z", "r1", None, None, 1, "layer_c_invariant",
         "ink-write", "writer", f"writer.short_word_count", sev, "x", None, None)
        for sev in severities
    ]
    conn.executemany(
        "INSERT INTO incidents (ts, run_id, session_id, project, chapter, source, skill, step, "
        "kind, severity, message, evidence_json, trace_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()


def test_chapter_summary_with_warn(tmp_path: Path, capsys: pytest.CaptureFixture):
    _seed(tmp_path, ["warn", "warn", "info"])
    cfg = DebugConfig(project_root=tmp_path)
    Alerter(cfg).chapter_summary(run_id="r1")
    out = capsys.readouterr().out
    assert "warn" in out
    assert "writer.short_word_count" in out


def test_chapter_summary_disabled_when_master_off(tmp_path: Path, capsys: pytest.CaptureFixture):
    _seed(tmp_path, ["warn"])
    cfg = DebugConfig(project_root=tmp_path)
    cfg.master_enabled = False
    Alerter(cfg).chapter_summary(run_id="r1")
    assert capsys.readouterr().out == ""


def test_batch_report_writes_file(tmp_path: Path):
    _seed(tmp_path, ["warn"])
    cfg = DebugConfig(project_root=tmp_path)
    path = Alerter(cfg).batch_report(run_id="auto-batch-1")
    assert path is not None
    assert path.exists()
    assert path.parent.name == "reports"
    assert path.read_text(encoding="utf-8").startswith("#")
