"""Configuration for the reader-pull hook retry gate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ink_writer.platforms.resolver import resolve_platform_config

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "reader-pull.yaml"
)


@dataclass
class ReaderPullConfig:
    enabled: bool = True
    score_threshold: float = 70.0
    golden_three_threshold: float = 80.0
    max_retries: int = 2


def _resolve_platform_values(raw: dict, platform: str) -> dict:
    """Resolve platform overrides in the raw YAML dict."""
    if not isinstance(raw, dict):
        return raw
    return resolve_platform_config(raw, platform)


def load_config(path: Path | str | None = None, platform: str = "qidian") -> ReaderPullConfig:
    """Load reader-pull config from YAML, resolving platform overrides."""
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)

    if not path.exists():
        return ReaderPullConfig()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return ReaderPullConfig()

    resolved = _resolve_platform_values(raw, platform)

    return ReaderPullConfig(
        enabled=bool(resolved.get("enabled", True)),
        score_threshold=float(resolved.get("score_threshold", 70.0)),
        golden_three_threshold=float(resolved.get("golden_three_threshold", 80.0)),
        max_retries=int(resolved.get("max_retries", 2)),
    )
