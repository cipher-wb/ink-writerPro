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
from pathlib import Path
from typing import Any

GOLDEN_THREE_CHAPTERS = frozenset({1, 2, 3})

_PRIORITY_ORDER = ("P0", "P1", "P2", "P3")
_PRIORITY_RANK = {p: i for i, p in enumerate(_PRIORITY_ORDER)}

# US-012: matrix config path. Overlap groups + severity→priority map now
# live in ``config/arbitration.yaml``; adding a new overlap group no longer
# requires editing this file. NG-3 / Green G003 preserved: the 16 checker
# spec files remain independent — only their *runtime output* is merged.
_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "arbitration.yaml"
)

# Hardcoded fallbacks (used when the yaml is missing or unparseable). These
# mirror the v18 US-011 defaults so behavior is unchanged when config/ is
# absent (e.g. running tests from a stripped checkout).
_FALLBACK_CHECKERS: tuple[str, ...] = (
    "prose-impact-checker",
    "sensory-immersion-checker",
    "flow-naturalness-checker",
)
_FALLBACK_SEVERITY_PRIORITY: dict[str, str] = {
    "critical": "P2",
    "high": "P2",
    "medium": "P3",
    "warning": "P3",
    "low": "P3",
    "info": "P4",
}


def load_arbitration_matrix(
    path: Path | str | None = None,
) -> tuple[tuple[str, ...], dict[str, str]]:
    """US-012: load overlap checker list + severity→priority map from yaml.

    Returns ``(checkers, severity_priority)``. When the yaml is missing or
    malformed, falls back to the v18 US-011 hardcoded defaults so callers
    never crash — the arbitration pipeline is best-effort.

    ``checkers`` aggregates every entry from ``symptom_key_groups.<g>.checkers``;
    duplicates across groups are deduplicated while preserving first-seen
    order so reading-stable diagnostics stay deterministic.
    """
    target = Path(path) if path is not None else _CONFIG_PATH
    if not target.exists():
        return _FALLBACK_CHECKERS, dict(_FALLBACK_SEVERITY_PRIORITY)
    try:
        import yaml  # local import so non-yaml callers stay lightweight

        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except Exception:
        return _FALLBACK_CHECKERS, dict(_FALLBACK_SEVERITY_PRIORITY)
    if not isinstance(raw, Mapping):
        return _FALLBACK_CHECKERS, dict(_FALLBACK_SEVERITY_PRIORITY)

    seen: list[str] = []
    groups = raw.get("symptom_key_groups") or {}
    if isinstance(groups, Mapping):
        for group in groups.values():
            if not isinstance(group, Mapping):
                continue
            entries = group.get("checkers") or []
            if not isinstance(entries, list):
                continue
            for name in entries:
                if not isinstance(name, str):
                    continue
                if name and name not in seen:
                    seen.append(name)

    severity_raw = raw.get("severity_priority") or {}
    severity: dict[str, str] = {}
    if isinstance(severity_raw, Mapping):
        for k, v in severity_raw.items():
            if isinstance(k, str) and isinstance(v, str):
                severity[k.lower()] = v

    if not seen:
        seen_tuple = _FALLBACK_CHECKERS
    else:
        seen_tuple = tuple(seen)
    if not severity:
        severity = dict(_FALLBACK_SEVERITY_PRIORITY)
    return seen_tuple, severity


# Cache the parsed matrix so repeated calls (pipeline loops) avoid re-reading
# yaml. Tests can pass an explicit ``path=`` to ``load_arbitration_matrix`` to
# bypass the cache.
_GENERIC_CHECKERS, _GENERIC_SEVERITY_PRIORITY = load_arbitration_matrix()

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
    checkers: tuple[str, ...] | None = None,
    scene_mode: str | None = None,
    chapter_no: int = 0,
) -> list[Issue]:
    """US-011: extract ``Issue`` objects from an ``index.db.review_metrics``
    row (shape matches :meth:`IndexReadingMixin.read_review_metrics`).

    Consumes ``critical_issues`` + ``review_payload_json.checker_results`` for
    the overlap-prone prose-craft checkers. Each emitted issue carries a
    ``symptom_key`` normalized from the violation's ``type`` (falling back to
    ``symptom_key`` / ``category``) so ``arbitrate_generic`` can fold
    cross-checker duplicates.

    US-012: when ``checkers`` is ``None`` the matrix is loaded from
    ``config/arbitration.yaml`` (cached at import time). Callers wanting a
    one-off override (tests, migrations) can still pass an explicit tuple.

    US-007: ``scene_mode`` / ``chapter_no`` allow callers to filter out
    ``sensory-immersion-checker`` issues whenever directness mode is active
    (``scene_mode ∈ {golden_three, combat, climax, high_point}`` or
    ``scene_mode is None`` and ``chapter_no ∈ [1, 3]``). This mirrors the
    agent-spec skip behavior so stale / mis-configured sensory violations
    cannot reach polish-agent as Red in directness scenes. Non-directness
    scenes (``slow_build`` / ``emotional`` / ``other``) retain the full
    sensory-immersion pipeline — 零退化硬约束.
    """
    if checkers is None:
        checkers = _GENERIC_CHECKERS
    if not metrics:
        return []

    # US-007: drop sensory-immersion-checker from checker list when directness
    # mode is active. Import lazily to avoid a hard dependency cycle between
    # editor_wisdom and the prose package at module-import time.
    from ink_writer.prose.sensory_immersion_gate import (
        SENSORY_IMMERSION_CHECKER_NAME,
        should_skip_sensory_immersion,
    )

    _skip_sensory = should_skip_sensory_immersion(scene_mode, chapter_no)
    if _skip_sensory:
        checkers = tuple(c for c in checkers if c != SENSORY_IMMERSION_CHECKER_NAME)

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
    "load_arbitration_matrix",
]
