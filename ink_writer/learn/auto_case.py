"""US-009 — auto-propose pending cases from blocked-chapter evidence patterns.

This is the M5 short-term → long-term case bridge: scan recent ``blocked``
chapter evidence chains, find ``cases_violated`` combinations that recur
≥ ``min_pattern_occurrences`` times within ``pattern_window_days``, and write
new ``CASE-LEARN-NNNN`` proposals (status=pending) so that an editor can
review and approve them via ``ink case approve``.

Throttled at ``max_per_week`` to avoid flooding the case library with
auto-generated noise (spec §3 P3 default = 5).
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

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

DEFAULT_THROTTLE: dict[str, int] = {
    "max_per_week": 5,
    "min_pattern_occurrences": 2,
    "pattern_window_days": 7,
}


def _load_throttle(path: Path | None) -> dict[str, int]:
    if path is None or not path.exists():
        return dict(DEFAULT_THROTTLE)
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    section = (data.get("auto_case_from_failure") or {}) if isinstance(data, dict) else {}
    out = dict(DEFAULT_THROTTLE)
    for key in DEFAULT_THROTTLE:
        if isinstance(section.get(key), int):
            out[key] = section[key]
    return out


def _hit_case_ids(checker: dict) -> list[str]:
    """Extract ``CASE-...`` ids from a checker payload.

    Upstream schemas (``writer_self_check.ComplianceReport.cases_violated`` 与
    checker outcome ``cases_hit``) 显式声明为 ``list[str]`` 或 ``list[dict]``。
    收紧到 ``isinstance(value, list)``：dict / set / generator 等异常 payload
    被忽略（旧实现走 ``Iterable`` 时会 silently 迭代 dict keys 当作 case_id），
    避免上游 schema 漂移悄悄污染学习管线（review §三 #10）。
    """
    out: list[str] = []
    seen: set[str] = set()
    for key in ("cases_violated", "cases_hit"):
        for value in (checker.get(key), checker.get("details", {}).get(key)):
            if isinstance(value, list):
                for item in value:
                    cid: str | None = None
                    if isinstance(item, str):
                        cid = item
                    elif isinstance(item, dict) and isinstance(item.get("case_id"), str):
                        cid = item["case_id"]
                    if cid and cid not in seen:
                        seen.add(cid)
                        out.append(cid)
    return out


def _evidence_pattern(doc: dict) -> tuple[str, ...] | None:
    """Return a sorted tuple of case_ids violated by a blocked chapter, or None."""
    if not isinstance(doc, dict):
        return None
    if doc.get("outcome") != "blocked":
        return None
    phase = doc.get("phase_evidence") or {}
    cases: set[str] = set()
    for checker in phase.get("checkers", []) or []:
        if isinstance(checker, dict):
            cases.update(_hit_case_ids(checker))
    if not cases:
        return None
    return tuple(sorted(cases))


def _scan_blocked_evidence(
    *,
    base_dir: Path,
    since: datetime,
) -> list[tuple[str, str, tuple[str, ...]]]:
    """Yield ``(book, chapter, pattern)`` triples for every blocked chapter
    within the time window."""
    out: list[tuple[str, str, tuple[str, ...]]] = []
    if not base_dir.exists():
        return out
    since_iso = since.isoformat()
    for book_dir in sorted(p for p in base_dir.iterdir() if p.is_dir()):
        chapters = book_dir / "chapters"
        if not chapters.exists():
            continue
        for path in sorted(chapters.glob("*.evidence.json")):
            try:
                with open(path, encoding="utf-8") as fh:
                    doc = json.load(fh)
            except (OSError, ValueError):
                continue
            produced_at = doc.get("produced_at") if isinstance(doc, dict) else None
            if isinstance(produced_at, str) and produced_at < since_iso:
                continue
            pattern = _evidence_pattern(doc)
            if pattern is None:
                continue
            chapter = path.name.removesuffix(".evidence.json")
            out.append((book_dir.name, chapter, pattern))
    return out


def _next_learn_id(cases_dir: Path) -> str:
    """并发安全分配 ``CASE-LEARN-NNNN``（review §二 P1#6 修复）。"""
    return allocate_case_id(cases_dir, "CASE-LEARN-")


def _count_existing_learn_this_week(cases_dir: Path, now: datetime) -> int:
    """Count CASE-LEARN-* yaml files whose source.ingested_at is within the
    current ISO week (Monday 00:00 UTC anchor)."""
    week_start = (now - timedelta(days=now.weekday())).date().isoformat()
    count = 0
    for path in cases_dir.glob("CASE-LEARN-*.yaml"):
        try:
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except (OSError, ValueError):
            continue
        ingested = ((data.get("source") or {}).get("ingested_at")
                    if isinstance(data, dict) else None)
        if isinstance(ingested, str) and ingested >= week_start:
            count += 1
    return count


