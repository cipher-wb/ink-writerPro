"""Configuration for the voice fingerprint system."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "voice-fingerprint.yaml"
)


@dataclass
class DeviationThresholds:
    catchphrase_absence_chapters: int = 3
    vocabulary_level_mismatch: float = 0.4
    forbidden_expression_severity: str = "critical"
    tone_drift_threshold: float = 0.5
    distinctiveness_min_diff: float = 0.3


@dataclass
class LearningConfig:
    min_dialogue_lines: int = 5
    auto_learn_on_first_appearance: bool = True
    append_only: bool = True
    max_catchphrases: int = 5
    max_speech_habits: int = 5
    max_forbidden_expressions: int = 5


@dataclass
class VoiceFingerprintConfig:
    enabled: bool = True
    score_threshold: float = 60.0
    max_retries: int = 2
    deviation_thresholds: DeviationThresholds = field(
        default_factory=DeviationThresholds
    )
    learning: LearningConfig = field(default_factory=LearningConfig)
    core_tiers: list[str] = field(
        default_factory=lambda: ["核心", "重要"]
    )


def load_config(path: Path | str | None = None) -> VoiceFingerprintConfig:
    """Load voice fingerprint config from YAML, falling back to defaults."""
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)

    if not path.exists():
        return VoiceFingerprintConfig()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return VoiceFingerprintConfig()

    dev_raw = raw.get("deviation_thresholds", {})
    deviation = DeviationThresholds(
        catchphrase_absence_chapters=int(dev_raw.get("catchphrase_absence_chapters", 3)),
        vocabulary_level_mismatch=float(dev_raw.get("vocabulary_level_mismatch", 0.4)),
        forbidden_expression_severity=str(dev_raw.get("forbidden_expression_severity", "critical")),
        tone_drift_threshold=float(dev_raw.get("tone_drift_threshold", 0.5)),
        distinctiveness_min_diff=float(dev_raw.get("distinctiveness_min_diff", 0.3)),
    )

    learn_raw = raw.get("learning", {})
    learning = LearningConfig(
        min_dialogue_lines=int(learn_raw.get("min_dialogue_lines", 5)),
        auto_learn_on_first_appearance=bool(learn_raw.get("auto_learn_on_first_appearance", True)),
        append_only=bool(learn_raw.get("append_only", True)),
        max_catchphrases=int(learn_raw.get("max_catchphrases", 5)),
        max_speech_habits=int(learn_raw.get("max_speech_habits", 5)),
        max_forbidden_expressions=int(learn_raw.get("max_forbidden_expressions", 5)),
    )

    core_tiers = raw.get("core_tiers", ["核心", "重要"])
    if not isinstance(core_tiers, list):
        core_tiers = ["核心", "重要"]

    return VoiceFingerprintConfig(
        enabled=bool(raw.get("enabled", True)),
        score_threshold=float(raw.get("score_threshold", 60.0)),
        max_retries=int(raw.get("max_retries", 2)),
        deviation_thresholds=deviation,
        learning=learning,
        core_tiers=core_tiers,
    )
