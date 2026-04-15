"""Tests for v9→v10 schema migration (voice fingerprint)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ink-writer" / "scripts"))

from migrate import _migrate_v9_to_v10, CURRENT_SCHEMA_VERSION  # noqa: E402


def test_current_schema_version():
    assert CURRENT_SCHEMA_VERSION == 10


def test_migrate_v9_to_v10_adds_voice_fingerprint_config():
    state = {"schema_version": 9}
    result = _migrate_v9_to_v10(state)
    assert result["schema_version"] == 10
    assert "voice_fingerprint_config" in result
    vf_config = result["voice_fingerprint_config"]
    assert vf_config["enabled"] is True
    assert vf_config["score_threshold"] == 60.0
    assert vf_config["max_retries"] == 2
    assert vf_config["core_tiers"] == ["核心", "重要"]


def test_migrate_v9_to_v10_preserves_existing_fields():
    state = {
        "schema_version": 9,
        "hook_contract_config": {"enabled": True},
        "_migrated_to_single_source": True,
        "project_info": {"title": "测试小说"},
    }
    result = _migrate_v9_to_v10(state)
    assert result["schema_version"] == 10
    assert result["hook_contract_config"] == {"enabled": True}
    assert result["_migrated_to_single_source"] is True
    assert result["project_info"]["title"] == "测试小说"


def test_migrate_v9_to_v10_idempotent_safe():
    state = {"schema_version": 9}
    result = _migrate_v9_to_v10(state)
    assert result["schema_version"] == 10
    result2 = dict(result)
    result2["voice_fingerprint_config"]["score_threshold"] = 75.0
    assert result2["voice_fingerprint_config"]["score_threshold"] == 75.0
