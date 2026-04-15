"""Tests for foreshadow lifecycle config loading."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from ink_writer.foreshadow.config import (
    ForeshadowLifecycleConfig,
    PriorityOverdueRules,
    load_config,
)


class TestDefaultConfig:
    def test_default_values(self):
        cfg = ForeshadowLifecycleConfig()
        assert cfg.enabled is True
        assert cfg.overdue_grace_chapters == 10
        assert cfg.silence_threshold_chapters == 30
        assert cfg.max_forced_payoffs_per_chapter == 2
        assert cfg.plan_injection_mode == "force"
        assert cfg.active_foreshadow_warn_limit == 15
        assert cfg.heatmap_bucket_size == 10

    def test_default_priority_rules(self):
        rules = PriorityOverdueRules()
        assert rules.p0_threshold == 80
        assert rules.p0_grace == 5
        assert rules.p1_threshold == 50
        assert rules.p1_grace == 10
        assert rules.p2_grace == 20


class TestLoadConfig:
    def test_load_nonexistent_path_returns_defaults(self):
        cfg = load_config("/nonexistent/path.yaml")
        assert cfg.enabled is True
        assert cfg.overdue_grace_chapters == 10

    def test_load_empty_yaml_returns_defaults(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("")
            f.flush()
            cfg = load_config(f.name)
        assert cfg.enabled is True

    def test_load_valid_yaml(self):
        data = {
            "enabled": False,
            "overdue_grace_chapters": 15,
            "silence_threshold_chapters": 40,
            "priority_overdue_rules": {
                "p0_threshold": 90,
                "p0_grace": 3,
                "p1_threshold": 60,
                "p1_grace": 8,
                "p2_grace": 25,
            },
            "max_forced_payoffs_per_chapter": 3,
            "plan_injection_mode": "warn",
            "active_foreshadow_warn_limit": 20,
            "heatmap_bucket_size": 5,
        }
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            f.flush()
            cfg = load_config(f.name)

        assert cfg.enabled is False
        assert cfg.overdue_grace_chapters == 15
        assert cfg.silence_threshold_chapters == 40
        assert cfg.priority_overdue_rules.p0_threshold == 90
        assert cfg.priority_overdue_rules.p0_grace == 3
        assert cfg.priority_overdue_rules.p1_threshold == 60
        assert cfg.priority_overdue_rules.p1_grace == 8
        assert cfg.priority_overdue_rules.p2_grace == 25
        assert cfg.max_forced_payoffs_per_chapter == 3
        assert cfg.plan_injection_mode == "warn"
        assert cfg.active_foreshadow_warn_limit == 20
        assert cfg.heatmap_bucket_size == 5

    def test_load_partial_yaml_fills_defaults(self):
        data = {"overdue_grace_chapters": 20}
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(data, f)
            f.flush()
            cfg = load_config(f.name)

        assert cfg.overdue_grace_chapters == 20
        assert cfg.silence_threshold_chapters == 30  # default
        assert cfg.enabled is True  # default

    def test_load_from_project_config(self):
        cfg = load_config(Path(__file__).resolve().parent.parent.parent / "config" / "foreshadow-lifecycle.yaml")
        assert cfg.enabled is True
        assert cfg.priority_overdue_rules.p0_grace == 5