def _make_learn_case(
    *,
    case_id: str,
    pattern: tuple[str, ...],
    occurrences: int,
    sample_chapters: list[str],
    now: datetime,
) -> Case:
    pattern_list = list(pattern)
    tags = ["m5_auto_learn", *pattern_list[:3]]
    notes = (
        f"auto-proposed by ink_writer.learn.auto_case after pattern "
        f"{pattern_list} fired in {occurrences} blocked chapters "
        f"(samples: {sample_chapters[:3]})"
    )
    return Case(
        case_id=case_id,
        title=f"自动学习: 失败模式 {'+'.join(pattern_list[:3])}",
        status=CaseStatus.PENDING,
        severity=CaseSeverity.P2,
        domain=CaseDomain.WRITING_QUALITY,
        layer=[CaseLayer.DOWNSTREAM],
        tags=tags,
        scope=Scope(genre=[], chapter=[]),
        source=Source(
            type=SourceType.SELF_AUDIT,
            raw_text=notes,
            ingested_at=now.date().isoformat(),
            ingested_from="ink_learn_auto",
        ),
        failure_pattern=FailurePattern(
            description=(
                f"重复触发组合 {'+'.join(pattern_list)} —— 由 ink-learn 自动从最近"
                f"{occurrences} 个 blocked 章节聚合得出，需编辑确认是否升格为长期 case。"
            ),
            observable=list(pattern_list),
        ),
        # M5 三字段显式赋默认值（review §二 P1#5）：避免依赖 dataclass 默认导致
        # dashboard 复发率聚合 / regression_tracker 难判"无复发数据" vs "无复发"。
        recurrence_history=[],
        meta_rule_id=None,
        sovereign=False,
    )


def propose_cases_from_failures(
    *,
    case_store: CaseStore,
    base_dir: Path,
    cases_dir: Path | str,
    throttle_path: Path | None = None,
    now: datetime | None = None,
) -> list[Case]:
    """Scan recent blocked chapter evidence and propose new pending cases.

    Args:
        case_store: target case library; new cases are persisted via
            ``case_store.save`` so the schema validator runs.
        base_dir: parent of per-book directories with ``chapters/*.evidence.json``.
        cases_dir: directory to scan for ID allocation + weekly throttle counter.
        throttle_path: yaml with ``auto_case_from_failure: {max_per_week, ...}``.
        now: clock injection; defaults to UTC now.

    Returns:
        list of newly-created ``Case`` instances (already persisted). Empty if
        no recurring patterns found, throttle hit, or all patterns already
        covered by existing cases.
    """
    throttle = _load_throttle(throttle_path)
    now_dt = now or datetime.now(UTC)
    since_dt = now_dt - timedelta(days=int(throttle["pattern_window_days"]))

    blocked = _scan_blocked_evidence(base_dir=Path(base_dir), since=since_dt)
    if not blocked:
        return []

    pattern_counts: Counter[tuple[str, ...]] = Counter()
    pattern_chapters: dict[tuple[str, ...], list[str]] = {}
    for _book, chapter, pattern in blocked:
        pattern_counts[pattern] += 1
        pattern_chapters.setdefault(pattern, []).append(chapter)

    min_occurrences = int(throttle["min_pattern_occurrences"])
    qualifying = [
        (pattern, count)
        for pattern, count in pattern_counts.items()
        if count >= min_occurrences
    ]
    if not qualifying:
        return []

    cases_dir_p = Path(cases_dir)
    max_per_week = int(throttle["max_per_week"])
    used_this_week = _count_existing_learn_this_week(cases_dir_p, now_dt)
    budget = max(0, max_per_week - used_this_week)
    if budget == 0:
        return []

    # Sort newest-pattern-first by occurrence count then sorted pattern (stable).
    qualifying.sort(key=lambda item: (-item[1], item[0]))

    proposed: list[Case] = []
    for pattern, count in qualifying:
        if len(proposed) >= budget:
            break
        case = _make_learn_case(
            case_id=_next_learn_id(cases_dir_p),
            pattern=pattern,
            occurrences=count,
            sample_chapters=pattern_chapters[pattern],
            now=now_dt,
        )
        case_store.save(case)
        proposed.append(case)

    return proposed


__all__ = [
    "DEFAULT_THROTTLE",
    "propose_cases_from_failures",
]
