"""US-010 — promote short-term ``project_memory.json`` patterns into long-term cases.

This is the *opposite* short-term → long-term bridge from
``ink_writer.learn.auto_case``: rather than scanning blocked chapter evidence,
``promote_short_term_to_long_term`` reads the per-book ``.ink/project_memory.json``
written by ink-learn modes A/B/C, and turns repeatedly-seen patterns
(``count >= min_occurrences``) into pending ``CASE-PROMOTE-NNNN.yaml`` proposals.

The editor then approves them via ``ink case approve`` to merge them into the
long-term case library, just like ``CASE-LEARN-*`` proposals.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ink_writer.case_library._id_alloc import allocate_case_id
from ink_writer.case_library.models import (
    Case,
    CaseDomain,
    CaseLayer,
    CaseSeverity,
    CaseStatus,
    FailurePattern,
    Scope,
    Source,
    SourceType,
)
from ink_writer.case_library.store import CaseStore


def _next_promote_id(cases_dir: Path) -> str:
    """并发安全分配 ``CASE-PROMOTE-NNNN``（review §二 P1#6 修复）。"""
    return allocate_case_id(cases_dir, "CASE-PROMOTE-")


def _severity_for_kind(kind: str) -> CaseSeverity:
    """failure → P2; success/anything else → P3."""
    if kind == "failure":
        return CaseSeverity.P2
    return CaseSeverity.P3


def _make_promote_case(
    *,
    case_id: str,
    text: str,
    kind: str,
    count: int,
    now: datetime,
) -> Case:
    severity = _severity_for_kind(kind)
    notes = (
        f"auto-promoted by ink_writer.learn.promote from short-term "
        f"project_memory pattern (kind={kind}, count={count})"
    )
    return Case(
        case_id=case_id,
        title=f"自动晋升: {kind} 模式 — {text[:40]}",
        status=CaseStatus.PENDING,
        severity=severity,
        domain=CaseDomain.WRITING_QUALITY,
        layer=[CaseLayer.DOWNSTREAM],
        tags=["m5_promote", kind],
        scope=Scope(genre=[], chapter=[]),
        source=Source(
            type=SourceType.SELF_AUDIT,
            raw_text=notes,
            ingested_at=now.date().isoformat(),
            ingested_from="ink_learn_promote",
        ),
        failure_pattern=FailurePattern(
            description=text,
            observable=[text],
        ),
        # M5 三字段显式赋默认值（review §二 P1#5）。
        recurrence_history=[],
        meta_rule_id=None,
        sovereign=False,
    )


def promote_short_term_to_long_term(
    *,
    project_memory_path: Path,
    case_store: CaseStore,
    cases_dir: Path | str | None = None,
    min_occurrences: int = 3,
    now: datetime | None = None,
) -> list[Case]:
    """Promote frequent project_memory patterns into pending ``CASE-PROMOTE-*`` cases.

    Args:
        project_memory_path: path to ``.ink/<book>/project_memory.json``;
            missing file → returns an empty list (no error).
        case_store: target library; new cases are persisted via
            ``case_store.save`` so the schema validator runs.
        cases_dir: directory used for ``CASE-PROMOTE-*`` ID allocation; defaults
            to ``data/case_library/cases``.
        min_occurrences: minimum ``count`` field on a pattern to qualify
            (spec §3 P3 default = 3).
        now: clock injection; defaults to UTC now.

    Returns:
        list of newly-created ``Case`` instances (already persisted). Empty if
        the memory file is missing, has no qualifying patterns, or fails to
        parse.
    """
    project_memory_path = Path(project_memory_path)
    if not project_memory_path.exists():
        return []

    try:
        with open(project_memory_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []

    if not isinstance(data, dict):
        return []
    patterns = data.get("patterns")
    if not isinstance(patterns, list):
        return []

    cases_dir_p = Path(cases_dir) if cases_dir is not None else Path("data/case_library/cases")
    now_dt = now or datetime.now(UTC)

    proposed: list[Case] = []
    for pattern in patterns:
        if not isinstance(pattern, dict):
            continue
        text = pattern.get("text")
        kind = pattern.get("kind")
        count = pattern.get("count")
        if not isinstance(text, str) or not text:
            continue
        if not isinstance(kind, str) or not kind:
            continue
        if not isinstance(count, int) or count < min_occurrences:
            continue

        case = _make_promote_case(
            case_id=_next_promote_id(cases_dir_p),
            text=text,
            kind=kind,
            count=count,
            now=now_dt,
        )
        case_store.save(case)
        proposed.append(case)

    return proposed


__all__ = ["promote_short_term_to_long_term"]
