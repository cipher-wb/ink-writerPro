"""Configuration loader for the editor-wisdom module."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "editor-wisdom.yaml"


@dataclass
class InjectInto:
    context: bool = True
    writer: bool = True
    polish: bool = True


@dataclass
class DirectnessRecall:
    """v22 US-004: scene-aware simplicity recall config for writer-injection."""

    scene_modes: tuple[str, ...] = (
        "golden_three",
        "combat",
        "climax",
        "high_point",
        "slow_build",
        "emotional",
        "other",
    )
    floor_categories: tuple[str, ...] = ("simplicity",)
    floor_per_category: int = 5


@dataclass
class EditorWisdomConfig:
    enabled: bool = True
    retrieval_top_k: int = 5
    hard_gate_threshold: float = 0.75
    # US-015: split golden-three threshold into hard (blocking) + soft (target).
    # golden_three_threshold is kept for backward-compat (legacy single-value API).
    golden_three_threshold: float = 0.85
    golden_three_hard_threshold: float = 0.75
    golden_three_soft_threshold: float = 0.92
    inject_into: InjectInto = field(default_factory=InjectInto)
    # v22 US-004: 主题域注册表（从 config/editor-wisdom.yaml:categories 读取）。
    # 默认包含既有 10 类 + 4 类 prose_* + simplicity（与 05_extract_rules.CATEGORIES 对齐）。
    categories: tuple[str, ...] = (
        "opening", "hook", "golden_finger", "character", "pacing",
        "highpoint", "taboo", "genre", "ops", "misc",
        "prose_shot", "prose_sensory", "prose_rhythm", "prose_density",
        "simplicity",
    )
    directness_recall: DirectnessRecall = field(default_factory=DirectnessRecall)


def load_config(path: Path | str | None = None) -> EditorWisdomConfig:
    """Load editor-wisdom config from YAML, falling back to defaults."""
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)

    if not path.exists():
        return EditorWisdomConfig()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return EditorWisdomConfig()

    inject_raw = raw.get("inject_into", {})
    if not isinstance(inject_raw, dict):
        inject_raw = {}

    inject = InjectInto(
        context=bool(inject_raw.get("context", True)),
        writer=bool(inject_raw.get("writer", True)),
        polish=bool(inject_raw.get("polish", True)),
    )

    # v22 US-004: 读取主题域注册表；无配置时走默认元组。对非 list / 非 str 元素过滤掉。
    raw_cats = raw.get("categories")
    cat_default = EditorWisdomConfig().categories
    if isinstance(raw_cats, list):
        cats = tuple(str(c) for c in raw_cats if isinstance(c, str) and c.strip())
        if not cats:
            cats = cat_default
    else:
        cats = cat_default

    # v22 US-004: 读取 directness_recall；缺失或字段不合法时走 DirectnessRecall() 默认
    raw_directness = raw.get("directness_recall")
    if isinstance(raw_directness, dict):
        scene_raw = raw_directness.get("scene_modes")
        floor_raw = raw_directness.get("floor_categories")
        per_raw = raw_directness.get("floor_per_category")
        scene_modes = (
            tuple(str(s) for s in scene_raw if isinstance(s, str) and s.strip())
            if isinstance(scene_raw, list)
            else DirectnessRecall().scene_modes
        )
        floor_categories = (
            tuple(str(c) for c in floor_raw if isinstance(c, str) and c.strip())
            if isinstance(floor_raw, list)
            else DirectnessRecall().floor_categories
        )
        try:
            floor_per_category = int(per_raw) if per_raw is not None else DirectnessRecall().floor_per_category
        except (TypeError, ValueError):
            floor_per_category = DirectnessRecall().floor_per_category
        directness_recall = DirectnessRecall(
            scene_modes=scene_modes or DirectnessRecall().scene_modes,
            floor_categories=floor_categories or DirectnessRecall().floor_categories,
            floor_per_category=floor_per_category,
        )
    else:
        directness_recall = DirectnessRecall()

    return EditorWisdomConfig(
        enabled=bool(raw.get("enabled", True)),
        retrieval_top_k=int(raw.get("retrieval_top_k", 5)),
        hard_gate_threshold=float(raw.get("hard_gate_threshold", 0.75)),
        golden_three_threshold=float(raw.get("golden_three_threshold", 0.85)),
        golden_three_hard_threshold=float(raw.get("golden_three_hard_threshold", 0.75)),
        golden_three_soft_threshold=float(raw.get("golden_three_soft_threshold", 0.92)),
        inject_into=inject,
        categories=cats,
        directness_recall=directness_recall,
    )
