"""Configuration for the foreshadow lifecycle manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "foreshadow-lifecycle.yaml"
)


@dataclass
class PriorityOverdueRules:
    p0_threshold: int = 80
    p0_grace: int = 5
    p1_threshold: int = 50
    p1_grace: int = 10
    p2_grace: int = 20


@dataclass
class ForeshadowLifecycleConfig:
    enabled: bool = True
    overdue_grace_chapters: int = 10
    silence_threshold_chapters: int = 30
    priority_overdue_rules: PriorityOverdueRules = field(
        default_factory=PriorityOverdueRules
    )
    max_forced_payoffs_per_chapter: int = 2
    plan_injection_mode: str = "force"
    active_foreshadow_warn_limit: int = 15
    heatmap_bucket_size: int = 10


def load_config(path: Path | str | None = None) -> ForeshadowLifecycleConfig:
    """Load foreshadow lifecycle config from YAML, falling back to defaults."""
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)

    if not path.exists():
        return ForeshadowLifecycleConfig()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return ForeshadowLifecycleConfig()

    priority_raw = raw.get("priority_overdue_rules", {})
    priority_rules = PriorityOverdueRules(
        p0_threshold=int(priority_raw.get("p0_threshold", 80)),
        p0_grace=int(priority_raw.get("p0_grace", 5)),
        p1_threshold=int(priority_raw.get("p1_threshold", 50)),
        p1_grace=int(priority_raw.get("p1_grace", 10)),
        p2_grace=int(priority_raw.get("p2_grace", 20)),
    )

    return ForeshadowLifecycleConfig(
        enabled=bool(raw.get("enabled", True)),
        overdue_grace_chapters=int(raw.get("overdue_grace_chapters", 10)),
        silence_threshold_chapters=int(raw.get("silence_threshold_chapters", 30)),
        priority_overdue_rules=priority_rules,
        max_forced_payoffs_per_chapter=int(raw.get("max_forced_payoffs_per_chapter", 2)),
        plan_injection_mode=str(raw.get("plan_injection_mode", "force")),
        active_foreshadow_warn_limit=int(raw.get("active_foreshadow_warn_limit", 15)),
        heatmap_bucket_size=int(raw.get("heatmap_bucket_size", 10)),
    )
