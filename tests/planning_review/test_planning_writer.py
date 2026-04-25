"""M4 US-002: tests for evidence_chain.planning_writer。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ink_writer.evidence_chain import (
    EvidenceChain,
    PlanningEvidenceChainMissingError,
    require_planning_evidence_chain,
    write_planning_evidence_chain,
)


def test_write_creates_new_file(
    planning_base_dir: Path, sample_planning_evidence_init: EvidenceChain
) -> None:
    """文件不存在 → 新建 schema_version 1.0 + phase planning + 单 stage + overall_passed True。"""
    written = write_planning_evidence_chain(
        book="test-book",
        evidence=sample_planning_evidence_init,
        base_dir=planning_base_dir,
    )

    assert written == planning_base_dir / "test-book" / "planning_evidence_chain.json"
    assert written.exists()

    with open(written, encoding="utf-8") as fh:
        doc = json.load(fh)

    assert doc["schema_version"] == "1.0"
    assert doc["phase"] == "planning"
    assert doc["book"] == "test-book"
    assert len(doc["stages"]) == 1
    assert doc["stages"][0]["stage"] == "ink-init"
    assert doc["stages"][0]["phase"] == "planning"
    assert doc["overall_passed"] is True


def test_write_merges_ink_plan_after_ink_init(
    planning_base_dir: Path, sample_planning_evidence_init: EvidenceChain
) -> None:
    """先写 ink-init 后写 ink-plan：stages 合并到 2 段，顺序保留，overall_passed 聚合。"""
    write_planning_evidence_chain(
        book="test-book",
        evidence=sample_planning_evidence_init,
        base_dir=planning_base_dir,
    )

    plan_evidence = EvidenceChain(
        book="test-book",
        chapter="",
        phase="planning",
        stage="ink-plan",
        produced_at="2026-04-25T11:00:00+00:00",
        outcome="passed",
    )
    plan_evidence.record_checkers(
        [
            {
                "id": "golden-finger-timing",
                "score": 1.0,
                "blocked": False,
                "cases_hit": [],
            },
            {
                "id": "protagonist-agency-skeleton",
                "score": 0.62,
                "blocked": False,
                "cases_hit": [],
            },
            {
                "id": "chapter-hook-density",
                "score": 0.78,
                "blocked": False,
                "cases_hit": [],
            },
        ]
    )

    written = write_planning_evidence_chain(
        book="test-book",
        evidence=plan_evidence,
        base_dir=planning_base_dir,
    )

    with open(written, encoding="utf-8") as fh:
        doc = json.load(fh)

    stage_names = [s["stage"] for s in doc["stages"]]
    assert stage_names == ["ink-init", "ink-plan"]
    assert doc["overall_passed"] is True

    # ink-plan 阶段的 checker_results 也要原样写入
    ink_plan_stage = next(s for s in doc["stages"] if s["stage"] == "ink-plan")
    checker_ids = [c["id"] for c in ink_plan_stage["phase_evidence"]["checkers"]]
    assert checker_ids == [
        "golden-finger-timing",
        "protagonist-agency-skeleton",
        "chapter-hook-density",
    ]


def test_require_raises_when_missing(planning_base_dir: Path) -> None:
    """文件不存在时 require_planning_evidence_chain raise PlanningEvidenceChainMissingError。"""
    with pytest.raises(PlanningEvidenceChainMissingError, match="missing-book"):
        require_planning_evidence_chain(
            book="missing-book",
            base_dir=planning_base_dir,
        )


def test_write_rejects_non_planning_phase(
    planning_base_dir: Path,
) -> None:
    """phase != 'planning' 直接 ValueError，避免误把章节级 evidence 写到策划期文件。"""
    chapter_evidence = EvidenceChain(
        book="test-book",
        chapter="ch001",
        phase="writing",
        stage=None,
        outcome="delivered",
    )

    with pytest.raises(ValueError, match="phase='planning'"):
        write_planning_evidence_chain(
            book="test-book",
            evidence=chapter_evidence,
            base_dir=planning_base_dir,
        )
