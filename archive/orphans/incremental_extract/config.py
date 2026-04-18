"""Incremental extraction configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class IncrementalExtractConfig:
    enabled: bool = True
    diff_confidence_threshold: float = 0.8
    skip_unchanged_entities: bool = True
    always_extract_protagonist: bool = True
    max_prior_state_age: int = 5


def load_config(
    config_path: Optional[Path] = None,
) -> IncrementalExtractConfig:
    if config_path is None:
        candidates = [
            Path("config/incremental-extract.yaml"),
            Path(__file__).resolve().parents[2] / "config" / "incremental-extract.yaml",
        ]
        for c in candidates:
            if c.exists():
                config_path = c
                break

    if config_path is None or not config_path.exists():
        return IncrementalExtractConfig()

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return IncrementalExtractConfig(
        enabled=data.get("enabled", True),
        diff_confidence_threshold=data.get("diff_confidence_threshold", 0.8),
        skip_unchanged_entities=data.get("skip_unchanged_entities", True),
        always_extract_protagonist=data.get("always_extract_protagonist", True),
        max_prior_state_age=data.get("max_prior_state_age", 5),
    )
