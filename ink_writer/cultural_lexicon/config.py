"""Configuration loader for the cultural-lexicon module."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "cultural-lexicon.yaml"
)

SUPPORTED_GENRES = frozenset({
    "xianxia", "xuanhuan", "urban", "scifi", "lishi", "youxi",
})

DEFAULT_MIN_TERMS: dict[str, int] = {
    "xianxia": 5,
    "xuanhuan": 5,
    "urban": 3,
    "scifi": 4,
    "lishi": 5,
    "youxi": 3,
}


@dataclass
class InjectInto:
    context: bool = True
    writer: bool = True


@dataclass
class CulturalLexiconConfig:
    enabled: bool = True
    inject_into: InjectInto = field(default_factory=InjectInto)
    min_terms_per_chapter: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_MIN_TERMS))
    inject_count: int = 20
    seed_offset: int = 42


def load_config(path: Path | str | None = None) -> CulturalLexiconConfig:
    """Load cultural-lexicon config from YAML, falling back to defaults."""
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)

    if not path.exists():
        return CulturalLexiconConfig()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return CulturalLexiconConfig()

    inject_raw = raw.get("inject_into", {})
    if not isinstance(inject_raw, dict):
        inject_raw = {}

    inject = InjectInto(
        context=bool(inject_raw.get("context", True)),
        writer=bool(inject_raw.get("writer", True)),
    )

    min_terms_raw = raw.get("min_terms_per_chapter", {})
    if not isinstance(min_terms_raw, dict):
        min_terms_raw = {}
    min_terms = dict(DEFAULT_MIN_TERMS)
    for k, v in min_terms_raw.items():
        if isinstance(v, (int, float)):
            min_terms[str(k)] = int(v)

    return CulturalLexiconConfig(
        enabled=bool(raw.get("enabled", True)),
        inject_into=inject,
        min_terms_per_chapter=min_terms,
        inject_count=int(raw.get("inject_count", 20)),
        seed_offset=int(raw.get("seed_offset", 42)),
    )
