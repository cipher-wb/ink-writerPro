"""Tests for ink_writer.debug.collector."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ink_writer.debug.collector import Collector
from ink_writer.debug.config import DebugConfig
from ink_writer.debug.schema import Incident


def _config(tmp_path: Path, **overrides) -> DebugConfig:
    cfg = DebugConfig(project_root=tmp_path)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _incident(severity: str = "warn", kind: str = "writer.short_word_count") -> Incident:
    return Incident(
        ts="2026-04-28T14:23:51Z",
        run_id="r1",
        source="layer_c_invariant",
        skill="ink-write",
        kind=kind,
        severity=severity,
        message="test",
    )


def test_record_appends_to_jsonl(tmp_path: Path):
    coll = Collector(_config(tmp_path))
    coll.record(_incident())
    events_path = tmp_path / ".ink-debug" / "events.jsonl"
    assert events_path.exists()
    lines = events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["kind"] == "writer.short_word_count"


def test_master_disabled_skips_write(tmp_path: Path):
    cfg = _config(tmp_path)
    cfg.master_enabled = False
    coll = Collector(cfg)
    coll.record(_incident())
    assert not (tmp_path / ".ink-debug" / "events.jsonl").exists()


def test_below_jsonl_threshold_skipped(tmp_path: Path):
    cfg = _config(tmp_path)
    cfg.severity.jsonl_threshold = "warn"
    coll = Collector(cfg)
    coll.record(_incident(severity="info"))
    assert not (tmp_path / ".ink-debug" / "events.jsonl").exists()


def test_error_severity_writes_to_stderr(tmp_path: Path, capsys: pytest.CaptureFixture):
    coll = Collector(_config(tmp_path))
    coll.record(_incident(severity="error"))
    captured = capsys.readouterr()
    assert "error" in captured.err.lower() or "writer.short_word_count" in captured.err


def test_collector_swallows_internal_exceptions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = _config(tmp_path)
    coll = Collector(cfg)

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "open", boom)
    coll.record(_incident())  # MUST NOT raise


def test_unknown_kind_in_strict_mode_raises(tmp_path: Path):
    cfg = _config(tmp_path)
    cfg.strict_mode = True
    coll = Collector(cfg)
    bogus = Incident(
        ts="2026-04-28T14:23:51Z",
        run_id="r1",
        source="layer_c_invariant",
        skill="x",
        kind="totally.made.up",
        severity="info",
        message="x",
    )
    with pytest.raises(ValueError, match="unknown kind"):
        coll.record(bogus)


def test_unknown_kind_in_loose_mode_records_meta(tmp_path: Path):
    cfg = _config(tmp_path)
    cfg.strict_mode = False
    coll = Collector(cfg)
    bogus = Incident(
        ts="2026-04-28T14:23:51Z",
        run_id="r1",
        source="layer_c_invariant",
        skill="x",
        kind="totally.made.up",
        severity="info",
        message="x",
    )
    coll.record(bogus)
    events_path = tmp_path / ".ink-debug" / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    kinds = {json.loads(l)["kind"] for l in lines}
    assert "meta.unknown_kind" in kinds
