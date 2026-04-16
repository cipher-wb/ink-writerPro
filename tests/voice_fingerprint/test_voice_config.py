"""Tests for voice fingerprint config loading."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from ink_writer.voice_fingerprint.config import (
    DeviationThresholds,
    LearningConfig,
    VoiceFingerprintConfig,
    load_config,
)


def test_default_config():
    cfg = VoiceFingerprintConfig()
    assert cfg.enabled is True
    assert cfg.score_threshold == 60.0
    assert cfg.max_retries == 2
    assert cfg.core_tiers == ["核心", "重要"]


def test_default_deviation_thresholds():
    t = DeviationThresholds()
    assert t.catchphrase_absence_chapters == 3
    assert t.vocabulary_level_mismatch == 0.4
    assert t.forbidden_expression_severity == "critical"
    assert t.tone_drift_threshold == 0.5
    assert t.distinctiveness_min_diff == 0.3


def test_default_learning_config():
    lc = LearningConfig()
    assert lc.min_dialogue_lines == 5
    assert lc.auto_learn_on_first_appearance is True
    assert lc.append_only is True
    assert lc.max_catchphrases == 5


def test_load_config_missing_file():
    cfg = load_config("/nonexistent/path.yaml")
    assert isinstance(cfg, VoiceFingerprintConfig)
    assert cfg.enabled is True


def test_load_config_from_yaml():
    data = {
        "enabled": False,
        "score_threshold": 75.0,
        "max_retries": 3,
        "deviation_thresholds": {
            "catchphrase_absence_chapters": 5,
            "vocabulary_level_mismatch": 0.6,
            "forbidden_expression_severity": "high",
        },
        "learning": {
            "min_dialogue_lines": 3,
            "append_only": False,
            "max_catchphrases": 10,
        },
        "core_tiers": ["核心"],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f, allow_unicode=True)
        f.flush()
        cfg = load_config(f.name)

    assert cfg.enabled is False
    assert cfg.score_threshold == 75.0
    assert cfg.max_retries == 3
    assert cfg.deviation_thresholds.catchphrase_absence_chapters == 5
    assert cfg.deviation_thresholds.vocabulary_level_mismatch == 0.6
    assert cfg.deviation_thresholds.forbidden_expression_severity == "high"
    assert cfg.learning.min_dialogue_lines == 3
    assert cfg.learning.append_only is False
    assert cfg.learning.max_catchphrases == 10
    assert cfg.core_tiers == ["核心"]


def test_load_config_invalid_yaml():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("just a string\n")
        f.flush()
        cfg = load_config(f.name)

    assert isinstance(cfg, VoiceFingerprintConfig)
    assert cfg.enabled is True


def test_load_config_default_path():
    cfg = load_config()
    assert isinstance(cfg, VoiceFingerprintConfig)
