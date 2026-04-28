"""Invariant: ink-auto each chapter touches every expected step."""
from __future__ import annotations

from datetime import datetime, timezone

from ink_writer.debug.schema import Incident


def check(
    *,
    actual_steps: list[str],
    expected_steps: list[str],
    run_id: str,
    chapter: int | None,
) -> Incident | None:
    actual_set = set(actual_steps)
    missing = [s for s in expected_steps if s not in actual_set]
    if not missing:
        return None
    return Incident(
        ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        run_id=run_id,
        source="layer_c_invariant",
        skill="ink-auto",
        step=None,
        kind="auto.skill_step_skipped",
        severity="warn",
        message=f"ink-auto 漏 {len(missing)}/{len(expected_steps)} 步: {','.join(missing)}",
        chapter=chapter,
        evidence={"missing": missing, "expected": expected_steps, "actual": actual_steps},
    )
