"""Invariant: polish before/after has meaningful character-level diff."""
from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher

from ink_writer.debug.schema import Incident


def _approx_diff_chars(before: str, after: str) -> int:
    """Approximate count of changed characters via SequenceMatcher ratio."""
    if not before and not after:
        return 0
    ratio = SequenceMatcher(None, before, after, autojunk=False).ratio()
    return int(round((1.0 - ratio) * max(len(before), len(after))))


def check(
    *,
    before: str,
    after: str,
    run_id: str,
    chapter: int | None,
    min_diff_chars: int,
) -> Incident | None:
    diff_chars = _approx_diff_chars(before, after)
    if diff_chars >= min_diff_chars:
        return None
    return Incident(
        ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        run_id=run_id,
        source="layer_c_invariant",
        skill="ink-write",
        step="polish",
        kind="polish.diff_too_small",
        severity="warn",
        message=f"polish 前后 diff ≈ {diff_chars} 字符 < 阈值 {min_diff_chars}",
        chapter=chapter,
        evidence={"diff_chars": diff_chars, "threshold": min_diff_chars},
    )
