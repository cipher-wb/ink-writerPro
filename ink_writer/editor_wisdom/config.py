"""Configuration loader for the editor-wisdom module."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "editor-wisdom.yaml"


@dataclass
class InjectInto:
    context: bool = True
    writer: bool = True
    polish: bool = True


@dataclass
class EditorWisdomConfig:
    enabled: bool = True
    retrieval_top_k: int = 5
    hard_gate_threshold: float = 0.75
    # US-015: split golden-three threshold into hard (blocking) + soft (target).
    # golden_three_threshold is kept for backward-compat (legacy single-value API).
    golden_three_threshold: float = 0.85
    golden_three_hard_threshold: float = 0.75
    golden_three_soft_threshold: float = 0.92
    inject_into: InjectInto = field(default_factory=InjectInto)


def load_config(path: Path | str | None = None) -> EditorWisdomConfig:
    """Load editor-wisdom config from YAML, falling back to defaults."""
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)

    if not path.exists():
        return EditorWisdomConfig()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return EditorWisdomConfig()

    inject_raw = raw.get("inject_into", {})
    if not isinstance(inject_raw, dict):
        inject_raw = {}

    inject = InjectInto(
        context=bool(inject_raw.get("context", True)),
        writer=bool(inject_raw.get("writer", True)),
        polish=bool(inject_raw.get("polish", True)),
    )

    return EditorWisdomConfig(
        enabled=bool(raw.get("enabled", True)),
        retrieval_top_k=int(raw.get("retrieval_top_k", 5)),
        hard_gate_threshold=float(raw.get("hard_gate_threshold", 0.75)),
        golden_three_threshold=float(raw.get("golden_three_threshold", 0.85)),
        golden_three_hard_threshold=float(raw.get("golden_three_hard_threshold", 0.75)),
        golden_three_soft_threshold=float(raw.get("golden_three_soft_threshold", 0.92)),
        inject_into=inject,
    )
