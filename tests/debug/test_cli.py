"""Tests for ink_writer.debug.cli."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ink_writer.debug import cli
from ink_writer.debug.config import DebugConfig
from ink_writer.debug.indexer import SCHEMA


def _seed(tmp_path: Path) -> None:
    debug_dir = tmp_path / ".ink-debug"
    debug_dir.mkdir(parents=True)
    db = debug_dir / "debug.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO incidents (ts, run_id, source, skill, kind, severity, message) "
        "VALUES (?,?,?,?,?,?,?)",
        ("2026-04-28T00:00:00Z", "r1", "layer_c_invariant", "ink-write",
         "writer.short_word_count", "warn", "test"),
    )
    conn.commit()
    conn.close()


def test_status_prints_switches(tmp_path: Path, capsys: pytest.CaptureFixture):
    _seed(tmp_path)
    cli.cmd_status(project_root=tmp_path, global_yaml=Path("config/debug.yaml"))
    out = capsys.readouterr().out
    assert "master" in out
    assert "layer_a" in out
    assert "writer.short_word_count" in out


def test_report_writes_markdown(tmp_path: Path, capsys: pytest.CaptureFixture):
    _seed(tmp_path)
    path = cli.cmd_report(project_root=tmp_path, global_yaml=Path("config/debug.yaml"),
                          since="1d", run_id=None, severity="info")
    assert path.exists()
    assert path.read_text(encoding="utf-8").startswith("#")


def test_toggle_writes_local_yaml(tmp_path: Path):
    cli.cmd_toggle(project_root=tmp_path, global_yaml=Path("config/debug.yaml"),
                   key="layer_a", value=False)
    local = tmp_path / ".ink-debug" / "config.local.yaml"
    assert local.exists()
    assert "layer_a_hooks: false" in local.read_text(encoding="utf-8").lower()


def test_toggle_master(tmp_path: Path):
    cli.cmd_toggle(project_root=tmp_path, global_yaml=Path("config/debug.yaml"),
                   key="master", value=False)
    local = tmp_path / ".ink-debug" / "config.local.yaml"
    assert "master_enabled: false" in local.read_text(encoding="utf-8").lower()
