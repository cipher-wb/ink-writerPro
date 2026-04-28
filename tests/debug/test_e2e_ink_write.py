"""End-to-end smoke: simulate writer/polish/review producing incidents, then status + report."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ink_writer.debug.collector import Collector
from ink_writer.debug.config import load_config
from ink_writer.debug.invariants.writer_word_count import check as check_words
from ink_writer.debug.invariants.polish_diff import check as check_polish
from ink_writer.debug.indexer import Indexer
from ink_writer.debug import cli


def test_full_write_path(tmp_path: Path, capsys: pytest.CaptureFixture):
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    coll = Collector(cfg)

    # 1. Simulate writer producing a too-short chapter.
    inc1 = check_words(text="x" * 1000, run_id="r1", chapter=1, min_words=2200, skill="ink-write")
    assert inc1 is not None
    coll.record(inc1)

    # 2. Simulate polish doing nothing.
    inc2 = check_polish(before="x" * 1000, after="x" * 1000, run_id="r1", chapter=1, min_diff_chars=50)
    assert inc2 is not None
    coll.record(inc2)

    # 3. events.jsonl exists with 2 lines.
    events = tmp_path / ".ink-debug" / "events.jsonl"
    assert events.exists()
    lines = events.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

    # 4. Sync to SQLite.
    Indexer(cfg).sync()
    db = tmp_path / ".ink-debug" / "debug.db"
    assert db.exists()
    count = sqlite3.connect(db).execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    assert count == 2

    # 5. /ink-debug-status equivalent.
    cli.cmd_status(project_root=tmp_path, global_yaml=Path("config/debug.yaml"))
    out = capsys.readouterr().out
    assert "writer.short_word_count" in out

    # 6. /ink-debug-report equivalent.
    md_path = cli.cmd_report(project_root=tmp_path, global_yaml=Path("config/debug.yaml"),
                              since="1d", run_id=None, severity="info")
    assert md_path.exists()
    md = md_path.read_text(encoding="utf-8")
    assert "writer.short_word_count" in md
    assert "polish.diff_too_small" in md
