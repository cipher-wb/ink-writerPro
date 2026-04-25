"""US-003 — Layer 5 meta-rule emergence tests."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

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
from ink_writer.meta_rule_emergence import (
    MetaRuleProposal,
    find_similar_clusters,
    write_meta_rule_proposal,
)


# --- helpers ----------------------------------------------------------------


def _make_case(
    *,
    case_id: str,
    tags: list[str],
    description: str = "seed pattern",
    sovereign: bool = False,
    meta_rule_id: str | None = None,
    status: CaseStatus = CaseStatus.ACTIVE,
) -> Case:
    return Case(
        case_id=case_id,
        title=f"Test {case_id}",
        status=status,
        severity=CaseSeverity.P2,
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
            observable=["something happens"],
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
        self.calls: list[dict] = []

    def create(self, *, max_tokens: int, messages: list[dict], model: str | None = None) -> _FakeResponse:
        self.calls.append({"messages": messages, "model": model, "max_tokens": max_tokens})
        if isinstance(self._payload, list):
            payload = self._payload[min(self._index, len(self._payload) - 1)]
            self._index += 1
        else:
            payload = self._payload
        return _FakeResponse(content=[_FakeMessage(text=json.dumps(payload, ensure_ascii=False))])


class _FakeLLM:
    def __init__(self, payload: dict | list[dict]) -> None:
        self.messages = _FakeMessages(payload)


# --- tests ------------------------------------------------------------------


def test_finds_cluster_with_5_similar(tmp_path: Path) -> None:
    cases = [
        _make_case(case_id=f"CASE-2026-100{i}", tags=["dialogue-flat"])
        for i in range(5)
    ]
    covered = [c.case_id for c in cases]
    fake = _FakeLLM({
        "similar": True,
        "similarity": 0.88,
        "merged_rule": "对话过于平面",
        "covered_cases": covered,
        "reason": "都缺少潜台词",
    })

    proposals = find_similar_clusters(
        cases=cases,
        llm_client=fake,
        min_cluster_size=5,
        similarity_threshold=0.80,
        meta_rules_dir=tmp_path / "meta_rules",
    )

    assert len(proposals) == 1
    p = proposals[0]
    assert p.proposal_id == "MR-0001"
    assert p.similarity == 0.88
    assert sorted(p.covered_cases) == sorted(covered)
    assert "对话" in p.merged_rule


def test_skips_below_min_cluster(tmp_path: Path) -> None:
    cases = [
        _make_case(case_id=f"CASE-2026-200{i}", tags=["pacing"])
        for i in range(4)
    ]
    fake = _FakeLLM({
        "similar": True,
        "similarity": 0.95,
        "merged_rule": "节奏过快",
        "covered_cases": [c.case_id for c in cases],
        "reason": "全部呈现节奏失衡",
    })

    proposals = find_similar_clusters(
        cases=cases,
        llm_client=fake,
        min_cluster_size=5,
        similarity_threshold=0.80,
        meta_rules_dir=tmp_path / "meta_rules",
    )
    assert proposals == []
    # tag pre-filter rejects the cluster before LLM is even invoked
    assert fake.messages.calls == []


def test_skips_sovereign(tmp_path: Path) -> None:
    cases = [
        _make_case(
            case_id=f"CASE-2026-300{i}",
            tags=["author-voice"],
            sovereign=(i == 0),  # first one is sovereign
        )
        for i in range(5)
    ]
    fake = _FakeLLM({
        "similar": True,
        "similarity": 0.90,
        "merged_rule": "作者腔太重",
        "covered_cases": [c.case_id for c in cases],
        "reason": "voice 过度雷同",
    })

    proposals = find_similar_clusters(
        cases=cases,
        llm_client=fake,
        min_cluster_size=5,
        similarity_threshold=0.80,
        meta_rules_dir=tmp_path / "meta_rules",
    )
    # 4 eligible cases ≠ ≥ 5 → no proposal
    assert proposals == []


def test_skips_already_meta_rule_id(tmp_path: Path) -> None:
    cases = [
        _make_case(
            case_id=f"CASE-2026-400{i}",
            tags=["tense-shift"],
            meta_rule_id="MR-0001" if i == 0 else None,
        )
        for i in range(5)
    ]
    fake = _FakeLLM({
        "similar": True,
        "similarity": 0.92,
        "merged_rule": "时态飘移",
        "covered_cases": [c.case_id for c in cases],
        "reason": "all share tense issue",
    })

    proposals = find_similar_clusters(
        cases=cases,
        llm_client=fake,
        min_cluster_size=5,
        similarity_threshold=0.80,
        meta_rules_dir=tmp_path / "meta_rules",
    )
    assert proposals == []


def test_low_similarity_returns_empty(tmp_path: Path) -> None:
    cases = [
        _make_case(case_id=f"CASE-2026-500{i}", tags=["mixed"])
        for i in range(5)
    ]
    fake = _FakeLLM({
        "similar": True,
        "similarity": 0.55,
        "merged_rule": "weak match",
        "covered_cases": [c.case_id for c in cases],
        "reason": "loose theme",
    })

    proposals = find_similar_clusters(
        cases=cases,
        llm_client=fake,
        min_cluster_size=5,
        similarity_threshold=0.80,
        meta_rules_dir=tmp_path / "meta_rules",
    )
    assert proposals == []


def test_write_meta_rule_proposal(tmp_path: Path) -> None:
    out_dir = tmp_path / "meta_rules"
    proposal = MetaRuleProposal(
        proposal_id="MR-0007",
        similarity=0.91,
        merged_rule="情绪转折太快",
        covered_cases=[
            "CASE-2026-0001",
            "CASE-2026-0002",
            "CASE-2026-0003",
            "CASE-2026-0004",
            "CASE-2026-0005",
        ],
        reason="均缺少铺垫",
    )

    path = write_meta_rule_proposal(proposal=proposal, base_dir=out_dir)

    assert path == out_dir / "MR-0007.yaml"
    assert path.exists()
    with open(path, encoding="utf-8") as fp:
        loaded = yaml.safe_load(fp)
    assert loaded["proposal_id"] == "MR-0007"
    assert loaded["status"] == "pending"
    assert loaded["similarity"] == 0.91
    assert loaded["merged_rule"] == "情绪转折太快"
    assert len(loaded["covered_cases"]) == 5
