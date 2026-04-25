"""M3 US-012: tests for evidence_chain.dry_run_report (spec §6.3)."""

from __future__ import annotations

import json
from pathlib import Path

from ink_writer.evidence_chain.dry_run_report import (
    aggregate_dry_run_metrics,
    generate_dry_run_report,
)


def _write_evidence(tmp_path: Path, book: str, chapter: str, payload: dict) -> None:
    p = tmp_path / "data" / book / "chapters" / f"{chapter}.evidence.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)


def _payload(
    *,
    book: str,
    chapter: str,
    outcome: str,
    rule_compliance: float = 0.8,
    rewrite_rounds: int = 0,
    case_updates: list[dict] | None = None,
) -> dict:
    return {
        "book": book,
        "chapter": chapter,
        "outcome": outcome,
        "dry_run": True,
        "phase_evidence": {
            "writer_agent": {
                "rounds": [
                    {
                        "round": 0,
                        "compliance_report": {"rule_compliance": rule_compliance},
                    }
                ],
            },
            "checkers": [],
            "polish_agent": {"rewrite_rounds": rewrite_rounds, "rewrite_drivers": []},
        },
        "case_evidence_updates": case_updates or [],
    }


def test_aggregate_metrics_counts_outcomes(tmp_path: Path) -> None:
    """5 章 dry-run（4 delivered + 1 needs_human_review）→ aggregate 统计正确。"""
    outcomes = ["delivered", "delivered", "needs_human_review", "delivered", "delivered"]
    for i, outcome in enumerate(outcomes):
        _write_evidence(
            tmp_path,
            "b",
            f"c{i}",
            _payload(
                book="b",
                chapter=f"c{i}",
                outcome=outcome,
                rule_compliance=0.7 if outcome == "needs_human_review" else 0.85,
                rewrite_rounds=3 if outcome == "needs_human_review" else 0,
                case_updates=[
                    {"case_id": "CASE-2026-0042", "result": "violated", "by": "round_0"}
                ]
                if outcome == "needs_human_review"
                else [],
            ),
        )

    metrics = aggregate_dry_run_metrics(book="b", base_dir=tmp_path)

    assert metrics["total_chapters"] == 5
    assert metrics["delivered"] == 4
    assert metrics["needs_human_review"] == 1
    assert metrics["rewrite_rounds_total"] == 3
    assert metrics["human_review_rate"] == 0.2
    assert metrics["case_hit_top10"] == [("CASE-2026-0042", 1)]
    assert metrics["rule_compliance_avg"] > 0


def test_generate_dry_run_report_writes_md(tmp_path: Path) -> None:
    """generate_dry_run_report 写 markdown 含必要节标题。"""
    _write_evidence(
        tmp_path,
        "b",
        "c0",
        _payload(book="b", chapter="c0", outcome="delivered", rule_compliance=0.85),
    )

    report_path = generate_dry_run_report(book="b", base_dir=tmp_path)

    assert report_path.is_file()
    assert report_path.parent == tmp_path / "data"
    assert report_path.name.startswith("dry_run_report_")
    assert report_path.suffix == ".md"

    content = report_path.read_text(encoding="utf-8")
    assert "# M3 Dry-Run Report" in content
    assert "## Outcomes" in content
    assert "delivered" in content
    assert "## Top 10 Case Hits" in content


def test_generate_report_handles_no_evidence(tmp_path: Path) -> None:
    """无 evidence 文件 → 报告含 0 chapters / no chapters 提示，不抛异常。"""
    report_path = generate_dry_run_report(book="b", base_dir=tmp_path)

    assert report_path.is_file()
    content = report_path.read_text(encoding="utf-8")
    lowered = content.lower()
    assert "no chapters" in lowered or "0 chapters" in lowered
