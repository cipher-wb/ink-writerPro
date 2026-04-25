"""EvidenceChain dataclass — spec §6.1 schema。

每章 ink-write 交付时把 EvidenceChain.to_dict() 写到
``data/<book>/chapters/<chapter>.evidence.json``。

M3 期 chunk_borrowing 字段保留为 None（M2 chunks deferred 兼容；spec §3.5 风险 8）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

SCHEMA_URI = "https://ink-writer/evidence_chain_v1"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class EvidenceChain:
    """spec §6.1 evidence_chain.json schema 的内存表示。

    字段分组对应 phase_evidence 三段（context / writer / checkers / polish）。
    helper 方法供 rewrite_loop / writer_self_check 逐轮追加，避免调用方直接拼 dict。
    """

    book: str
    chapter: str
    dry_run: bool = False
    outcome: str = "pending"
    produced_at: str = ""

    phase: str = "writing"
    stage: str | None = None
    channel: str | None = None

    context_recalled_rules: int = 0
    context_recalled_chunks: int = 0
    context_recalled_cases: int = 0
    context_recall_quality_avg: float | None = None

    writer_prompt_hash: str = ""
    writer_model: str = ""
    writer_rounds: list[dict[str, Any]] = field(default_factory=list)

    checker_results: list[dict[str, Any]] = field(default_factory=list)

    polish_rounds: list[dict[str, Any]] = field(default_factory=list)

    case_updates: list[dict[str, Any]] = field(default_factory=list)

    human_overrides: list[dict[str, Any]] = field(default_factory=list)

    def record_self_check(
        self,
        *,
        round_idx: int,
        compliance_report: dict[str, Any],
    ) -> None:
        self.writer_rounds.append(
            {"round": round_idx, "compliance_report": dict(compliance_report)}
        )

    def record_checkers(self, checker_outcomes: list[dict[str, Any]]) -> None:
        self.checker_results = [dict(item) for item in checker_outcomes]

    def record_polish(
        self,
        *,
        round_idx: int,
        case_id: str,
        result: str,
    ) -> None:
        self.polish_rounds.append(
            {"round": round_idx, "case_id": case_id, "result": result}
        )

    def record_case_update(
        self,
        *,
        case_id: str,
        result: str,
        by: str,
    ) -> None:
        self.case_updates.append(
            {"case_id": case_id, "result": result, "by": by}
        )

    def to_dict(self) -> dict[str, Any]:
        produced_at = self.produced_at or _utc_now_iso()
        return {
            "$schema": SCHEMA_URI,
            "book": self.book,
            "chapter": self.chapter,
            "phase": self.phase,
            "stage": self.stage,
            "channel": self.channel,
            "produced_at": produced_at,
            "dry_run": self.dry_run,
            "outcome": self.outcome,
            "phase_evidence": {
                "context_agent": {
                    "recalled": {
                        "rules": self.context_recalled_rules,
                        "chunks": self.context_recalled_chunks,
                        "cases": self.context_recalled_cases,
                    },
                    "recall_quality_avg": self.context_recall_quality_avg,
                },
                "writer_agent": {
                    "prompt_hash": self.writer_prompt_hash,
                    "model": self.writer_model,
                    "rounds": [dict(r) for r in self.writer_rounds],
                },
                "checkers": [dict(c) for c in self.checker_results],
                "polish_agent": {
                    "rewrite_rounds": len(self.polish_rounds),
                    "rewrite_drivers": [dict(d) for d in self.polish_rounds],
                },
            },
            "case_evidence_updates": [dict(u) for u in self.case_updates],
            "human_overrides": [dict(h) for h in self.human_overrides],
        }
