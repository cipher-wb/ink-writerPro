#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Centralized context template weights.
"""

from __future__ import annotations


DEFAULT_TEMPLATE = "plot"

# US-008: reflections 作为 L2 memory 的最小预算占比（每个模板最少 0.05 = 5% 的
# max_chars，≈400 chars @ 8000 基线）。把 reflections 放进 TEMPLATE_WEIGHTS 而非
# EXTRA_SECTIONS，确保在所有模板/阶段下都能分到不小于 0.05 的独立预算。
REFLECTIONS_WEIGHT_FLOOR: float = 0.05

TEMPLATE_WEIGHTS: dict[str, dict[str, float]] = {
    "plot": {"core": 0.40, "scene": 0.35, "global": 0.25, "reflections": REFLECTIONS_WEIGHT_FLOOR},
    "battle": {"core": 0.35, "scene": 0.45, "global": 0.20, "reflections": REFLECTIONS_WEIGHT_FLOOR},
    "emotion": {"core": 0.45, "scene": 0.35, "global": 0.20, "reflections": REFLECTIONS_WEIGHT_FLOOR},
    "transition": {"core": 0.50, "scene": 0.25, "global": 0.25, "reflections": REFLECTIONS_WEIGHT_FLOOR},
}

TEMPLATE_WEIGHTS_DYNAMIC_DEFAULT: dict[str, dict[str, dict[str, float]]] = {
    "early": {
        "plot": {"core": 0.48, "scene": 0.39, "global": 0.13, "reflections": REFLECTIONS_WEIGHT_FLOOR},
        "battle": {"core": 0.42, "scene": 0.50, "global": 0.08, "reflections": REFLECTIONS_WEIGHT_FLOOR},
        "emotion": {"core": 0.52, "scene": 0.38, "global": 0.10, "reflections": REFLECTIONS_WEIGHT_FLOOR},
        "transition": {"core": 0.56, "scene": 0.28, "global": 0.16, "reflections": REFLECTIONS_WEIGHT_FLOOR},
    },
    "mid": {
        "plot": {"core": 0.40, "scene": 0.35, "global": 0.25, "reflections": REFLECTIONS_WEIGHT_FLOOR},
        "battle": {"core": 0.35, "scene": 0.45, "global": 0.20, "reflections": REFLECTIONS_WEIGHT_FLOOR},
        "emotion": {"core": 0.45, "scene": 0.35, "global": 0.20, "reflections": REFLECTIONS_WEIGHT_FLOOR},
        "transition": {"core": 0.50, "scene": 0.25, "global": 0.25, "reflections": REFLECTIONS_WEIGHT_FLOOR},
    },
    "late": {
        "plot": {"core": 0.36, "scene": 0.29, "global": 0.35, "reflections": REFLECTIONS_WEIGHT_FLOOR},
        "battle": {"core": 0.31, "scene": 0.39, "global": 0.30, "reflections": REFLECTIONS_WEIGHT_FLOOR},
        "emotion": {"core": 0.41, "scene": 0.29, "global": 0.30, "reflections": REFLECTIONS_WEIGHT_FLOOR},
        "transition": {"core": 0.46, "scene": 0.21, "global": 0.33, "reflections": REFLECTIONS_WEIGHT_FLOOR},
    },
}

