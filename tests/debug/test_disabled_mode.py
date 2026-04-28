"""Disabled mode: master_enabled=false → no events written, no summary printed."""
from __future__ import annotations

from pathlib import Path

import pytest

from ink_writer.debug.alerter import Alerter
from ink_writer.debug.collector import Collector
from ink_writer.debug.config import load_config
from ink_writer.debug.invariants.writer_word_count import check as check_words


def test_master_disabled_via_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                 capsys: pytest.CaptureFixture):
    monkeypatch.setenv("INK_DEBUG_OFF", "1")
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    coll = Collector(cfg)
    inc = check_words(text="x" * 100, run_id="r1", chapter=1, min_words=2200, skill="ink-write")
    coll.record(inc)
    assert not (tmp_path / ".ink-debug" / "events.jsonl").exists()


def test_alerter_silent_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                      capsys: pytest.CaptureFixture):
    monkeypatch.setenv("INK_DEBUG_OFF", "1")
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    Alerter(cfg).chapter_summary(run_id="r1")
    out = capsys.readouterr().out
    assert out == ""


def test_delete_debug_dir_does_not_break(tmp_path: Path):
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    Collector(cfg).record(check_words(
        text="x" * 100, run_id="r1", chapter=1, min_words=2200, skill="ink-write",
    ))
    assert (tmp_path / ".ink-debug" / "events.jsonl").exists()
    import shutil
    shutil.rmtree(tmp_path / ".ink-debug")
    # Re-record: directory should be auto-recreated.
    Collector(cfg).record(check_words(
        text="x" * 100, run_id="r2", chapter=2, min_words=2200, skill="ink-write",
    ))
    assert (tmp_path / ".ink-debug" / "events.jsonl").exists()
