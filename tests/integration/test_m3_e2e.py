"""M3 end-to-end integration (US-013, spec §6.5).

Eight scenarios stitching the full M3 P1 loop together:

1. ``test_e2e_chapter_passes_first_round_when_clear`` — clean chapter,
   ``run_rewrite_loop`` → ``delivered`` r1 with no polish.
2. ``test_e2e_chapter_polishes_then_passes`` — r0 fails 1 case → polish_fn
   called once → r1 passes → ``delivered``.
3. ``test_e2e_chapter_3_rounds_fails_then_human_review`` — every round
   blocks → outcome=``needs_human_review``; ``save_rewrite_history`` emits
   4 r-files, ``write_human_review_record`` appends jsonl.
4. ``test_e2e_dry_run_records_blocked_but_does_not_polish`` — checker
   would_have_blocked=True but blocked=False under dry_run; orchestrator
   sees no blocking case → no polish call; evidence reflects the soft hit.
5. ``test_e2e_dry_run_counter_switches_after_5`` — 5 increments + cfg
   switch_to_block_after=True → ``is_dry_run`` flips to False on chapter 6.
6. ``test_e2e_evidence_chain_strict_required`` — missing evidence file →
   ``require_evidence_chain`` raises ``EvidenceChainMissingError``.
7. ``test_e2e_polish_prompt_carries_case_failure_pattern`` — prompt built
   by ``build_polish_prompt`` carries case_id + failure_description +
   observable bullets.
8. ``test_e2e_5chapter_dry_run_report_generated`` — 4 delivered + 1
   needs_human_review on disk → ``generate_dry_run_report`` outputs md
   with the right counts.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from ink_writer.checker_pipeline.block_threshold_wrapper import (
    apply_block_threshold,
)
from ink_writer.evidence_chain import (
    EvidenceChain,
    EvidenceChainMissingError,
    require_evidence_chain,
    write_evidence_chain,
)
from ink_writer.evidence_chain.dry_run_report import generate_dry_run_report
from ink_writer.rewrite_loop.dry_run import (
    increment_dry_run_counter,
    is_dry_run,
)
from ink_writer.rewrite_loop.human_review import (
    save_rewrite_history,
    write_human_review_record,
)
from ink_writer.rewrite_loop.orchestrator import (
    RewriteLoopResult,
    run_rewrite_loop,
)
from ink_writer.rewrite_loop.polish_prompt import build_polish_prompt

BOOK = "demo-book"
CHAPTER = "ch001"


def _cfg() -> dict:
    return {
        "rewrite_loop": {
            "max_rounds": 3,
            "needs_human_review_path": "data/<book>/needs_human_review.jsonl",
        },
        "writer_self_check": {"rule_compliance_threshold": 0.70},
        "dry_run": {
            "enabled": True,
            "observation_chapters": 5,
            "switch_to_block_after": True,
        },
        "reader_pull": {
            "block_threshold": 60,
            "bound_cases_tags": ["reader_pull"],
        },
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


def _mk_compliance(*, passed: bool, violated=None, rule_compliance: float = 0.5):
    return MagicMock(
        overall_passed=passed,
        cases_violated=list(violated or []),
        rule_compliance=rule_compliance,
        raw_scores={},
        cases_addressed=[],
        chunk_borrowing=None,
        notes="" if passed else "blocked",
    )


# ---------------------------------------------------------------------------
# 1) clear chapter passes round 1
# ---------------------------------------------------------------------------


def test_e2e_chapter_passes_first_round_when_clear(tmp_path: Path) -> None:
    case_store = MagicMock()
    self_check = MagicMock(
        return_value=_mk_compliance(passed=True, violated=[], rule_compliance=0.92)
    )
    checkers = MagicMock(return_value=[])
    polish = MagicMock()

    result = run_rewrite_loop(
        book=BOOK,
        chapter=CHAPTER,
        chapter_text="一个干净开篇的章节正文。",
        cfg=_cfg(),
        case_store=case_store,
        self_check_fn=self_check,
        checkers_fn=checkers,
        polish_fn=polish,
        is_dry_run=False,
        base_dir=tmp_path,
    )
    assert isinstance(result, RewriteLoopResult)
    assert result.outcome == "delivered"
    assert result.rounds == 1
    polish.assert_not_called()

    # 写盘 + 强制必带门禁应可通过
    out_path = write_evidence_chain(
        book=BOOK,
        chapter=CHAPTER,
        evidence=result.evidence,
        base_dir=tmp_path / "data",
    )
    assert out_path.exists()
    assert require_evidence_chain(
        book=BOOK, chapter=CHAPTER, base_dir=tmp_path / "data"
    ) == out_path


# ---------------------------------------------------------------------------
# 2) polish once then pass
# ---------------------------------------------------------------------------


def test_e2e_chapter_polishes_then_passes(tmp_path: Path) -> None:
    case_store = MagicMock()
    case_store.load.return_value = _mk_case("CASE-2026-0042", "P1")

    self_check = MagicMock()
    self_check.side_effect = [
        _mk_compliance(passed=False, violated=["CASE-2026-0042"], rule_compliance=0.4),
        _mk_compliance(passed=True, violated=[], rule_compliance=0.85),
    ]
    checkers = MagicMock(return_value=[])
    polish = MagicMock(return_value="重写后的章节正文（已修复 CASE-2026-0042）。")

    result = run_rewrite_loop(
        book=BOOK,
        chapter=CHAPTER,
        chapter_text="初稿章节正文。",
        cfg=_cfg(),
        case_store=case_store,
        self_check_fn=self_check,
        checkers_fn=checkers,
        polish_fn=polish,
        is_dry_run=False,
        base_dir=tmp_path,
    )
    assert result.outcome == "delivered"
    assert result.rounds == 2
    polish.assert_called_once()
    kwargs = polish.call_args.kwargs
    assert kwargs["case_id"] == "CASE-2026-0042"
    assert kwargs["related_chunks"] is None
    assert "CASE-2026-0042 failure description" in kwargs["case_failure_description"]


# ---------------------------------------------------------------------------
# 3) 3 rounds → human review (4 versions + jsonl)
# ---------------------------------------------------------------------------


def test_e2e_chapter_3_rounds_fails_then_human_review(tmp_path: Path) -> None:
    case_store = MagicMock()
    case_store.load.return_value = _mk_case("CASE-2026-0099", "P0")

    self_check = MagicMock(
        return_value=_mk_compliance(
            passed=False, violated=["CASE-2026-0099"], rule_compliance=0.3
        )
    )
    checkers = MagicMock(return_value=[])

    rewrites = iter(["重写 v1", "重写 v2", "重写 v3"])
    polish = MagicMock(side_effect=lambda **_: next(rewrites))

    result = run_rewrite_loop(
        book=BOOK,
        chapter=CHAPTER,
        chapter_text="初稿 v0",
        cfg=_cfg(),
        case_store=case_store,
        self_check_fn=self_check,
        checkers_fn=checkers,
        polish_fn=polish,
        is_dry_run=False,
        base_dir=tmp_path,
    )
    assert result.outcome == "needs_human_review"
    assert polish.call_count == 3
    assert len(result.history) == 4
    assert result.history == ["初稿 v0", "重写 v1", "重写 v2", "重写 v3"]

    # 落 4 版 + jsonl 记录
    history_paths = save_rewrite_history(
        book=BOOK,
        chapter=CHAPTER,
        history=result.history,
        base_dir=tmp_path,
    )
    assert len(history_paths) == 4
    for i, path in enumerate(history_paths):
        assert path.name == f"{CHAPTER}.r{i}.txt"
        assert path.exists()

    evidence_path = write_evidence_chain(
        book=BOOK,
        chapter=CHAPTER,
        evidence=result.evidence,
        base_dir=tmp_path / "data",
    )
    jsonl_path = write_human_review_record(
        book=BOOK,
        chapter=CHAPTER,
        blocking_cases=["CASE-2026-0099"],
        rewrite_attempts=3,
        rewrite_history_paths=history_paths,
        evidence_chain_path=evidence_path,
        base_dir=tmp_path,
    )
    assert jsonl_path.exists()
    record = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert record["chapter"] == CHAPTER
    assert record["rewrite_attempts"] == 3
    assert record["blocking_cases"] == ["CASE-2026-0099"]
    assert "marked_at" in record


# ---------------------------------------------------------------------------
# 4) dry-run records blocked but does not polish
# ---------------------------------------------------------------------------


def test_e2e_dry_run_records_blocked_but_does_not_polish(tmp_path: Path) -> None:
    cfg = _cfg()

    case_store = MagicMock()
    case_store.list_ids_by_tag = MagicMock(return_value=["CASE-2026-0007"])

    self_check = MagicMock(
        return_value=_mk_compliance(passed=True, violated=[], rule_compliance=0.95)
    )

    def _checkers_fn(**_):
        # raw score below threshold → would_have_blocked, but is_dry_run gates it.
        return [
            apply_block_threshold(
                checker_id="reader_pull",
                score=42.0,
                cfg=cfg,
                is_dry_run=True,
                case_store=case_store,
            )
        ]

    polish = MagicMock()

    result = run_rewrite_loop(
        book=BOOK,
        chapter=CHAPTER,
        chapter_text="dry-run 章节正文",
        cfg=cfg,
        case_store=case_store,
        self_check_fn=self_check,
        checkers_fn=_checkers_fn,
        polish_fn=polish,
        is_dry_run=True,
        base_dir=tmp_path,
    )
    assert result.outcome == "delivered"
    polish.assert_not_called()
    assert result.evidence.dry_run is True

    # checker 留痕 would_have_blocked
    [checker_record] = result.evidence.checker_results
    assert checker_record["blocked"] is False
    assert checker_record["would_have_blocked"] is True
    assert "CASE-2026-0007" in checker_record["cases_hit"]


# ---------------------------------------------------------------------------
# 5) dry-run counter auto-switches after 5
# ---------------------------------------------------------------------------


def test_e2e_dry_run_counter_switches_after_5(tmp_path: Path) -> None:
    cfg = _cfg()
    base = tmp_path / "data"

    for _ in range(5):
        assert is_dry_run(cfg, base_dir=base) is True
        increment_dry_run_counter(base_dir=base)

    # 第 6 章前 counter 已到 observation_chapters，auto-switch 触发
    assert is_dry_run(cfg, base_dir=base) is False

    # switch_to_block_after=False → 即使 counter 已到也保持 dry-run
    cfg["dry_run"]["switch_to_block_after"] = False
    assert is_dry_run(cfg, base_dir=base) is True


# ---------------------------------------------------------------------------
# 6) evidence_chain.json strict required
# ---------------------------------------------------------------------------


def test_e2e_evidence_chain_strict_required(tmp_path: Path) -> None:
    base = tmp_path / "data"
    with pytest.raises(EvidenceChainMissingError):
        require_evidence_chain(book=BOOK, chapter=CHAPTER, base_dir=base)

    # 写盘后再调通过
    evidence = EvidenceChain(book=BOOK, chapter=CHAPTER, outcome="delivered")
    write_evidence_chain(book=BOOK, chapter=CHAPTER, evidence=evidence, base_dir=base)
    path = require_evidence_chain(book=BOOK, chapter=CHAPTER, base_dir=base)
    assert path.exists()


# ---------------------------------------------------------------------------
# 7) polish prompt carries case failure pattern
# ---------------------------------------------------------------------------


def test_e2e_polish_prompt_carries_case_failure_pattern() -> None:
    prompt = build_polish_prompt(
        chapter_text="主角站在街口张望。",
        case_id="CASE-2026-0123",
        case_failure_description="主角缺乏主动决策，沦为摄像头视角",
        case_observable=[
            "主角连续 3 段未做出选择",
            "情节由配角推动",
        ],
        related_chunks=None,
    )
    assert "CASE-2026-0123" in prompt
    assert "主角缺乏主动决策" in prompt
    assert "主角连续 3 段未做出选择" in prompt
    assert "情节由配角推动" in prompt
    assert "无相关范文" in prompt or "no related chunks available" in prompt


# ---------------------------------------------------------------------------
# 8) 5-chapter dry-run report (4 delivered + 1 needs_human_review)
# ---------------------------------------------------------------------------


def test_e2e_5chapter_dry_run_report_generated(tmp_path: Path) -> None:
    base = tmp_path
    evidence_base = base / "data"

    outcomes = [
        ("ch001", "delivered"),
        ("ch002", "delivered"),
        ("ch003", "delivered"),
        ("ch004", "delivered"),
        ("ch005", "needs_human_review"),
    ]
    for chapter, outcome in outcomes:
        ev = EvidenceChain(book=BOOK, chapter=chapter, dry_run=True, outcome=outcome)
        ev.record_self_check(
            round_idx=0,
            compliance_report={
                "rule_compliance": 0.8,
                "chunk_borrowing": None,
                "cases_addressed": [],
                "cases_violated": [],
                "overall_passed": outcome == "delivered",
                "notes": "",
            },
        )
        if outcome == "needs_human_review":
            ev.record_polish(round_idx=1, case_id="CASE-2026-0042", result="rewrite")
            ev.record_polish(round_idx=2, case_id="CASE-2026-0042", result="rewrite")
            ev.record_polish(round_idx=3, case_id="CASE-2026-0042", result="rewrite")
            ev.record_case_update(
                case_id="CASE-2026-0042", result="violated", by="polish-agent"
            )
        write_evidence_chain(
            book=BOOK, chapter=chapter, evidence=ev, base_dir=evidence_base
        )

    report_path = generate_dry_run_report(book=BOOK, base_dir=base)
    assert report_path.exists()
    body = report_path.read_text(encoding="utf-8")
    assert "# M3 Dry-Run Report" in body
    assert "delivered: 4" in body
    assert "needs_human_review: 1" in body
    assert "CASE-2026-0042" in body
