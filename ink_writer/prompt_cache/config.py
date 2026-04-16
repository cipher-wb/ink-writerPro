"""Prompt cache configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class PromptCacheConfig:
    enabled: bool = True
    min_cacheable_tokens: int = 1024
    stable_segments: list[str] = field(
        default_factory=lambda: [
            "system_prompt",
            "character_archive",
            "worldbuilding",
            "style_guide",
            "power_system",
            "iron_laws",
            "editor_wisdom_rules",
        ]
    )
    volatile_segments: list[str] = field(
        default_factory=lambda: [
            "chapter_outline",
            "recent_summaries",
            "protagonist_state",
            "scene_context",
            "alerts",
        ]
    )
    metrics_db_path: Optional[str] = None


def load_config(
    config_path: Optional[Path] = None,
) -> PromptCacheConfig:
    if config_path is None:
        candidates = [
            Path("config/prompt-cache.yaml"),
            Path(__file__).resolve().parents[2] / "config" / "prompt-cache.yaml",
        ]
        for c in candidates:
            if c.exists():
                config_path = c
                break

    if config_path is None or not config_path.exists():
        return PromptCacheConfig()

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    defaults = PromptCacheConfig()
    return PromptCacheConfig(
        enabled=data.get("enabled", True),
        min_cacheable_tokens=data.get("min_cacheable_tokens", 1024),
        stable_segments=data.get("stable_segments", defaults.stable_segments),
        volatile_segments=data.get("volatile_segments", defaults.volatile_segments),
        metrics_db_path=data.get("metrics_db_path"),
    )
