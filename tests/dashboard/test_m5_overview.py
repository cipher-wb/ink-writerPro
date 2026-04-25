"""US-005 — m5_overview JSON payload tests (3 cases)."""
from __future__ import annotations

from pathlib import Path

from ink_writer.case_library.models import CaseSeverity, CaseStatus
from ink_writer.case_library.store import CaseStore
from ink_writer.dashboard.m5_overview import get_m5_overview
from tests.dashboard.conftest import (
    make_case,
    write_chapter_evidence,
    write_counter,
    write_meta_rule_proposal,
)


def test_overview_structure(tmp_path: Path) -> None:
    base_dir = tmp_path / "data"
    base_dir.mkdir(parents=True, exist_ok=True)
    case_store = CaseStore(base_dir / "case_library")

    overview = get_m5_overview(base_dir=base_dir, case_store=case_store)

    assert set(overview.keys()) == {
        "metrics",
        "dry_run",
        "pending_meta_rules",
        "recurrent_cases",
    }
    metrics = overview["metrics"]
    assert set(metrics.keys()) == {
        "recurrence_rate",
        "repair_speed_days",
        "editor_score_trend",
        "checker_accuracy",
    }
    assert set(overview["dry_run"].keys()) == {"m3", "m4"}
    assert set(overview["dry_run"]["m3"].keys()) == {
        "counter",
        "pass_rate",
        "recommendation",
    }


def test_overview_finds_pending_meta(tmp_path: Path) -> None:
    base_dir = tmp_path / "data"
    base_dir.mkdir(parents=True, exist_ok=True)
    case_store = CaseStore(base_dir / "case_library")

    meta_rules_dir = base_dir / "case_library" / "meta_rules"
    write_meta_rule_proposal(
        meta_rules_dir=meta_rules_dir,
        proposal_id="MR-0001",
        status="pending",
        covered_cases=["CASE-2026-0001", "CASE-2026-0002"],
    )
    write_meta_rule_proposal(
        meta_rules_dir=meta_rules_dir,
        proposal_id="MR-0002",
        status="approved",
    )
    # Case with recurrence_history → surfaces in recurrent_cases.
    regressed = make_case(
        case_id="CASE-2026-0050",
        status=CaseStatus.REGRESSED,
        severity=CaseSeverity.P1,
        recurrence_history=[
            {"severity_before": "P2", "severity_after": "P1", "regressed_at": "2026-04-25"}
        ],
    )
    case_store.save(regressed)

    overview = get_m5_overview(base_dir=base_dir, case_store=case_store)

    proposal_ids = [p["proposal_id"] for p in overview["pending_meta_rules"]]
    assert proposal_ids == ["MR-0001"]
    assert overview["recurrent_cases"][0]["case_id"] == "CASE-2026-0050"
    assert overview["recurrent_cases"][0]["recurrence_count"] == 1


def test_overview_recommends_correctly(tmp_path: Path) -> None:
    base_dir = tmp_path / "data"
    base_dir.mkdir(parents=True, exist_ok=True)
    case_store = CaseStore(base_dir / "case_library")

    write_counter(base_dir=base_dir, filename=".dry_run_counter", value=10)
    for i in range(8):
        write_chapter_evidence(
            base_dir=base_dir, book="book-A", chapter=f"{i:04d}", outcome="delivered"
        )
    for i in range(8, 10):
        write_chapter_evidence(
            base_dir=base_dir, book="book-A", chapter=f"{i:04d}", outcome="blocked"
        )

    overview = get_m5_overview(base_dir=base_dir, case_store=case_store)

    m3 = overview["dry_run"]["m3"]
    assert m3["counter"] == 10
    assert m3["pass_rate"] == 0.8
    assert m3["recommendation"] == "switch"

    # m4 has no fixtures → counter 0, pass_rate 0.0, recommendation continue
    m4 = overview["dry_run"]["m4"]
    assert m4["counter"] == 0
    assert m4["recommendation"] == "continue"
