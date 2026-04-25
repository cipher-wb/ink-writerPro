"""M3 US-002: tests for evidence_chain.{models,writer}."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ink_writer.evidence_chain import (
    EvidenceChain,
    EvidenceChainMissingError,
    require_evidence_chain,
    write_evidence_chain,
)


def _build_evidence(book: str = "都市A", chapter: str = "ch005") -> EvidenceChain:
    ev = EvidenceChain(
        book=book,
        chapter=chapter,
        dry_run=False,
        outcome="delivered",
        produced_at="2026-04-25T12:30:00+00:00",
        context_recalled_rules=12,
        context_recalled_chunks=0,
        context_recalled_cases=8,
        writer_prompt_hash="abc123def456",
        writer_model="glm-4.6",
    )
    ev.record_self_check(
        round_idx=0,
        compliance_report={
            "rule_compliance": 0.65,
            "chunk_borrowing": None,
            "cases_addressed": ["CASE-2026-0017"],
            "cases_violated": ["CASE-2026-0042"],
            "raw_scores": {"EW-0001": 0.7, "EW-0042": 0.5},
            "overall_passed": False,
            "notes": "first round",
        },
    )
    ev.record_self_check(
        round_idx=1,
        compliance_report={
            "rule_compliance": 0.78,
            "chunk_borrowing": None,
            "cases_addressed": ["CASE-2026-0042"],
            "cases_violated": [],
            "raw_scores": {"EW-0001": 0.8, "EW-0042": 0.76},
            "overall_passed": True,
            "notes": "polish ok",
        },
    )
    ev.record_checkers(
        [
            {"id": "reader-pull", "score": 78, "blocked": False, "cases_hit": []},
            {"id": "conflict-skeleton", "score": 0.85, "blocked": False, "cases_hit": []},
        ]
    )
    ev.record_polish(round_idx=1, case_id="CASE-2026-0042", result="passed_after")
    ev.record_case_update(
        case_id="CASE-2026-0017",
        result="passed",
        by="writer_self_check.round_0",
    )
    return ev


def test_evidence_chain_round_trip(tmp_path: Path) -> None:
    """write_evidence_chain → require_evidence_chain → 文件存在且 JSON 可还原。"""
    ev = _build_evidence()

    written = write_evidence_chain(
        book="都市A",
        chapter="ch005",
        evidence=ev,
        base_dir=tmp_path,
    )

    assert written == tmp_path / "都市A" / "chapters" / "ch005.evidence.json"
    assert written.exists()

    with open(written, encoding="utf-8") as fh:
        loaded = json.load(fh)

    assert loaded["book"] == "都市A"
    assert loaded["chapter"] == "ch005"
    assert loaded["dry_run"] is False
    assert loaded["outcome"] == "delivered"
    assert loaded["produced_at"] == "2026-04-25T12:30:00+00:00"
    assert loaded["case_evidence_updates"][0]["case_id"] == "CASE-2026-0017"


def test_evidence_chain_includes_phase_evidence(tmp_path: Path) -> None:
    """to_dict 输出 spec §6.1 phase_evidence 三段：context_agent/writer_agent/checkers/polish_agent。"""
    ev = _build_evidence()

    written = write_evidence_chain(
        book="都市A",
        chapter="ch005",
        evidence=ev,
        base_dir=tmp_path,
    )

    with open(written, encoding="utf-8") as fh:
        loaded = json.load(fh)

    phase = loaded["phase_evidence"]
    assert phase["context_agent"]["recalled"] == {"rules": 12, "chunks": 0, "cases": 8}
    assert phase["context_agent"]["recall_quality_avg"] is None

    writer_phase = phase["writer_agent"]
    assert writer_phase["prompt_hash"] == "abc123def456"
    assert writer_phase["model"] == "glm-4.6"
    assert len(writer_phase["rounds"]) == 2
    assert writer_phase["rounds"][0]["round"] == 0
    # M2 chunks deferred → chunk_borrowing 必须保留 null（兼容字段）
    assert writer_phase["rounds"][0]["compliance_report"]["chunk_borrowing"] is None
    assert writer_phase["rounds"][1]["compliance_report"]["overall_passed"] is True

    assert len(phase["checkers"]) == 2
    assert phase["checkers"][0]["id"] == "reader-pull"

    polish = phase["polish_agent"]
    assert polish["rewrite_rounds"] == 1
    assert polish["rewrite_drivers"][0]["case_id"] == "CASE-2026-0042"


def test_require_evidence_chain_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(EvidenceChainMissingError, match="ch999"):
        require_evidence_chain(
            book="都市A",
            chapter="ch999",
            base_dir=tmp_path,
        )


def test_require_evidence_chain_present_returns_path(tmp_path: Path) -> None:
    ev = _build_evidence(chapter="ch007")

    write_evidence_chain(
        book="都市A",
        chapter="ch007",
        evidence=ev,
        base_dir=tmp_path,
    )

    path = require_evidence_chain(
        book="都市A",
        chapter="ch007",
        base_dir=tmp_path,
    )

    assert path == tmp_path / "都市A" / "chapters" / "ch007.evidence.json"
    assert path.exists()
