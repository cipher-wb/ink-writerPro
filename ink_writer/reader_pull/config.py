"""Configuration for the reader-pull hook retry gate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "reader-pull.yaml"
)


@dataclass
class ReaderPullConfig:
    enabled: bool = True
    score_threshold: float = 70.0
    golden_three_threshold: float = 80.0
    max_retries: int = 2


def load_config(path: Path | str | None = None) -> ReaderPullConfig:
    """Load reader-pull config from YAML, falling back to defaults."""
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)

    if not path.exists():
        return ReaderPullConfig()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return ReaderPullConfig()

    return ReaderPullConfig(
        enabled=bool(raw.get("enabled", True)),
        score_threshold=float(raw.get("score_threshold", 70.0)),
        golden_three_threshold=float(raw.get("golden_three_threshold", 80.0)),
        max_retries=int(raw.get("max_retries", 2)),
    )
