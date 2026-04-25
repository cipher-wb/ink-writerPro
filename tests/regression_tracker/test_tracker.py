"""US-002 — Layer 4 regression tracker tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

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
from ink_writer.regression_tracker import (
    apply_recurrence,
    scan_evidence_chains,
)


def _make_case(
    *,
    case_id: str,
    status: CaseStatus,
    severity: CaseSeverity = CaseSeverity.P3,
) -> Case:
    return Case(
        case_id=case_id,
        title=f"Test {case_id}",
        status=status,
        severity=severity,
        domain=CaseDomain.WRITING_QUALITY,
        layer=[CaseLayer.DOWNSTREAM],
        tags=[],
        scope=Scope(genre=["all"], chapter=["all"]),
        source=Source(
            type=SourceType.SELF_AUDIT,
            raw_text="seed",
            ingested_at="2026-04-25",
        ),
        failure_pattern=FailurePattern(
            description="seed pattern",
            observable=["something happens"],
        ),
        resolution={"introduced_at": "2026-04-20"},
    )


def _write_chapter_evidence(
    *,
    base_dir: Path,
    book: str,
    chapter: str,
    cases_violated: list[str],
    produced_at: str = "2026-04-24T00:00:00+00:00",
) -> Path:
    out = base_dir / book / "chapters" / f"{chapter}.evidence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "$schema": "https://ink-writer/evidence_chain_v1",
        "book": book,
        "chapter": chapter,
        "phase": "writing",
        "stage": None,
        "produced_at": produced_at,
        "dry_run": False,
        "outcome": "blocked" if cases_violated else "passed",
        "phase_evidence": {
            "checkers": [
                {
                    "id": "test-checker",
                    "score": 0.0,
                    "blocked": bool(cases_violated),
                    "cases_violated": list(cases_violated),
                    "cases_hit": [],
                }
            ],
        },
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    return out


def _write_planning_evidence(
    *,
    base_dir: Path,
    book: str,
    cases_hit: list[str],
    produced_at: str = "2026-04-24T00:00:00+00:00",
) -> Path:
    out = base_dir / book / "planning_evidence_chain.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": "1.0",
        "phase": "planning",
        "book": book,
        "stages": [
            {
                "$schema": "https://ink-writer/evidence_chain_v1",
                "book": book,
                "chapter": "",
                "phase": "planning",
                "stage": "ink-init",
                "produced_at": produced_at,
                "outcome": "blocked" if cases_hit else "passed",
                "phase_evidence": {
                    "checkers": [
                        {
                            "id": "planning-checker",
                            "cases_hit": list(cases_hit),
                        }
                    ],
                },
            }
        ],
        "overall_passed": not cases_hit,
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    return out


@pytest.fixture
def case_store(tmp_path: Path) -> CaseStore:
    return CaseStore(tmp_path / "case_library")


def test_scan_detects_resolved_case_recurrence(
    tmp_path: Path, case_store: CaseStore
) -> None:
    resolved = _make_case(case_id="CASE-2026-0001", status=CaseStatus.RESOLVED)
    case_store.save(resolved)
    base_dir = tmp_path / "data"
    _write_chapter_evidence(
        base_dir=base_dir,
        book="book-A",
        chapter="0001",
        cases_violated=["CASE-2026-0001"],
    )

    records = scan_evidence_chains(base_dir=base_dir, case_store=case_store)

    assert len(records) == 1
    rec = records[0]
    assert rec.case_id == "CASE-2026-0001"
    assert rec.book == "book-A"
    assert rec.chapter == "0001"
    assert rec.severity_before == "P3"
    assert rec.severity_after == "P2"


def test_scan_skips_pending_cases(tmp_path: Path, case_store: CaseStore) -> None:
    pending = _make_case(case_id="CASE-2026-0010", status=CaseStatus.PENDING)
    case_store.save(pending)
    base_dir = tmp_path / "data"
    _write_chapter_evidence(
        base_dir=base_dir,
        book="book-A",
        chapter="0001",
        cases_violated=["CASE-2026-0010"],
    )

    records = scan_evidence_chains(base_dir=base_dir, case_store=case_store)
    assert records == []


def test_scan_dedup_per_book(tmp_path: Path, case_store: CaseStore) -> None:
    resolved = _make_case(case_id="CASE-2026-0002", status=CaseStatus.RESOLVED)
    case_store.save(resolved)
    base_dir = tmp_path / "data"
    _write_chapter_evidence(
        base_dir=base_dir, book="book-A", chapter="0001",
        cases_violated=["CASE-2026-0002"],
    )
    _write_chapter_evidence(
        base_dir=base_dir, book="book-A", chapter="0002",
        cases_violated=["CASE-2026-0002"],
    )
    # different book → separate record allowed
    _write_chapter_evidence(
        base_dir=base_dir, book="book-B", chapter="0001",
        cases_violated=["CASE-2026-0002"],
    )

    records = scan_evidence_chains(base_dir=base_dir, case_store=case_store)

    books = sorted(r.book for r in records)
    assert books == ["book-A", "book-B"]
    assert len(records) == 2


def test_scan_handles_planning_evidence(
    tmp_path: Path, case_store: CaseStore
) -> None:
    resolved = _make_case(case_id="CASE-2026-0003", status=CaseStatus.RESOLVED)
    case_store.save(resolved)
    base_dir = tmp_path / "data"
    _write_planning_evidence(
        base_dir=base_dir, book="book-A", cases_hit=["CASE-2026-0003"],
    )

    records = scan_evidence_chains(base_dir=base_dir, case_store=case_store)
    assert len(records) == 1
    assert records[0].chapter is None
    assert records[0].evidence_chain_path.endswith("planning_evidence_chain.json")


def test_apply_upgrades_severity_and_status(
    tmp_path: Path, case_store: CaseStore
) -> None:
    resolved = _make_case(
        case_id="CASE-2026-0004",
        status=CaseStatus.RESOLVED,
        severity=CaseSeverity.P2,
    )
    case_store.save(resolved)
    base_dir = tmp_path / "data"
    _write_chapter_evidence(
        base_dir=base_dir, book="book-A", chapter="0001",
        cases_violated=["CASE-2026-0004"],
    )

    records = scan_evidence_chains(base_dir=base_dir, case_store=case_store)
    assert len(records) == 1
    updated = apply_recurrence(record=records[0], case_store=case_store)

    assert updated.status == CaseStatus.REGRESSED
    assert updated.severity == CaseSeverity.P1
    assert len(updated.recurrence_history) == 1
    assert updated.recurrence_history[0]["severity_before"] == "P2"
    assert updated.recurrence_history[0]["severity_after"] == "P1"

    # Subsequent recurrence pushes from P1 to P0; another one stays at P0.
    next_record = records[0]
    next_record.severity_before = "P1"
    next_record.severity_after = "P0"
    apply_recurrence(record=next_record, case_store=case_store)
    again = apply_recurrence(record=next_record, case_store=case_store)
    assert again.severity == CaseSeverity.P0
    assert len(again.recurrence_history) == 3
