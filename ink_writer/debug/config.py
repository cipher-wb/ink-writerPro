"""Debug mode config loader: yaml + project override + env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "DebugConfig",
    "LayerSwitches",
    "SeverityThresholds",
    "StorageConfig",
    "AlertsConfig",
    "SEVERITY_RANK",
    "deep_merge",
    "load_config",
]

SEVERITY_RANK = {"info": 0, "warn": 1, "error": 2}


@dataclass
class LayerSwitches:
    layer_a_hooks: bool = True
    layer_b_checker_router: bool = True
    layer_c_invariants: bool = True
    layer_d_adversarial: bool = False


@dataclass
class SeverityThresholds:
    jsonl_threshold: str = "info"
    sqlite_threshold: str = "warn"
    alert_threshold: str = "warn"
    stderr_threshold: str = "error"


@dataclass
class StorageConfig:
    base_dir: str = ".ink-debug"
    events_max_mb: int = 100
    archive_keep: int = 5


@dataclass
class AlertsConfig:
    per_chapter_summary: bool = True
    per_batch_report: bool = True
    warn_window_days: int = 7
    warn_window_threshold: int = 5


@dataclass
class DebugConfig:
    master_enabled: bool = True
    layers: LayerSwitches = field(default_factory=LayerSwitches)
    severity: SeverityThresholds = field(default_factory=SeverityThresholds)
    storage: StorageConfig = field(default_factory=StorageConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    invariants: dict[str, dict[str, Any]] = field(default_factory=dict)
    strict_mode: bool = False
    project_root: Path = field(default_factory=Path)

    def passes_threshold(self, severity: str, threshold_field: str) -> bool:
        """Return True if severity rank >= self.severity.<threshold_field> rank."""
        threshold = getattr(self.severity, threshold_field)
        return SEVERITY_RANK.get(severity, -1) >= SEVERITY_RANK[threshold]

    def base_path(self) -> Path:
        return self.project_root / self.storage.base_dir


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` into `base`. Dicts merge; everything else replaces."""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(
    *,
    global_yaml_path: Path,
    project_root: Path,
) -> DebugConfig:
    """Load global config + optional project override + env var override."""
    raw: dict[str, Any] = {}
    if global_yaml_path.exists():
        raw = yaml.safe_load(global_yaml_path.read_text(encoding="utf-8")) or {}

    local_path = project_root / ".ink-debug" / "config.local.yaml"
    if local_path.exists():
        local_raw = yaml.safe_load(local_path.read_text(encoding="utf-8")) or {}
        raw = deep_merge(raw, local_raw)

    cfg = DebugConfig(
        master_enabled=raw.get("master_enabled", True),
        layers=LayerSwitches(**(raw.get("layers") or {})),
        severity=SeverityThresholds(**(raw.get("severity") or {})),
        storage=StorageConfig(**(raw.get("storage") or {})),
        alerts=AlertsConfig(**(raw.get("alerts") or {})),
        invariants=raw.get("invariants") or {},
        strict_mode=raw.get("strict_mode", False),
        project_root=project_root,
    )

    if os.environ.get("INK_DEBUG_OFF") == "1":
        cfg.master_enabled = False

    return cfg
