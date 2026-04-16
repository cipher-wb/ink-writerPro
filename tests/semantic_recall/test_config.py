"""Tests for SemanticRecallConfig."""

from __future__ import annotations

import pytest
from pathlib import Path

pytest.importorskip("numpy")

from ink_writer.semantic_recall.config import SemanticRecallConfig


class TestSemanticRecallConfigDefaults:
    def test_default_values(self):
        cfg = SemanticRecallConfig()
        assert cfg.enabled is True
        assert cfg.model_name == "BAAI/bge-small-zh-v1.5"
        assert cfg.semantic_top_k == 8
        assert cfg.recent_n == 5
        assert cfg.entity_forced_max == 10
        assert cfg.final_top_k == 10
        assert cfg.min_semantic_score == 0.3
        assert cfg.entity_boost_weight == 0.15
        assert cfg.max_pack_chars == 3000


class TestSemanticRecallConfigFromYaml:
    def test_loads_from_yaml(self, tmp_path):
        yaml_file = tmp_path / "semantic-recall.yaml"
        yaml_file.write_text(
            "enabled: false\nsemantic_top_k: 12\nrecent_n: 3\n",
            encoding="utf-8",
        )
        cfg = SemanticRecallConfig.from_yaml(yaml_file)
        assert cfg.enabled is False
        assert cfg.semantic_top_k == 12
        assert cfg.recent_n == 3
        assert cfg.final_top_k == 10  # default

    def test_missing_file_returns_defaults(self, tmp_path):
        cfg = SemanticRecallConfig.from_yaml(tmp_path / "nonexistent.yaml")
        assert cfg.enabled is True
        assert cfg.semantic_top_k == 8

    def test_ignores_unknown_keys(self, tmp_path):
        yaml_file = tmp_path / "semantic-recall.yaml"
        yaml_file.write_text("unknown_key: 42\nenabled: true\n", encoding="utf-8")
        cfg = SemanticRecallConfig.from_yaml(yaml_file)
        assert cfg.enabled is True
        assert not hasattr(cfg, "unknown_key")


class TestSemanticRecallConfigFromProjectRoot:
    def test_loads_from_config_dir(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "semantic-recall.yaml").write_text(
            "semantic_top_k: 20\n", encoding="utf-8"
        )
        cfg = SemanticRecallConfig.from_project_root(tmp_path)
        assert cfg.semantic_top_k == 20

    def test_loads_from_ink_dir(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        (ink_dir / "semantic-recall.yaml").write_text(
            "recent_n: 10\n", encoding="utf-8"
        )
        cfg = SemanticRecallConfig.from_project_root(tmp_path)
        assert cfg.recent_n == 10

    def test_fallback_to_defaults(self, tmp_path):
        cfg = SemanticRecallConfig.from_project_root(tmp_path)
        assert cfg.enabled is True
        assert cfg.semantic_top_k == 8
