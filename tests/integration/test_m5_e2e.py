"""M5 e2e 集成测试（US-013, spec §13 验收清单）。

6 个用例覆盖 M5 全链路：

1. ``test_layer4_recurrence_full_cycle`` — resolved case → chapter evidence
   命中 cases_violated → ``scan_evidence_chains`` → ``apply_recurrence`` →
   case status=regressed + severity 升级（P1 → P0）。
2. ``test_layer5_meta_rule_proposal_and_write`` — 5 个共享 tag 的相似 case →
   ``find_similar_clusters`` 走 _FakeLLM 出 1 条 proposal → ``write_meta_rule_proposal``
   写盘后 status=pending。
3. ``test_dashboard_m5_overview_aggregates`` — counter=3 + delivered evidence →
   ``get_m5_overview`` 返回 m3.counter==3 + recommendation=='continue'。
4. ``test_weekly_report_generation`` — ``generate_weekly_report(week_num=17)`` 写盘 +
   markdown 含 '2026-W17'。
5. ``test_ab_channel_in_planning_evidence`` — EvidenceChain(channel='A') →
   ``write_planning_evidence_chain`` → stages[0]['channel']=='A'。
6. ``test_auto_case_proposes_pattern`` — 2 章 outcome=blocked + 同 pattern →
   ``propose_cases_from_failures`` 出 1 条 CASE-LEARN-* 含 'm5_auto_learn' tag。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

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
from ink_writer.dashboard.m5_overview import get_m5_overview
from ink_writer.dashboard.weekly_report import generate_weekly_report
from ink_writer.evidence_chain.models import EvidenceChain
from ink_writer.evidence_chain.planning_writer import write_planning_evidence_chain
from ink_writer.learn.auto_case import propose_cases_from_failures
from ink_writer.meta_rule_emergence import (
    find_similar_clusters,
    write_meta_rule_proposal,
)
from ink_writer.regression_tracker import apply_recurrence, scan_evidence_chains


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_case(
    *,
    case_id: str,
    tags: list[str],
    status: CaseStatus = CaseStatus.ACTIVE,
    severity: CaseSeverity = CaseSeverity.P1,
    description: str = "seed pattern",
    sovereign: bool = False,
    meta_rule_id: str | None = None,
) -> Case:
    return Case(
        case_id=case_id,
        title=f"Test {case_id}",
        status=status,
        severity=severity,
        domain=CaseDomain.WRITING_QUALITY,
        layer=[CaseLayer.DOWNSTREAM],
        tags=list(tags),
        scope=Scope(genre=["all"], chapter=["all"]),
        source=Source(
            type=SourceType.SELF_AUDIT,
            raw_text="seed",
            ingested_at="2026-04-25",
        ),
        failure_pattern=FailurePattern(
            description=description,
            observable=["x"],
        ),
        sovereign=sovereign,
        meta_rule_id=meta_rule_id,
    )


@dataclass
class _FakeMessage:
    text: str


@dataclass
class _FakeResponse:
    content: list[_FakeMessage]


class _FakeMessages:
    def __init__(self, payload: dict | list[dict]) -> None:
        self._payload = payload
        self._index = 0

    def create(
        self,
        *,
        max_tokens: int,
        messages: list[dict],
        model: str | None = None,
    ) -> _FakeResponse:
        if isinstance(self._payload, list):
            payload = self._payload[min(self._index, len(self._payload) - 1)]
            self._index += 1
        else:
            payload = self._payload
        return _FakeResponse(
            content=[_FakeMessage(text=json.dumps(payload, ensure_ascii=False))]
        )


class _FakeLLM:
    def __init__(self, payload: dict | list[dict]) -> None:
        self.messages = _FakeMessages(payload)


# ---------------------------------------------------------------------------
# 1) Layer 4 recurrence full cycle
# ---------------------------------------------------------------------------


def test_layer4_recurrence_full_cycle(tmp_path: Path) -> None:
    """resolved → 命中 cases_violated → status=regressed + severity P1→P0。"""
    library = tmp_path / "case_library"
    store = CaseStore(library)
    case = _make_case(
        case_id="CASE-2026-9999",
        tags=["regression-target"],
        status=CaseStatus.RESOLVED,
        severity=CaseSeverity.P1,
    )
    store.save(case)

    base = tmp_path / "data"
    chapter_evidence = base / "demo" / "chapters" / "ch001.evidence.json"
    chapter_evidence.parent.mkdir(parents=True)
    chapter_evidence.write_text(
        json.dumps(
            {
                "outcome": "blocked",
                "phase_evidence": {
                    "checkers": [
                        {"id": "fake-checker", "cases_violated": ["CASE-2026-9999"]}
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    records = scan_evidence_chains(base_dir=base, case_store=store)
    assert len(records) == 1
    assert records[0].case_id == "CASE-2026-9999"

    updated = apply_recurrence(record=records[0], case_store=store)
    assert updated.status == CaseStatus.REGRESSED
    assert updated.severity == CaseSeverity.P0  # P1 → P0
    assert len(updated.recurrence_history) == 1


# ---------------------------------------------------------------------------
# 2) Layer 5 meta-rule proposal + write
# ---------------------------------------------------------------------------


def test_layer5_meta_rule_proposal_and_write(tmp_path: Path) -> None:
    """5 相似 case → propose → 写 yaml → status=pending。"""
    cases = [
        _make_case(case_id=f"CASE-2026-100{i}", tags=["dialogue-flat"])
        for i in range(5)
    ]
    covered = [c.case_id for c in cases]
    fake = _FakeLLM(
        {
            "similar": True,
            "similarity": 0.88,
            "merged_rule": "对话过于平面",
            "covered_cases": covered,
            "reason": "都缺少潜台词",
        }
    )

    proposals = find_similar_clusters(
        cases=cases,
        llm_client=fake,
        min_cluster_size=5,
        similarity_threshold=0.80,
        meta_rules_dir=tmp_path / "meta_rules",
    )
    assert len(proposals) == 1

    out_path = write_meta_rule_proposal(
        proposal=proposals[0], base_dir=tmp_path / "meta_rules"
    )
    assert out_path.exists()
    with open(out_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert data["status"] == "pending"
    assert data["proposal_id"].startswith("MR-")
    assert sorted(data["covered_cases"]) == sorted(covered)


# ---------------------------------------------------------------------------
# 3) dashboard m5 overview aggregates
# ---------------------------------------------------------------------------


def test_dashboard_m5_overview_aggregates(tmp_path: Path) -> None:
    """counter=3 + 1 delivered evidence → counter==3 + recommendation='continue'。"""
    base = tmp_path / "data"
    base.mkdir()
    (base / ".dry_run_counter").write_text("3", encoding="utf-8")

    chapters = base / "demo" / "chapters"
    chapters.mkdir(parents=True)
    (chapters / "ch001.evidence.json").write_text(
        json.dumps({"outcome": "delivered"}),
        encoding="utf-8",
    )

    overview = get_m5_overview(base_dir=base)
    assert overview["dry_run"]["m3"]["counter"] == 3
    assert overview["dry_run"]["m3"]["recommendation"] == "continue"
    # 4 大指标 schema 兜底
    assert "metrics" in overview
    assert "recurrence_rate" in overview["metrics"]


# ---------------------------------------------------------------------------
# 4) weekly report generation
# ---------------------------------------------------------------------------


def test_weekly_report_generation(tmp_path: Path) -> None:
    """W17 周报 markdown 落盘 + 含 '2026-W17' label。"""
    out_path = tmp_path / "report.md"
    result = generate_weekly_report(
        week_num=17,
        year=2026,
        base_dir=tmp_path / "data",
        out_path=out_path,
    )
    assert result == out_path
    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")
    assert "2026-W17" in text
    assert "## 行动项" in text


# ---------------------------------------------------------------------------
# 5) A/B channel field flows through planning evidence
# ---------------------------------------------------------------------------


def test_ab_channel_in_planning_evidence(tmp_path: Path) -> None:
    """EvidenceChain(channel='A') → planning evidence stages[0]['channel']=='A'。"""
    evidence = EvidenceChain(
        book="demo-m5",
        chapter="planning",
        phase="planning",
        stage="ink-init",
        channel="A",
        outcome="delivered",
    )
    out = write_planning_evidence_chain(
        book="demo-m5",
        evidence=evidence,
        base_dir=tmp_path,
    )
    with open(out, encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["stages"][0]["channel"] == "A"
    assert doc["stages"][0]["stage"] == "ink-init"


# ---------------------------------------------------------------------------
# 6) auto_case proposes pattern from blocked chapters
# ---------------------------------------------------------------------------


def test_auto_case_proposes_pattern(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """2 章 outcome=blocked + 同 pattern → 1 条 CASE-LEARN-* 含 'm5_auto_learn' tag。"""
    library = tmp_path / "case_library"
    store = CaseStore(library)
    cases_dir = store.cases_dir

    base = tmp_path / "data"
    chapters = base / "demo" / "chapters"
    chapters.mkdir(parents=True)
    for ch in ("ch001", "ch002"):
        (chapters / f"{ch}.evidence.json").write_text(
            json.dumps(
                {
                    "outcome": "blocked",
                    "produced_at": "2026-04-25T12:00:00+00:00",
                    "phase_evidence": {
                        "checkers": [
                            {"id": "fake", "cases_violated": ["CASE-2026-0001", "CASE-2026-0002"]}
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )

    proposed = propose_cases_from_failures(
        case_store=store,
        base_dir=base,
        cases_dir=cases_dir,
    )
    assert len(proposed) == 1
    learn_case = proposed[0]
    assert learn_case.case_id.startswith("CASE-LEARN-")
    assert "m5_auto_learn" in learn_case.tags
    # 落盘验证
    saved = list(cases_dir.glob("CASE-LEARN-*.yaml"))
    assert len(saved) == 1
