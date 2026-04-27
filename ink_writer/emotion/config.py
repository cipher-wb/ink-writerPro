"""Configuration for the emotion-curve gate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ink_writer.platforms.resolver import resolve_platform_config

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "emotion-curve.yaml"
)


@dataclass
class EmotionCurveConfig:
    enabled: bool = True
    variance_threshold: float = 0.15
    flat_segment_max: int = 2
    corpus_similarity_threshold: float = 0.8
    max_retries: int = 2
    score_threshold: float = 60.0


def _resolve_platform_values(raw: dict, platform: str) -> dict:
    """Resolve platform overrides in the raw YAML dict."""
    if not isinstance(raw, dict):
        return raw
    return resolve_platform_config(raw, platform)


def load_config(path: Path | str | None = None, platform: str = "qidian") -> EmotionCurveConfig:
    """Load emotion-curve config from YAML, resolving platform overrides."""
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)

    if not path.exists():
        return EmotionCurveConfig()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return EmotionCurveConfig()

    resolved = _resolve_platform_values(raw, platform)

    return EmotionCurveConfig(
        enabled=bool(resolved.get("enabled", True)),
        variance_threshold=float(resolved.get("variance_threshold", 0.15)),
        flat_segment_max=int(resolved.get("flat_segment_max", 2)),
        corpus_similarity_threshold=float(resolved.get("corpus_similarity_threshold", 0.8)),
        max_retries=int(resolved.get("max_retries", 2)),
        score_threshold=float(resolved.get("score_threshold", 60.0)),
    )
