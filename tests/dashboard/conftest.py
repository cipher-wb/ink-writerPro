"""Shared fixtures for ink_writer/dashboard tests (US-005 + US-006)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

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


def make_case(
    *,
    case_id: str,
    status: CaseStatus = CaseStatus.RESOLVED,
    severity: CaseSeverity = CaseSeverity.P3,
    recurrence_history: list[dict[str, Any]] | None = None,
) -> Case:
    return Case(
        case_id=case_id,
        title=f"Test {case_id}",
        status=status,
        severity=severity,
        domain=CaseDomain.WRITING_QUALITY,
        layer=[CaseLayer.DOWNSTREAM],
        tags=["m5-test"],
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
        recurrence_history=list(recurrence_history or []),
    )


def write_chapter_evidence(
    *,
    base_dir: Path,
    book: str,
    chapter: str,
    outcome: str,
) -> Path:
    out = base_dir / book / "chapters" / f"{chapter}.evidence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "book": book,
        "chapter": chapter,
        "phase": "writing",
        "outcome": outcome,
        "phase_evidence": {"checkers": []},
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    return out


def write_planning_evidence(
    *,
    base_dir: Path,
    book: str,
    stage_outcomes: list[str],
) -> Path:
    out = base_dir / book / "planning_evidence_chain.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    stages = [
        {
            "book": book,
            "stage": f"stage-{i}",
            "outcome": outcome,
            "phase": "planning",
        }
        for i, outcome in enumerate(stage_outcomes)
    ]
    doc = {
        "schema_version": "1.0",
        "phase": "planning",
        "book": book,
        "stages": stages,
        "overall_passed": all(s["outcome"] != "blocked" for s in stages),
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    return out


def write_meta_rule_proposal(
    *,
    meta_rules_dir: Path,
    proposal_id: str,
    status: str = "pending",
    similarity: float = 0.85,
    merged_rule: str = "test merged rule",
    covered_cases: list[str] | None = None,
) -> Path:
    meta_rules_dir.mkdir(parents=True, exist_ok=True)
    out = meta_rules_dir / f"{proposal_id}.yaml"
    payload = {
        "proposal_id": proposal_id,
        "similarity": similarity,
        "merged_rule": merged_rule,
        "covered_cases": list(covered_cases or []),
        "reason": "test",
        "status": status,
    }
    with open(out, "w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False)
    return out


def write_counter(*, base_dir: Path, filename: str, value: int) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    out = base_dir / filename
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(str(value))
    return out


@pytest.fixture
def case_store(tmp_path: Path) -> CaseStore:
    return CaseStore(tmp_path / "data" / "case_library")
