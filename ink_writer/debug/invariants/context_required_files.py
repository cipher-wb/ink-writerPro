"""Invariant: context-agent reads all skill files declared in Context Contract."""
from __future__ import annotations

from datetime import datetime, timezone

from ink_writer.debug.schema import Incident


def check(
    *,
    required: list[str],
    actually_read: list[str],
    run_id: str,
    chapter: int | None,
) -> Incident | None:
    if not required:
        # No declared contract → fail-soft: return None.
        return None
    missing = [f for f in required if f not in set(actually_read)]
    if not missing:
        return None
    return Incident(
        ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        run_id=run_id,
        source="layer_c_invariant",
        skill="ink-write",
        step="context",
        kind="context.missing_required_skill_file",
        severity="warn",
        message=f"context-agent 漏读 {len(missing)} 个必读文件",
        chapter=chapter,
        evidence={"missing": missing, "required_total": len(required)},
    )
