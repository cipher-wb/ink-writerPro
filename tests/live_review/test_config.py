"""US-LR-002: live-review.yaml 配置加载。"""
from __future__ import annotations

from pathlib import Path

from ink_writer.live_review.config import LiveReviewConfig, load_config


def test_load_default_when_missing(tmp_path):
    cfg = load_config(tmp_path / "nonexistent.yaml")
    assert cfg.enabled is True
    assert cfg.model == "claude-sonnet-4-6"
    assert cfg.hard_gate_threshold == 0.65
    assert cfg.batch.resume_from_jsonl is True
    assert cfg.inject_into.init is True


def test_load_full_yaml(tmp_path):
    p = tmp_path / "lr.yaml"
    p.write_text(
        "enabled: true\n"
        "model: claude-haiku-4-5\n"
        "hard_gate_threshold: 0.70\n"
        "init_top_k: 5\n"
        "batch:\n  resume_from_jsonl: false\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.model == "claude-haiku-4-5"
    assert cfg.hard_gate_threshold == 0.70
    assert cfg.init_top_k == 5
    assert cfg.batch.resume_from_jsonl is False
    # 未提供字段回落默认
    assert cfg.batch.skip_failed is True
    assert cfg.golden_three_threshold == 0.75


def test_disabled_forces_inject_false(tmp_path):
    """enabled=false 时 inject_into.init/review 强制 false 即使 yaml 写 true。"""
    p = tmp_path / "lr.yaml"
    p.write_text(
        "enabled: false\ninject_into:\n  init: true\n  review: true\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.enabled is False
    assert cfg.inject_into.init is False
    assert cfg.inject_into.review is False


def test_partial_yaml_falls_through_defaults(tmp_path):
    """缺字段全部回落默认值，不抛 KeyError。"""
    p = tmp_path / "lr.yaml"
    p.write_text("model: custom-model\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.model == "custom-model"
    assert cfg.hard_gate_threshold == 0.65
    assert cfg.batch.input_dir == "~/Desktop/星河审稿"


def test_real_config_file_loads():
    """实际 config/live-review.yaml 应能成功加载（实施时已写）。"""
    cfg = load_config(Path("config/live-review.yaml"))
    assert isinstance(cfg, LiveReviewConfig)
    assert cfg.enabled is True
