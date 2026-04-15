"""Configuration for the plotline lifecycle tracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "plotline-lifecycle.yaml"
)


@dataclass
class InactivityRules:
    main_max_gap: int = 3
    sub_max_gap: int = 8
    dark_max_gap: int = 15


@dataclass
class PlotlineLifecycleConfig:
    enabled: bool = True
    inactivity_rules: InactivityRules = field(default_factory=InactivityRules)
    max_forced_advances_per_chapter: int = 2
    plan_injection_mode: str = "force"
    active_plotline_warn_limit: int = 10
    heatmap_bucket_size: int = 10


def load_config(path: Path | str | None = None) -> PlotlineLifecycleConfig:
    """Load plotline lifecycle config from YAML, falling back to defaults."""
    if path is None:
        path = DEFAULT_CONFIG_PATH
    path = Path(path)

    if not path.exists():
        return PlotlineLifecycleConfig()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return PlotlineLifecycleConfig()

    inactivity_raw = raw.get("inactivity_rules", {})
    inactivity = InactivityRules(
        main_max_gap=int(inactivity_raw.get("main_max_gap", 3)),
        sub_max_gap=int(inactivity_raw.get("sub_max_gap", 8)),
        dark_max_gap=int(inactivity_raw.get("dark_max_gap", 15)),
    )

    return PlotlineLifecycleConfig(
        enabled=bool(raw.get("enabled", True)),
        inactivity_rules=inactivity,
        max_forced_advances_per_chapter=int(raw.get("max_forced_advances_per_chapter", 2)),
        plan_injection_mode=str(raw.get("plan_injection_mode", "force")),
        active_plotline_warn_limit=int(raw.get("active_plotline_warn_limit", 10)),
        heatmap_bucket_size=int(raw.get("heatmap_bucket_size", 10)),
    )
