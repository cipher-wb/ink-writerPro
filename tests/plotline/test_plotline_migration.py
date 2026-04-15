"""Tests for v10→v11 schema migration (plotline lifecycle)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ink-writer" / "scripts"))

from migrate import _migrate_v10_to_v11, CURRENT_SCHEMA_VERSION  # noqa: E402


def test_current_schema_version():
    assert CURRENT_SCHEMA_VERSION == 11


def test_migrate_v10_to_v11_adds_plotline_lifecycle_config():
    state = {"schema_version": 10}
    result = _migrate_v10_to_v11(state)
    assert result["schema_version"] == 11
    assert "plotline_lifecycle_config" in result


def test_plotline_lifecycle_config_fields():
    state = {"schema_version": 10}
    result = _migrate_v10_to_v11(state)
    cfg = result["plotline_lifecycle_config"]
    assert cfg["enabled"] is True
    assert cfg["inactivity_rules"]["main_max_gap"] == 3
    assert cfg["inactivity_rules"]["sub_max_gap"] == 8
    assert cfg["inactivity_rules"]["dark_max_gap"] == 15
    assert cfg["max_forced_advances_per_chapter"] == 2
    assert cfg["plan_injection_mode"] == "force"


def test_plotline_registry_added_to_plot_threads():
    state = {"schema_version": 10, "plot_threads": {"active_threads": [], "foreshadowing": []}}
    result = _migrate_v10_to_v11(state)
    assert "plotline_registry" in result["plot_threads"]
    assert result["plot_threads"]["plotline_registry"] == []


def test_plotline_registry_preserves_existing():
    existing = [{"id": "pl_1", "title": "existing"}]
    state = {
        "schema_version": 10,
        "plot_threads": {"plotline_registry": existing},
    }
    result = _migrate_v10_to_v11(state)
    assert result["plot_threads"]["plotline_registry"] == existing


def test_migrate_idempotent_plot_threads():
    state = {"schema_version": 10}
    result = _migrate_v10_to_v11(state)
    assert "plot_threads" in result
    assert result["plot_threads"]["plotline_registry"] == []
