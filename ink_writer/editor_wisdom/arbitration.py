"""Golden-three chapter (1-3) checker conflict arbitration.

US-026: When chapters 1-3 simultaneously trigger `golden-three-checker`,
the 4 highpoint hard blockers, and `editor_wisdom` rules, polish-agent previously
received contradictory fix_prompts. This module merges them per the priority table
documented in `ink-writer/references/golden-three-arbitration.md`.

Priority (high to low):
  P0: golden-three-checker (hard, blocking)
  P1: highpoint-checker-x4 (hard, blocking)
  P2: editor_wisdom severity=hard
  P3: editor_wisdom severity=soft
  P4: editor_wisdom severity=info  (not merged, context-only)

Output contract (consumed by polish-agent):
{
  "chapter_id": int,
  "merged_fixes": [
    {
      "issue_id": "ARB-001",
      "priority": "P0|P1|P2|P3",
      "fix_prompt": str,
      "sources": [str, ...],
      "context_addendum": str | None,
    },
    ...
  ],
  "dropped": [{"source": str, "reason": str}, ...],
}

Only chapters 1-3 invoke this; chapter >= 4 returns `None` and callers should
fall back to the generic `checker-merge-matrix.md` flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

GOLDEN_THREE_CHAPTERS = frozenset({1, 2, 3})

_PRIORITY_ORDER = ("P0", "P1", "P2", "P3")
_PRIORITY_RANK = {p: i for i, p in enumerate(_PRIORITY_ORDER)}


@dataclass
class Issue:
    """A single checker-produced issue before arbitration."""

    source: str  # e.g. "golden-three-checker#H-12"
    priority: str  # one of P0..P4
    fix_prompt: str
    symptom_key: str  # normalized key to detect same-target conflicts
    direction: str = "forward"  # "forward" or conflicting label for reverse-conflict detection


@dataclass
class MergedFix:
    issue_id: str
    priority: str
    fix_prompt: str
    sources: list[str] = field(default_factory=list)
    context_addendum: str | None = None


def _is_higher(a: str, b: str) -> bool:
    return _PRIORITY_RANK[a] < _PRIORITY_RANK[b]


def arbitrate(chapter_id: int, issues: list[Issue]) -> dict[str, Any] | None:
    """Produce merged_fixes + dropped lists for chapters 1-3.

    Returns ``None`` when arbitration is not applicable (chapter >= 4).
    """
    if chapter_id not in GOLDEN_THREE_CHAPTERS:
        return None

    # Bucket by symptom_key so same-target issues fold together.
    buckets: dict[str, list[Issue]] = {}
    dropped: list[dict[str, str]] = []

    for issue in issues:
        if issue.priority == "P4":
            # info: never merged; caller may inject as context only.
            continue
        if issue.priority not in _PRIORITY_RANK:
            raise ValueError(f"unknown priority {issue.priority!r} from {issue.source}")
        buckets.setdefault(issue.symptom_key, []).append(issue)

    merged: list[MergedFix] = []
    for i, (_key, group) in enumerate(buckets.items(), start=1):
        # Highest priority wins within a symptom bucket.
        group.sort(key=lambda it: _PRIORITY_RANK[it.priority])
        top = group[0]

        directions = {it.direction for it in group}
        reverse_conflict = len(directions) > 1

        addendum_parts: list[str] = []
        sources: list[str] = [top.source]

        for other in group[1:]:
            if reverse_conflict and other.direction != top.direction:
                # §3.2 reverse conflict: demote to dropped log.
                dropped.append(
                    {"source": other.source, "reason": f"conflict_with_{top.priority}"}
                )
                continue
            sources.append(other.source)
            if _is_higher(top.priority, other.priority):
                # lower-priority same-direction → merge as context addendum
                addendum_parts.append(f"{other.source}: {other.fix_prompt}")
            else:
                # same priority same direction → concatenate as single fix; keep top text
                pass

        merged.append(
            MergedFix(
                issue_id=f"ARB-{i:03d}",
                priority=top.priority,
                fix_prompt=top.fix_prompt,
                sources=sources,
                context_addendum=" | ".join(addendum_parts) if addendum_parts else None,
            )
        )

    # Stable sort merged fixes by priority ascending (P0 first).
    merged.sort(key=lambda m: _PRIORITY_RANK[m.priority])

    return {
        "chapter_id": chapter_id,
        "merged_fixes": [
            {
                "issue_id": m.issue_id,
                "priority": m.priority,
                "fix_prompt": m.fix_prompt,
                "sources": m.sources,
                "context_addendum": m.context_addendum,
            }
            for m in merged
        ],
        "dropped": dropped,
    }
