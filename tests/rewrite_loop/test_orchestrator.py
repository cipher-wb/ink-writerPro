"""US-008: rewrite_loop orchestrator tests (spec §5.2 + Q3+Q4+Q12)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ink_writer.rewrite_loop.orchestrator import (
    RewriteLoopResult,
    collect_blocking_cases,
    run_rewrite_loop,
)


@pytest.fixture
def cfg() -> dict:
    return {
        "rewrite_loop": {
            "max_rounds": 3,
            "needs_human_review_path": "data/<book>/needs_human_review.jsonl",
        },
        "writer_self_check": {"rule_compliance_threshold": 0.70},
    }


def _mk_case(case_id: str, severity: str = "P1"):
    case = MagicMock()
    case.case_id = case_id
    case.severity = MagicMock()
    case.severity.value = severity
    case.failure_pattern = MagicMock()
    case.failure_pattern.description = f"{case_id} failure description"
    case.failure_pattern.observable = [f"{case_id} observable signal"]
    return case


def _mk_compliance(*, passed: bool, violated: list[str], rule_compliance: float):
    return MagicMock(
        overall_passed=passed,
        cases_violated=violated,
        rule_compliance=rule_compliance,
        raw_scores={},
        cases_addressed=[],
        chunk_borrowing=None,
        notes="" if passed else "blocked",
    )


def test_collect_blocking_cases_dedupes_and_sorts_by_severity() -> None:
    """重复 + P0 优先排序."""
    case_store = MagicMock()
    case_store.load.side_effect = lambda cid: _mk_case(
        cid, "P0" if cid == "CASE-2026-0001" else "P1"
    )

    compliance = MagicMock()
    compliance.overall_passed = False
    compliance.cases_violated = ["CASE-2026-0002", "CASE-2026-0001"]

    check_results = [
        MagicMock(blocked=True, cases_hit=["CASE-2026-0001", "CASE-2026-0003"])
    ]

    blockers = collect_blocking_cases(compliance, check_results, case_store)
    ids = [c.case_id for c in blockers]
    assert ids[0] == "CASE-2026-0001"
    assert "CASE-2026-0002" in ids
    assert "CASE-2026-0003" in ids
    assert len(set(ids)) == len(ids)


def test_orchestrator_passes_when_all_clear(cfg: dict, tmp_path) -> None:
    case_store = MagicMock()
    self_check_fn = MagicMock(
        return_value=_mk_compliance(passed=True, violated=[], rule_compliance=0.9)
    )
    checker_fn = MagicMock(return_value=[])
    polish_fn = MagicMock()

    result = run_rewrite_loop(
        book="b",
        chapter="c1",
        chapter_text="initial chapter text",
        cfg=cfg,
        case_store=case_store,
        self_check_fn=self_check_fn,
        checkers_fn=checker_fn,
        polish_fn=polish_fn,
        is_dry_run=False,
        base_dir=tmp_path,
    )
    assert isinstance(result, RewriteLoopResult)
    assert result.outcome == "delivered"
    assert result.rounds == 1
    assert result.final_text == "initial chapter text"
    assert result.history == ["initial chapter text"]
    polish_fn.assert_not_called()
    assert result.evidence.outcome == "delivered"


def test_orchestrator_rewrites_until_pass(cfg: dict, tmp_path) -> None:
    case_store = MagicMock()
    case_store.load.return_value = _mk_case("CASE-2026-0001", "P1")

    self_check_fn = MagicMock()
    self_check_fn.side_effect = [
        _mk_compliance(
            passed=False, violated=["CASE-2026-0001"], rule_compliance=0.5
        ),
        _mk_compliance(passed=True, violated=[], rule_compliance=0.85),
    ]
    checker_fn = MagicMock(return_value=[])
    polish_fn = MagicMock(return_value="rewritten chapter")

    result = run_rewrite_loop(
        book="b",
        chapter="c1",
        chapter_text="initial",
        cfg=cfg,
        case_store=case_store,
        self_check_fn=self_check_fn,
        checkers_fn=checker_fn,
        polish_fn=polish_fn,
        is_dry_run=False,
        base_dir=tmp_path,
    )
    assert result.outcome == "delivered"
    assert result.rounds == 2
    polish_fn.assert_called_once()
    assert polish_fn.call_args.kwargs["case_id"] == "CASE-2026-0001"
    assert polish_fn.call_args.kwargs["related_chunks"] is None
    assert result.history == ["initial", "rewritten chapter"]
    assert result.final_text == "rewritten chapter"


def test_orchestrator_3_rounds_then_human_review(cfg: dict, tmp_path) -> None:
    case_store = MagicMock()
    case_store.load.return_value = _mk_case("CASE-2026-0001", "P1")
    self_check_fn = MagicMock(
        return_value=_mk_compliance(
            passed=False, violated=["CASE-2026-0001"], rule_compliance=0.5
        )
    )
    checker_fn = MagicMock(return_value=[])
    polish_fn = MagicMock(return_value="still fails")

    result = run_rewrite_loop(
        book="b",
        chapter="c1",
        chapter_text="initial",
        cfg=cfg,
        case_store=case_store,
        self_check_fn=self_check_fn,
        checkers_fn=checker_fn,
        polish_fn=polish_fn,
        is_dry_run=False,
        base_dir=tmp_path,
    )
    assert result.outcome == "needs_human_review"
    assert result.rounds == 4  # round 0 (initial) + 3 rewrites = 4 self_check calls
    assert polish_fn.call_count == 3
    # 4 versions kept in history (r0..r3)
    assert len(result.history) == 4
    assert result.evidence.outcome == "needs_human_review"


def test_orchestrator_one_case_per_round(cfg: dict, tmp_path) -> None:
    """2 个阻断 case → 第 1 轮修 P0 case、第 2 轮修 P1 case."""
    case_store = MagicMock()
    case_store.load.side_effect = lambda cid: _mk_case(
        cid, "P0" if cid == "CASE-2026-0001" else "P1"
    )

    self_check_fn = MagicMock()
    self_check_fn.side_effect = [
        _mk_compliance(
            passed=False,
            violated=["CASE-2026-0002", "CASE-2026-0001"],
            rule_compliance=0.5,
        ),
        _mk_compliance(
            passed=False, violated=["CASE-2026-0002"], rule_compliance=0.6
        ),
        _mk_compliance(passed=True, violated=[], rule_compliance=0.85),
    ]
    checker_fn = MagicMock(return_value=[])
    polish_fn = MagicMock(return_value="rewritten")

    result = run_rewrite_loop(
        book="b",
        chapter="c1",
        chapter_text="initial",
        cfg=cfg,
        case_store=case_store,
        self_check_fn=self_check_fn,
        checkers_fn=checker_fn,
        polish_fn=polish_fn,
        is_dry_run=False,
        base_dir=tmp_path,
    )
    assert result.outcome == "delivered"
    assert polish_fn.call_args_list[0].kwargs["case_id"] == "CASE-2026-0001"
    assert polish_fn.call_args_list[1].kwargs["case_id"] == "CASE-2026-0002"
    # evidence records polish rounds with case_id
    polish_log = result.evidence.polish_rounds
    assert [p["case_id"] for p in polish_log] == [
        "CASE-2026-0001",
        "CASE-2026-0002",
    ]
