"""Tests for editor-wisdom config loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ink_writer.editor_wisdom.config import (
    EditorWisdomConfig,
    InjectInto,
    load_config,
)


@pytest.fixture()
def default_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "editor-wisdom.yaml"
    p.write_text(
        yaml.dump({
            "enabled": True,
            "retrieval_top_k": 5,
            "hard_gate_threshold": 0.75,
            "golden_three_threshold": 0.85,
            "inject_into": {"context": True, "writer": True, "polish": True},
        }),
        encoding="utf-8",
    )
    return p


def test_load_default_yaml(default_yaml: Path) -> None:
    cfg = load_config(default_yaml)
    assert cfg.enabled is True
    assert cfg.retrieval_top_k == 5
    assert cfg.hard_gate_threshold == 0.75
    assert cfg.golden_three_threshold == 0.85
    assert cfg.inject_into.context is True
    assert cfg.inject_into.writer is True
    assert cfg.inject_into.polish is True


def test_load_missing_file(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "nonexistent.yaml")
    assert cfg == EditorWisdomConfig()


def test_load_custom_values(tmp_path: Path) -> None:
    p = tmp_path / "custom.yaml"
    p.write_text(
        yaml.dump({
            "enabled": False,
            "retrieval_top_k": 10,
            "hard_gate_threshold": 0.5,
            "golden_three_threshold": 0.9,
            "inject_into": {"context": False, "writer": True, "polish": False},
        }),
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.enabled is False
    assert cfg.retrieval_top_k == 10
    assert cfg.hard_gate_threshold == 0.5
    assert cfg.golden_three_threshold == 0.9
    assert cfg.inject_into.context is False
    assert cfg.inject_into.writer is True
    assert cfg.inject_into.polish is False


def test_type_coercion(tmp_path: Path) -> None:
    p = tmp_path / "coerce.yaml"
    p.write_text(
        yaml.dump({
            "enabled": 1,
            "retrieval_top_k": "7",
            "hard_gate_threshold": "0.6",
            "golden_three_threshold": "0.8",
            "inject_into": {"context": 0, "writer": 1, "polish": 0},
        }),
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.enabled is True
    assert cfg.retrieval_top_k == 7
    assert isinstance(cfg.retrieval_top_k, int)
    assert cfg.hard_gate_threshold == pytest.approx(0.6)
    assert isinstance(cfg.hard_gate_threshold, float)
    assert cfg.inject_into.context is False
    assert cfg.inject_into.writer is True


def test_missing_fields_use_defaults(tmp_path: Path) -> None:
    p = tmp_path / "partial.yaml"
    p.write_text(yaml.dump({"enabled": False}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.enabled is False
    assert cfg.retrieval_top_k == 5
    assert cfg.hard_gate_threshold == 0.75
    assert cfg.golden_three_threshold == 0.85
    assert cfg.inject_into == InjectInto()


def test_empty_yaml_returns_defaults(tmp_path: Path) -> None:
    p = tmp_path / "empty.yaml"
    p.write_text("", encoding="utf-8")
    cfg = load_config(p)
    assert cfg == EditorWisdomConfig()


def test_invalid_inject_into_returns_defaults(tmp_path: Path) -> None:
    p = tmp_path / "bad_inject.yaml"
    p.write_text(
        yaml.dump({"enabled": True, "inject_into": "not_a_dict"}),
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.inject_into == InjectInto()


def test_actual_config_file_loads() -> None:
    actual = Path(__file__).resolve().parent.parent.parent / "config" / "editor-wisdom.yaml"
    if actual.exists():
        cfg = load_config(actual)
        assert cfg.enabled is True
        assert cfg.retrieval_top_k == 5
