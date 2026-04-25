"""Scan evidence chains for resolved-case recurrences (Layer 4)."""
from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from ink_writer.case_library.models import Case, CaseSeverity
from ink_writer.case_library.store import _SEVERITY_LADDER, CaseStore
from ink_writer.regression_tracker.models import RecurrenceRecord


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _load_json(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _hit_case_ids(checker: dict) -> set[str]:
    """Pull case_ids from ``cases_violated`` / ``cases_hit`` in either the top
    level checker dict or its nested ``details`` dict."""
    out: set[str] = set()
    for key in ("cases_violated", "cases_hit"):
        for value in (checker.get(key), checker.get("details", {}).get(key)):
            if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
                for item in value:
                    if isinstance(item, str):
                        out.add(item)
                    elif isinstance(item, dict) and isinstance(item.get("case_id"), str):
                        out.add(item["case_id"])
    return out


def _evidence_files(base_dir: Path) -> list[tuple[str, str | None, Path, dict]]:
    """Yield ``(book, chapter_or_None, path, doc)`` for every evidence chain.

    Two shapes are recognised:
      - chapter evidence: ``data/<book>/chapters/<chapter>.evidence.json``
        — single dict with ``checkers`` under ``phase_evidence``.
      - planning evidence: ``data/<book>/planning_evidence_chain.json``
        — top-level dict with ``stages: [stage_dict, ...]``; each stage is
        treated as one logical evidence chain (``chapter=None``).
    """
    out: list[tuple[str, str | None, Path, dict]] = []
    if not base_dir.exists():
        return out
    for book_dir in sorted(p for p in base_dir.iterdir() if p.is_dir()):
        book = book_dir.name
        chapters_dir = book_dir / "chapters"
        if chapters_dir.exists():
            for path in sorted(chapters_dir.glob("*.evidence.json")):
                doc = _load_json(path)
                if doc is None:
                    continue
                chapter = path.name.removesuffix(".evidence.json")
                out.append((book, chapter, path, doc))
        planning_path = book_dir / "planning_evidence_chain.json"
        if planning_path.exists():
            doc = _load_json(planning_path)
            if isinstance(doc, dict):
                for stage in doc.get("stages", []) or []:
                    if isinstance(stage, dict):
                        out.append((book, None, planning_path, stage))
    return out


def _stage_case_hits(stage: dict) -> set[str]:
    out: set[str] = set()
    phase = stage.get("phase_evidence") or {}
    for checker in phase.get("checkers", []) or []:
        if isinstance(checker, dict):
            out.update(_hit_case_ids(checker))
    # spec also allows checker payloads to live at the top level (legacy)
    for checker in stage.get("checkers", []) or []:
        if isinstance(checker, dict):
            out.update(_hit_case_ids(checker))
    return out


def _next_severity(before: CaseSeverity) -> CaseSeverity:
    try:
        idx = _SEVERITY_LADDER.index(before)
    except ValueError:  # pragma: no cover
        return before
    return _SEVERITY_LADDER[min(idx + 1, len(_SEVERITY_LADDER) - 1)]


def _resolved_at_of(case: Case) -> str:
    raw = case.resolution.get("introduced_at") if case.resolution else None
    if isinstance(raw, str):
        return raw
    return ""


def _produced_at_of(stage: dict) -> str:
    value = stage.get("produced_at")
    return value if isinstance(value, str) else ""


def scan_evidence_chains(
    *,
    base_dir: Path | str,
    case_store: CaseStore,
    since: str | None = None,
) -> list[RecurrenceRecord]:
    """Return a deduped list of recurrence records.

    Args:
        base_dir: parent of the per-book directories (typically ``data/``).
        case_store: case library to source the *resolved* set from.
        since: ISO date / datetime; evidence chains with ``produced_at < since``
            are skipped. Default ``None`` keeps everything.

    Dedup rule (spec §4 Q3): one record per ``(book, case_id)`` even if the
    case re-fires across multiple chapters or stages — the first-seen evidence
    wins.
    """
    base = Path(base_dir)
    resolved_cases: dict[str, Case] = {c.case_id: c for c in case_store.iter_resolved()}
    if not resolved_cases:
        return []

    records: dict[tuple[str, str], RecurrenceRecord] = {}
    now_iso = _utc_now_iso()

    for book, chapter, path, stage in _evidence_files(base):
        produced_at = _produced_at_of(stage)
        if since and produced_at and produced_at < since:
            continue
        for case_id in _stage_case_hits(stage):
            case = resolved_cases.get(case_id)
            if case is None:
                continue
            key = (book, case_id)
            if key in records:
                continue
            severity_after = _next_severity(case.severity)
            records[key] = RecurrenceRecord(
                case_id=case_id,
                book=book,
                chapter=chapter,
                evidence_chain_path=str(path),
                resolved_at=_resolved_at_of(case),
                regressed_at=produced_at or now_iso,
                severity_before=case.severity.value,
                severity_after=severity_after.value,
            )
    return list(records.values())


def apply_recurrence(
    *,
    record: RecurrenceRecord,
    case_store: CaseStore,
) -> Case:
    """Persist a single recurrence into the case library and return the updated case."""
    return case_store.record_recurrence(record.case_id, record.to_dict())
