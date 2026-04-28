"""Tests for ink_writer.debug.indexer."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ink_writer.debug.config import DebugConfig
from ink_writer.debug.indexer import Indexer


def _seed_jsonl(tmp_path: Path, *records: dict) -> Path:
    debug_dir = tmp_path / ".ink-debug"
    debug_dir.mkdir(parents=True)
    events = debug_dir / "events.jsonl"
    with events.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return events


def _config(tmp_path: Path, sqlite_threshold: str = "warn") -> DebugConfig:
    cfg = DebugConfig(project_root=tmp_path)
    cfg.severity.sqlite_threshold = sqlite_threshold
    return cfg


def test_indexer_creates_schema(tmp_path: Path):
    _seed_jsonl(tmp_path)  # empty
    idx = Indexer(_config(tmp_path))
    idx.sync()
    db = tmp_path / ".ink-debug" / "debug.db"
    assert db.exists()
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "incidents" in tables
    assert "indexer_watermark" in tables


def test_indexer_only_indexes_above_threshold(tmp_path: Path):
    _seed_jsonl(
        tmp_path,
        {"ts": "2026-04-28T00:00:00Z", "run_id": "r1", "source": "layer_c_invariant",
         "skill": "x", "kind": "writer.short_word_count", "severity": "info", "message": "i"},
        {"ts": "2026-04-28T00:00:01Z", "run_id": "r1", "source": "layer_c_invariant",
         "skill": "x", "kind": "writer.short_word_count", "severity": "warn", "message": "w"},
        {"ts": "2026-04-28T00:00:02Z", "run_id": "r1", "source": "layer_c_invariant",
         "skill": "x", "kind": "writer.short_word_count", "severity": "error", "message": "e"},
    )
    idx = Indexer(_config(tmp_path, sqlite_threshold="warn"))
    idx.sync()
    db = tmp_path / ".ink-debug" / "debug.db"
    rows = list(sqlite3.connect(db).execute("SELECT severity FROM incidents ORDER BY ts"))
    assert rows == [("warn",), ("error",)]


def test_indexer_is_incremental(tmp_path: Path):
    events = _seed_jsonl(
        tmp_path,
        {"ts": "2026-04-28T00:00:00Z", "run_id": "r1", "source": "layer_c_invariant",
         "skill": "x", "kind": "writer.short_word_count", "severity": "warn", "message": "1"},
    )
    idx = Indexer(_config(tmp_path))
    idx.sync()

    with events.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": "2026-04-28T00:00:01Z", "run_id": "r1", "source": "layer_c_invariant",
            "skill": "x", "kind": "writer.short_word_count", "severity": "warn", "message": "2",
        }, ensure_ascii=False) + "\n")

    idx.sync()
    db = tmp_path / ".ink-debug" / "debug.db"
    count = sqlite3.connect(db).execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    assert count == 2


def test_indexer_skips_corrupted_lines(tmp_path: Path):
    debug_dir = tmp_path / ".ink-debug"
    debug_dir.mkdir(parents=True)
    events = debug_dir / "events.jsonl"
    events.write_text(
        '{"ts":"2026-04-28T00:00:00Z","run_id":"r1","source":"layer_c_invariant",'
        '"skill":"x","kind":"writer.short_word_count","severity":"warn","message":"1"}\n'
        'not-json-at-all\n'
        '{"ts":"2026-04-28T00:00:02Z","run_id":"r1","source":"layer_c_invariant",'
        '"skill":"x","kind":"writer.short_word_count","severity":"warn","message":"2"}\n',
        encoding="utf-8",
    )
    Indexer(_config(tmp_path)).sync()
    db = tmp_path / ".ink-debug" / "debug.db"
    count = sqlite3.connect(db).execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    assert count == 2
