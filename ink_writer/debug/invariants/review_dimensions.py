"""Invariant: review report has minimum number of evaluation dimensions."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ink_writer.debug.schema import Incident


def check(
    *,
    report: dict[str, Any],
    skill: str,
    run_id: str,
    chapter: int | None,
    min_dimensions: int,
) -> Incident | None:
    dims = report.get("dimensions") or {}
    found = len(dims) if isinstance(dims, dict) else 0
    if found >= min_dimensions:
        return None
    return Incident(
        ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        run_id=run_id,
        source="layer_c_invariant",
        skill=skill,
        step="review",
        kind="review.missing_dimensions",
        severity="warn",
        message=f"review 报告 {found} 维度 < 期望 {min_dimensions}",
        chapter=chapter,
        evidence={"found": found, "expected": min_dimensions},
    )
