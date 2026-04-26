"""Live-review 配置加载（带默认值 fallback + enabled=false 强制 inject_into 全 false）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG_PATH = Path("config/live-review.yaml")


@dataclass(frozen=True)
class BatchConfig:
    input_dir: str = "~/Desktop/星河审稿"
    output_dir: str = "data/live-review/extracted"
    resume_from_jsonl: bool = True
    skip_failed: bool = True
    log_progress: bool = True


@dataclass(frozen=True)
class InjectConfig:
    init: bool = True
    review: bool = True


@dataclass(frozen=True)
class LiveReviewConfig:
    enabled: bool = True
    model: str = "claude-sonnet-4-6"
    extractor_version: str = "1.0.0"
    batch: BatchConfig = field(default_factory=BatchConfig)
    hard_gate_threshold: float = 0.65
    golden_three_threshold: float = 0.75
    init_genre_warning_threshold: int = 60
    init_top_k: int = 3
    min_cases_per_genre: int = 3
    inject_into: InjectConfig = field(default_factory=InjectConfig)


def load_config(path: Path | None = None) -> LiveReviewConfig:
    """从 yaml 加载配置；缺字段走默认；enabled=false 强制 inject_into 全 false。"""
    p = path if path is not None else _DEFAULT_CONFIG_PATH
    if not p.exists():
        return LiveReviewConfig()
    raw: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    batch_raw = raw.get("batch", {}) or {}
    inject_raw = raw.get("inject_into", {}) or {}
    enabled = bool(raw.get("enabled", True))
    inject = InjectConfig(
        init=bool(inject_raw.get("init", True)) and enabled,
        review=bool(inject_raw.get("review", True)) and enabled,
    )
    return LiveReviewConfig(
        enabled=enabled,
        model=str(raw.get("model", "claude-sonnet-4-6")),
        extractor_version=str(raw.get("extractor_version", "1.0.0")),
        batch=BatchConfig(
            input_dir=str(batch_raw.get("input_dir", "~/Desktop/星河审稿")),
            output_dir=str(batch_raw.get("output_dir", "data/live-review/extracted")),
            resume_from_jsonl=bool(batch_raw.get("resume_from_jsonl", True)),
            skip_failed=bool(batch_raw.get("skip_failed", True)),
            log_progress=bool(batch_raw.get("log_progress", True)),
        ),
        hard_gate_threshold=float(raw.get("hard_gate_threshold", 0.65)),
        golden_three_threshold=float(raw.get("golden_three_threshold", 0.75)),
        init_genre_warning_threshold=int(raw.get("init_genre_warning_threshold", 60)),
        init_top_k=int(raw.get("init_top_k", 3)),
        min_cases_per_genre=int(raw.get("min_cases_per_genre", 3)),
        inject_into=inject,
    )


__all__ = ["LiveReviewConfig", "BatchConfig", "InjectConfig", "load_config"]
