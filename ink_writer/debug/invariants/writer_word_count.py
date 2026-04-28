"""Invariant: writer output length >= platform_min_words."""
from __future__ import annotations

from datetime import datetime, timezone

from ink_writer.debug.schema import Incident


def check(
    *,
    text: str,
    run_id: str,
    chapter: int | None,
    min_words: int,
    skill: str,
) -> Incident | None:
    """Return Incident if len(text) < min_words, else None."""
    length = len(text)
    if length >= min_words:
        return None
    return Incident(
        ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        run_id=run_id,
        source="layer_c_invariant",
        skill=skill,
        step="writer",
        kind="writer.short_word_count",
        severity="warn",
        message=f"writer 输出 {length} 字 < 平台下限 {min_words}",
        chapter=chapter,
        evidence={"length": length, "min": min_words},
    )
