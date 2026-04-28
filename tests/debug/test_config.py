"""Tests for ink_writer.debug.config."""
from __future__ import annotations

from pathlib import Path

import pytest

from ink_writer.debug.config import DebugConfig, load_config


def test_load_global_defaults(tmp_path: Path):
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    assert cfg.master_enabled is True
    assert cfg.layers.layer_a_hooks is True
    assert cfg.layers.layer_d_adversarial is False
    assert cfg.invariants["polish_diff"]["min_diff_chars"] == 50


def test_project_override_deep_merges(tmp_path: Path):
    debug_dir = tmp_path / ".ink-debug"
    debug_dir.mkdir()
    (debug_dir / "config.local.yaml").write_text(
        "invariants:\n  polish_diff:\n    min_diff_chars: 10\n",
        encoding="utf-8",
    )
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    assert cfg.invariants["polish_diff"]["min_diff_chars"] == 10
    # other fields preserved
    assert cfg.master_enabled is True


def test_env_var_overrides_master(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INK_DEBUG_OFF", "1")
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    assert cfg.master_enabled is False


def test_env_var_unset_preserves_master(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("INK_DEBUG_OFF", raising=False)
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    assert cfg.master_enabled is True


def test_severity_threshold_passes_warn(tmp_path: Path):
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=tmp_path)
    assert cfg.passes_threshold("warn", "sqlite_threshold") is True
    assert cfg.passes_threshold("info", "sqlite_threshold") is False
    assert cfg.passes_threshold("error", "stderr_threshold") is True
