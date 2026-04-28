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


def test_layer_a_disabled_skips_hook_event(tmp_path: Path):
    cfg = _config(tmp_path)
    cfg.layers.layer_a_hooks = False
    coll = Collector(cfg)
    inc = Incident(
        ts="2026-04-28T14:23:51Z",
        run_id="r1",
        source="layer_a_hook",
        skill="claude-code",
        kind="hook.post_tool_use",
        severity="info",
        message="x",
    )
    coll.record(inc)
    assert not (tmp_path / ".ink-debug" / "events.jsonl").exists()


def test_layer_b_disabled_skips_checker_event(tmp_path: Path):
    cfg = _config(tmp_path)
    cfg.layers.layer_b_checker_router = False
    coll = Collector(cfg)
    inc = Incident(
        ts="2026-04-28T14:23:51Z",
        run_id="r1",
        source="layer_b_checker",
        skill="ink-write",
        kind="checker.consistency.character_drift",
        severity="warn",
        message="x",
    )
    coll.record(inc)
    assert not (tmp_path / ".ink-debug" / "events.jsonl").exists()


def test_layer_c_disabled_skips_invariant_event(tmp_path: Path):
    cfg = _config(tmp_path)
    cfg.layers.layer_c_invariants = False
    coll = Collector(cfg)
    coll.record(_incident())  # default source=layer_c_invariant
    assert not (tmp_path / ".ink-debug" / "events.jsonl").exists()


def test_meta_source_bypasses_layer_gates(tmp_path: Path):
    """Meta events must surface even when all layers are off."""
    cfg = _config(tmp_path)
    cfg.layers.layer_a_hooks = False
    cfg.layers.layer_b_checker_router = False
    cfg.layers.layer_c_invariants = False
    coll = Collector(cfg)
    inc = Incident(
        ts="2026-04-28T14:23:51Z",
        run_id="r1",
        source="meta",
        skill="x",
        kind="meta.invariant_crashed",
        severity="info",
        message="x",
    )
    coll.record(inc)
    assert (tmp_path / ".ink-debug" / "events.jsonl").exists()


def test_warn_does_not_trigger_stderr(tmp_path: Path, capsys: pytest.CaptureFixture):
    """severity=warn does NOT print to stderr (only error does, per default config)."""
    coll = Collector(_config(tmp_path))
    coll.record(_incident(severity="warn"))
    captured = capsys.readouterr()
    assert captured.err == ""


def test_unknown_kind_in_loose_mode_evidence_preserves_original(tmp_path: Path):
    """The synthesized meta incident's evidence carries the original kind."""
    cfg = _config(tmp_path)
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
    import json
    rec = json.loads(events_path.read_text(encoding="utf-8").splitlines()[0])
    assert rec["source"] == "meta"
    assert rec["evidence"]["original_kind"] == "totally.made.up"


def test_strict_mode_does_not_write_original(tmp_path: Path):
    """In strict mode, unknown kind raises BEFORE any write happens."""
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
    with pytest.raises(ValueError):
        coll.record(bogus)
    events_path = tmp_path / ".ink-debug" / "events.jsonl"
    assert not events_path.exists()


def test_swallows_internal_exceptions_writes_stderr_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
):
    """When BOTH _write_jsonl and _log_error fail, stderr fallback fires."""
    cfg = _config(tmp_path)
    coll = Collector(cfg)

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "open", boom)
    coll.record(_incident())  # MUST NOT raise
    captured = capsys.readouterr()
    assert "[debug.collector] internal error" in captured.err


def test_utf8_multibyte_round_trip(tmp_path: Path):
    """Chinese characters in message/evidence write and read back identically."""
    coll = Collector(_config(tmp_path))
    inc = Incident(
        ts="2026-04-28T14:23:51Z",
        run_id="r1",
        source="layer_c_invariant",
        skill="ink-write",
        kind="writer.short_word_count",
        severity="warn",
        message="字数低于 2200 字下限",
        evidence={"项目": "因果剑歌", "字数": 1500},
    )
    coll.record(inc)
    events_path = tmp_path / ".ink-debug" / "events.jsonl"
    import json
    rec = json.loads(events_path.read_text(encoding="utf-8").splitlines()[0])
    assert rec["message"] == "字数低于 2200 字下限"
    assert rec["evidence"]["项目"] == "因果剑歌"
    assert rec["evidence"]["字数"] == 1500
