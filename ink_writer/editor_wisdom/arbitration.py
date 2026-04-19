"""Checker conflict arbitration (golden-three + generic).

US-026 (golden-three, chapters 1-3): ``arbitrate`` consolidates contradictory
fix_prompts emitted by `golden-three-checker`, the 4 highpoint hard blockers,
and `editor_wisdom` rules per `ink-writer/references/golden-three-arbitration.md`.

US-011 (generic, chapter >= 4): ``arbitrate_generic`` folds overlapping output
from the three prose-craft checkers (``prose-impact-checker`` /
``sensory-immersion-checker`` / ``flow-naturalness-checker``) whenever they
fire on the same ``symptom_key``. Polish-agent would otherwise receive 3×
fix_prompts per symptom and the prompt budget balloons 15-25% per chapter.
See `ink-writer/references/checker-merge-matrix.md` §"generic-arbitration".

Priority (high to low):
  P0: golden-three-checker (hard, blocking)
  P1: highpoint-checker-x4 (hard, blocking)
  P2: editor_wisdom severity=hard / prose-craft critical / high
  P3: editor_wisdom severity=soft / prose-craft medium / low
  P4: editor_wisdom severity=info  (not merged, context-only)

Output contract (consumed by polish-agent, identical for both paths):
{
  "chapter_id": int,
  "merged_fixes": [
    {
      "issue_id": "ARB-001" | "ARBG-001",
      "priority": "P0|P1|P2|P3",
      "fix_prompt": str,
      "sources": [str, ...],
      "context_addendum": str | None,
    },
    ...
  ],
  "dropped": [{"source": str, "reason": str}, ...],
  "mode": "golden" | "generic",  # generic-arbitration additions tagged
}

Chapter routing:
  ``arbitrate(ch)``         → chapters 1-3; returns ``None`` for ch >= 4.
  ``arbitrate_generic(ch)`` → chapters >= 4; returns ``None`` for ch < 4.

Callers (e.g. ``parallel.pipeline_manager``) should dispatch by chapter:
  ``arbitrate(ch, issues) or arbitrate_generic(ch, issues)``

Preserves Green G003 / NG-3: the 16 checkers themselves are untouched. Only
their runtime output is merged by symptom.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

GOLDEN_THREE_CHAPTERS = frozenset({1, 2, 3})

_PRIORITY_ORDER = ("P0", "P1", "P2", "P3")
_PRIORITY_RANK = {p: i for i, p in enumerate(_PRIORITY_ORDER)}

# US-011: overlapping prose-craft checkers whose runtime output is folded
# by ``arbitrate_generic`` for chapter >= 4. NG-3 safe: the checker spec
# files under ``ink-writer/agents/`` remain intact; only their emitted
# issues are deduped post-review.
_GENERIC_CHECKERS: tuple[str, ...] = (
    "prose-impact-checker",
    "sensory-immersion-checker",
    "flow-naturalness-checker",
)

# Severity → priority for generic checkers (golden-three path retains its
# own P0/P1 buckets via ``arbitrate``).
_GENERIC_SEVERITY_PRIORITY: dict[str, str] = {
    "critical": "P2",
    "high": "P2",
    "medium": "P3",
    "warning": "P3",
    "low": "P3",
    "info": "P4",
}

# Non-alnum → "_" for symptom_key normalization (stable across locales).
_SYMPTOM_NORMALIZE_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")


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


def _bucketize_and_merge(
    issues: list[Issue], *, issue_id_prefix: str
) -> tuple[list[MergedFix], list[dict[str, str]]]:
    """Shared bucketing logic for ``arbitrate`` / ``arbitrate_generic``.

    Groups issues by ``symptom_key`` and folds each group into a single
    ``MergedFix`` whose ``fix_prompt`` is the highest-priority text and whose
    lower-priority siblings either join as ``context_addendum`` (same
    direction) or are demoted to ``dropped`` (reverse conflict).
    """
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
                issue_id=f"{issue_id_prefix}-{i:03d}",
                priority=top.priority,
                fix_prompt=top.fix_prompt,
                sources=sources,
                context_addendum=" | ".join(addendum_parts) if addendum_parts else None,
            )
        )

    merged.sort(key=lambda m: _PRIORITY_RANK[m.priority])
    return merged, dropped


def _to_payload(
    chapter_id: int,
    merged: list[MergedFix],
    dropped: list[dict[str, str]],
    *,
    mode: str,
) -> dict[str, Any]:
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
        "mode": mode,
    }


def arbitrate(chapter_id: int, issues: list[Issue]) -> dict[str, Any] | None:
    """Produce merged_fixes + dropped lists for chapters 1-3.

    Returns ``None`` when arbitration is not applicable (chapter >= 4); in
    that case callers should delegate to :func:`arbitrate_generic`.
    """
    if chapter_id not in GOLDEN_THREE_CHAPTERS:
        return None

    merged, dropped = _bucketize_and_merge(issues, issue_id_prefix="ARB")
    payload = _to_payload(chapter_id, merged, dropped, mode="golden")
    # Back-compat: v14 tests inspect these keys without ``mode``; keep mode but
    # preserve original key ordering so JSON diffs stay stable.
    return payload


def arbitrate_generic(
    chapter_id: int, issues: list[Issue]
) -> dict[str, Any] | None:
    """US-011: generic checker-output arbitration for chapter >= 4.

    Merges overlapping ``prose-impact`` / ``sensory-immersion`` /
    ``flow-naturalness`` issues sharing the same ``symptom_key`` so
    polish-agent receives a single ``fix_prompt`` per symptom instead of
    three near-duplicate ones. Returns ``None`` for chapter < 4 (caller
    should dispatch to :func:`arbitrate` for chapters 1-3).

    Semantics mirror :func:`arbitrate` (bucket by symptom_key, highest
    priority wins, lower-priority siblings fold into ``context_addendum``
    or are dropped on reverse conflict). The only differences:
      * no ``GOLDEN_THREE_CHAPTERS`` gate (gated on ch >= 4)
      * issue_id prefix ``ARBG-`` (distinguishable from golden-three)
      * output ``mode`` tag is ``"generic"``

    Green G003 / NG-3: this *merges runtime output*, not the checker list
    itself. The 16 checkers remain independent writable spec files.
    """
    if chapter_id < 4:
        return None

    merged, dropped = _bucketize_and_merge(issues, issue_id_prefix="ARBG")
    return _to_payload(chapter_id, merged, dropped, mode="generic")


def _normalize_symptom_key(raw: str) -> str:
    """Normalize a checker-emitted ``type`` (e.g. ``"SHOT_MONOTONY"`` /
    ``"sensory.visual_overload"``) into a stable ``symptom_key`` so that
    overlapping checkers naming the same underlying issue differently all
    collide into one bucket.
    """
    if not raw:
        return "untyped"
    lowered = str(raw).strip().lower()
    norm = _SYMPTOM_NORMALIZE_RE.sub("_", lowered).strip("_")
    return norm or "untyped"


def _severity_to_priority(severity: str | None) -> str:
    if not severity:
        return "P3"
    return _GENERIC_SEVERITY_PRIORITY.get(severity.lower(), "P3")


def collect_issues_from_review_metrics(
    metrics: Mapping[str, Any] | None,
    *,
    checkers: tuple[str, ...] = _GENERIC_CHECKERS,
) -> list[Issue]:
    """US-011: extract ``Issue`` objects from an ``index.db.review_metrics``
    row (shape matches :meth:`IndexReadingMixin.read_review_metrics`).

    Consumes ``critical_issues`` + ``review_payload_json.checker_results`` for
    the overlap-prone prose-craft checkers. Each emitted issue carries a
    ``symptom_key`` normalized from the violation's ``type`` (falling back to
    ``symptom_key`` / ``category``) so ``arbitrate_generic`` can fold
    cross-checker duplicates.
    """
    if not metrics:
        return []
    issues: list[Issue] = []

    payload = metrics.get("review_payload_json") or {}
    if isinstance(payload, str):
        try:
            import json as _json
            payload = _json.loads(payload)
        except Exception:
            payload = {}
    if not isinstance(payload, Mapping):
        payload = {}

    checker_results = payload.get("checker_results") or {}
    if isinstance(checker_results, Mapping):
        for checker in checkers:
            entry = checker_results.get(checker)
            if not isinstance(entry, Mapping):
                continue
            raw_violations = entry.get("violations") or entry.get("issues") or []
            if not isinstance(raw_violations, list):
                continue
            for idx, v in enumerate(raw_violations):
                if not isinstance(v, Mapping):
                    continue
                vtype = (
                    v.get("type")
                    or v.get("symptom_key")
                    or v.get("category")
                    or ""
                )
                fix = (
                    v.get("suggestion")
                    or v.get("fix_prompt")
                    or v.get("description")
                    or ""
                )
                if not fix:
                    continue
                issues.append(
                    Issue(
                        source=f"{checker}#{vtype or idx}",
                        priority=_severity_to_priority(str(v.get("severity") or "")),
                        fix_prompt=str(fix).strip(),
                        symptom_key=_normalize_symptom_key(str(vtype)),
                        direction=str(v.get("direction") or "forward"),
                    )
                )

    # critical_issues may repeat entries (e.g. cross-checker consensus); include
    # when tagged with a recognized checker so arbitration still folds them.
    critical = metrics.get("critical_issues") or []
    if isinstance(critical, str):
        try:
            import json as _json
            critical = _json.loads(critical)
        except Exception:
            critical = []
    if isinstance(critical, list):
        for idx, v in enumerate(critical):
            if not isinstance(v, Mapping):
                continue
            checker = v.get("checker") or v.get("source") or ""
            if checker not in checkers:
                continue
            vtype = v.get("type") or v.get("symptom_key") or ""
            fix = v.get("suggestion") or v.get("fix_prompt") or ""
            if not fix:
                continue
            issues.append(
                Issue(
                    source=f"{checker}#critical-{vtype or idx}",
                    priority=_severity_to_priority(str(v.get("severity") or "critical")),
                    fix_prompt=str(fix).strip(),
                    symptom_key=_normalize_symptom_key(str(vtype)),
                    direction=str(v.get("direction") or "forward"),
                )
            )

    return issues


__all__ = [
    "Issue",
    "MergedFix",
    "GOLDEN_THREE_CHAPTERS",
    "arbitrate",
    "arbitrate_generic",
    "collect_issues_from_review_metrics",
]
