"""Tests for plotline lifecycle config loading."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from ink_writer.plotline.config import (
    InactivityRules,
    PlotlineLifecycleConfig,
    load_config,
)


class TestInactivityRules:
    def test_defaults(self):
        rules = InactivityRules()
        assert rules.main_max_gap == 3
        assert rules.sub_max_gap == 8
        assert rules.dark_max_gap == 15

    def test_custom(self):
        rules = InactivityRules(main_max_gap=5, sub_max_gap=10, dark_max_gap=20)
        assert rules.main_max_gap == 5


class TestPlotlineLifecycleConfig:
    def test_defaults(self):
        cfg = PlotlineLifecycleConfig()
        assert cfg.enabled is True
        assert cfg.max_forced_advances_per_chapter == 2
        assert cfg.plan_injection_mode == "force"
        assert cfg.active_plotline_warn_limit == 10
        assert cfg.heatmap_bucket_size == 10

    def test_inactivity_rules_default(self):
        cfg = PlotlineLifecycleConfig()
        assert cfg.inactivity_rules.main_max_gap == 3


class TestLoadConfig:
    def test_missing_file_returns_defaults(self, tmp_path: Path):
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.enabled is True
        assert cfg.inactivity_rules.main_max_gap == 3

    def test_load_from_yaml(self, tmp_path: Path):
        yaml_path = tmp_path / "plotline.yaml"
        yaml_path.write_text(
            "enabled: false\n"
            "inactivity_rules:\n"
            "  main_max_gap: 5\n"
            "  sub_max_gap: 12\n"
            "  dark_max_gap: 25\n"
            "max_forced_advances_per_chapter: 3\n"
            "plan_injection_mode: warn\n"
            "active_plotline_warn_limit: 8\n"
        )
        cfg = load_config(yaml_path)
        assert cfg.enabled is False
        assert cfg.inactivity_rules.main_max_gap == 5
        assert cfg.inactivity_rules.sub_max_gap == 12
        assert cfg.inactivity_rules.dark_max_gap == 25
        assert cfg.max_forced_advances_per_chapter == 3
        assert cfg.plan_injection_mode == "warn"
        assert cfg.active_plotline_warn_limit == 8

    def test_empty_file_returns_defaults(self, tmp_path: Path):
        yaml_path = tmp_path / "empty.yaml"
        yaml_path.write_text("")
        cfg = load_config(yaml_path)
        assert cfg.enabled is True

    def test_invalid_yaml_returns_defaults(self, tmp_path: Path):
        yaml_path = tmp_path / "bad.yaml"
        yaml_path.write_text("- just a list")
        cfg = load_config(yaml_path)
        assert cfg.enabled is True

    def test_default_config_path_exists(self):
        from ink_writer.plotline.config import DEFAULT_CONFIG_PATH
        assert DEFAULT_CONFIG_PATH.name == "plotline-lifecycle.yaml"
