"""US-005 — dashboard aggregator metrics tests (7 cases)."""
from __future__ import annotations

from pathlib import Path

from ink_writer.case_library.models import CaseSeverity, CaseStatus
from ink_writer.dashboard.aggregator import (
    compute_m3_dry_run_pass_rate,
    compute_m4_dry_run_pass_rate,
    compute_recurrence_rate,
    recommend_dry_run_switch,
)
from tests.dashboard.conftest import (
    make_case,
    write_chapter_evidence,
    write_counter,
    write_planning_evidence,
)


def test_recurrence_rate_zero_when_no_resolved() -> None:
    assert compute_recurrence_rate(case_store_iter=iter([])) == 0.0


def test_recurrence_rate_basic() -> None:
    cases = [
        make_case(case_id="CASE-2026-0001", status=CaseStatus.RESOLVED),
        make_case(case_id="CASE-2026-0002", status=CaseStatus.RESOLVED),
        make_case(
            case_id="CASE-2026-0003",
            status=CaseStatus.REGRESSED,
            severity=CaseSeverity.P1,
            recurrence_history=[{"severity_before": "P2", "severity_after": "P1"}],
        ),
        # active case is excluded from denominator
        make_case(case_id="CASE-2026-0099", status=CaseStatus.ACTIVE),
    ]
    rate = compute_recurrence_rate(case_store_iter=iter(cases))
    assert rate == 1 / 3


def test_recommend_switch_below_threshold() -> None:
    assert (
        recommend_dry_run_switch(counter=2, pass_rate=1.0)
        == "continue"
    )


def test_recommend_switch_low_pass_rate() -> None:
    assert (
        recommend_dry_run_switch(counter=5, pass_rate=0.40)
        == "investigate"
    )


def test_recommend_switch_ready() -> None:
    assert (
        recommend_dry_run_switch(counter=10, pass_rate=0.80)
        == "switch"
    )


def test_m3_dry_run_pass_rate(tmp_path: Path) -> None:
    base_dir = tmp_path / "data"
    write_counter(base_dir=base_dir, filename=".dry_run_counter", value=4)
    write_chapter_evidence(
        base_dir=base_dir, book="book-A", chapter="0001", outcome="delivered"
    )
    write_chapter_evidence(
        base_dir=base_dir, book="book-A", chapter="0002", outcome="delivered"
    )
    write_chapter_evidence(
        base_dir=base_dir, book="book-A", chapter="0003", outcome="needs_human_review"
    )
    write_chapter_evidence(
        base_dir=base_dir, book="book-B", chapter="0001", outcome="blocked"
    )

    counter, pass_rate = compute_m3_dry_run_pass_rate(base_dir=base_dir)

    assert counter == 4
    assert pass_rate == 2 / 4


def test_m4_dry_run_pass_rate(tmp_path: Path) -> None:
    base_dir = tmp_path / "data"
    write_counter(base_dir=base_dir, filename=".planning_dry_run_counter", value=3)
    write_planning_evidence(
        base_dir=base_dir,
        book="book-A",
        stage_outcomes=["passed", "passed", "blocked"],
    )
    write_planning_evidence(
        base_dir=base_dir,
        book="book-B",
        stage_outcomes=["passed"],
    )

    counter, pass_rate = compute_m4_dry_run_pass_rate(base_dir=base_dir)

    assert counter == 3
    assert pass_rate == 3 / 4
