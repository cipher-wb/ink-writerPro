"""Configuration for semantic chapter recall."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass
class SemanticRecallConfig:
    enabled: bool = True
    model_name: str = "BAAI/bge-small-zh-v1.5"
    semantic_top_k: int = 8
    recent_n: int = 5
    entity_forced_max: int = 10
    final_top_k: int = 10
    min_semantic_score: float = 0.3
    entity_boost_weight: float = 0.15
    max_pack_chars: int = 3000

    @classmethod
    def from_yaml(cls, path: Path | str) -> SemanticRecallConfig:
        path = Path(path)
        if not path.exists():
            return cls()
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in raw.items() if k in known_fields}
        return cls(**filtered)

    @classmethod
    def from_project_root(cls, project_root: Path | str) -> SemanticRecallConfig:
        project_root = Path(project_root)
        for candidate in [
            project_root / "config" / "semantic-recall.yaml",
            project_root / ".ink" / "semantic-recall.yaml",
        ]:
            if candidate.exists():
                return cls.from_yaml(candidate)
        return cls()
