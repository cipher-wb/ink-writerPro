"""Configuration for the anti-detection sentence diversity hard gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "anti-detection.yaml"
)


@dataclass
class ZeroToleranceRule:
    id: str
    description: str
    patterns: list[str] = field(default_factory=list)


@dataclass
class AntiDetectionConfig:
    enabled: bool = True
    score_threshold: float = 70.0
    golden_three_threshold: float = 80.0
    max_retries: int = 1

    sentence_cv_min: float = 0.35
    sentence_mean_min: float = 18.0
    short_sentence_ratio_max: float = 0.25
    long_sentence_ratio_min: float = 0.15

    single_sentence_paragraph_ratio_min: float = 0.20
    paragraph_cv_min: float = 0.40

    dialogue_ratio_min: float = 0.10

    exclamation_density_min: float = 1.5
    ellipsis_density_min: float = 1.0
    question_density_min: float = 2.0
    total_emotion_punctuation_min: float = 5.0

    causal_density_max: float = 1.0
    conjunction_density_max: float = 2.5

    zero_tolerance: list[ZeroToleranceRule] = field(default_factory=list)


_SCALAR_FIELDS = {
    "enabled", "score_threshold", "golden_three_threshold", "max_retries",
    "sentence_cv_min", "sentence_mean_min", "short_sentence_ratio_max",
    "long_sentence_ratio_min", "single_sentence_paragraph_ratio_min",
    "paragraph_cv_min", "dialogue_ratio_min", "exclamation_density_min",
    "ellipsis_density_min", "question_density_min",
    "total_emotion_punctuation_min", "causal_density_max",
    "conjunction_density_max",
}


def load_config(path: Path | str | None = None) -> AntiDetectionConfig:
    """Load anti-detection config from YAML, falling back to defaults."""
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)

    if not path.exists():
        return AntiDetectionConfig()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return AntiDetectionConfig()

    kwargs: dict = {}
    for k, v in raw.items():
        if k in _SCALAR_FIELDS:
            kwargs[k] = type(getattr(AntiDetectionConfig, k, v))(v)

    zt_raw = raw.get("zero_tolerance", [])
    if isinstance(zt_raw, list):
        rules = []
        for item in zt_raw:
            if isinstance(item, dict):
                rules.append(ZeroToleranceRule(
                    id=str(item.get("id", "UNKNOWN")),
                    description=str(item.get("description", "")),
                    patterns=list(item.get("patterns", [])),
                ))
        kwargs["zero_tolerance"] = rules

    return AntiDetectionConfig(**kwargs)
