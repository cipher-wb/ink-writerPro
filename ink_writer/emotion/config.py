"""Configuration for the emotion-curve gate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

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


def load_config(path: Path | str | None = None) -> EmotionCurveConfig:
    """Load emotion-curve config from YAML, falling back to defaults."""
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)

    if not path.exists():
        return EmotionCurveConfig()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return EmotionCurveConfig()

    return EmotionCurveConfig(
        enabled=bool(raw.get("enabled", True)),
        variance_threshold=float(raw.get("variance_threshold", 0.15)),
        flat_segment_max=int(raw.get("flat_segment_max", 2)),
        corpus_similarity_threshold=float(raw.get("corpus_similarity_threshold", 0.8)),
        max_retries=int(raw.get("max_retries", 2)),
        score_threshold=float(raw.get("score_threshold", 60.0)),
    )
