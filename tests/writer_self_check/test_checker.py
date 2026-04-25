"""writer-self-check 单元测试 — spec §3 + Q1+Q2+Q15。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from ink_writer.writer_self_check import ComplianceReport, writer_self_check
from tests.writer_self_check.conftest import FakeLLMClient

CHAPTER = "第一章正文，足够长以模拟真实场景。"


def _rules(n: int = 2) -> list[dict[str, Any]]:
    return [
        {"rule_id": f"RULE-{i:03d}", "text": f"测试规则 {i}"} for i in range(1, n + 1)
    ]


def _cases(ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": cid,
            "failure_description": f"{cid} failure",
            "observable": f"{cid} observable",
        }
        for cid in ids
    ]


def _payload(
    *, rule_scores: dict[str, float] | None = None,
    case_evaluation: list[dict[str, Any]] | None = None,
    notes: str = "ok",
) -> str:
    return json.dumps(
        {
            "rule_scores": rule_scores or {},
            "case_evaluation": case_evaluation or [],
            "notes": notes,
        },
        ensure_ascii=False,
    )


def test_self_check_happy_path(mock_llm_client: FakeLLMClient) -> None:
    mock_llm_client.queue(
        _payload(
            rule_scores={"RULE-001": 0.9, "RULE-002": 0.85},
            case_evaluation=[
                {"case_id": "CASE-2026-0001", "addressed": True, "evidence": "段 3"},
            ],
            notes="all good",
        )
    )
    report = writer_self_check(
        chapter_text=CHAPTER,
        injected_rules=_rules(2),
        injected_chunks=None,
        applicable_cases=_cases(["CASE-2026-0001"]),
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
    )
    assert isinstance(report, ComplianceReport)
    assert report.rule_compliance == pytest.approx((0.9 + 0.85) / 2)
    assert report.cases_addressed == ["CASE-2026-0001"]
    assert report.cases_violated == []
    assert report.overall_passed is True
    assert report.notes == "all good"


def test_self_check_threshold_passes_at_0_70(mock_llm_client: FakeLLMClient) -> None:
    mock_llm_client.queue(
        _payload(rule_scores={"RULE-001": 0.7, "RULE-002": 0.7})
    )
    report = writer_self_check(
        chapter_text=CHAPTER,
        injected_rules=_rules(2),
        injected_chunks=None,
        applicable_cases=[],
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
    )
    assert report.rule_compliance == pytest.approx(0.70)
    assert report.overall_passed is True


def test_self_check_case_violated_blocks_pass(
    mock_llm_client: FakeLLMClient,
) -> None:
    mock_llm_client.queue(
        _payload(
            rule_scores={"RULE-001": 1.0, "RULE-002": 1.0},
            case_evaluation=[
                {"case_id": "CASE-2026-0001", "addressed": True},
                {"case_id": "CASE-2026-0002", "addressed": False, "evidence": "miss"},
            ],
        )
    )
    report = writer_self_check(
        chapter_text=CHAPTER,
        injected_rules=_rules(2),
        injected_chunks=None,
        applicable_cases=_cases(["CASE-2026-0001", "CASE-2026-0002"]),
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
    )
    assert report.rule_compliance == pytest.approx(1.0)
    assert report.cases_addressed == ["CASE-2026-0001"]
    assert report.cases_violated == ["CASE-2026-0002"]
    assert report.overall_passed is False


def test_self_check_chunk_borrowing_is_none_in_m3(
    mock_llm_client: FakeLLMClient,
) -> None:
    mock_llm_client.queue(_payload(rule_scores={"RULE-001": 1.0, "RULE-002": 1.0}))
    report = writer_self_check(
        chapter_text=CHAPTER,
        injected_rules=_rules(2),
        injected_chunks=[{"chunk_id": "C-1", "text": "范文"}],  # 即便有 chunks 也忽略
        applicable_cases=[],
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
    )
    assert report.chunk_borrowing is None


def test_self_check_llm_failure_returns_failed_report(
    mock_llm_client: FakeLLMClient,
) -> None:
    # 三次都返回不可解析的输出（max_retries=3）
    mock_llm_client.queue("not json at all")
    mock_llm_client.queue("still garbage")
    mock_llm_client.queue("nope")
    cases = _cases(["CASE-2026-0001", "CASE-2026-0002"])
    rules = _rules(2)
    report = writer_self_check(
        chapter_text=CHAPTER,
        injected_rules=rules,
        injected_chunks=None,
        applicable_cases=cases,
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
        max_retries=3,
    )
    assert report.overall_passed is False
    assert report.notes == "self_check_failed"
    assert report.cases_violated == ["CASE-2026-0001", "CASE-2026-0002"]
    assert report.cases_addressed == []
    assert report.rule_compliance == 0.0
    assert report.raw_scores == {"missing": ["RULE-001", "RULE-002"]}
    assert len(mock_llm_client.calls) == 3


def test_self_check_missing_rule_score_treated_as_zero(
    mock_llm_client: FakeLLMClient,
) -> None:
    # 只给 RULE-001 评分，RULE-002 漏给 → 按 0 计入
    mock_llm_client.queue(_payload(rule_scores={"RULE-001": 1.0}))
    report = writer_self_check(
        chapter_text=CHAPTER,
        injected_rules=_rules(2),
        injected_chunks=None,
        applicable_cases=[],
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
    )
    assert report.rule_compliance == pytest.approx(0.5)
    assert report.overall_passed is False  # 0.5 < 0.70


def test_self_check_empty_cases_skips_case_block(
    mock_llm_client: FakeLLMClient,
) -> None:
    mock_llm_client.queue(_payload(rule_scores={"RULE-001": 0.8, "RULE-002": 0.8}))
    report = writer_self_check(
        chapter_text=CHAPTER,
        injected_rules=_rules(2),
        injected_chunks=None,
        applicable_cases=[],
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
    )
    assert report.cases_addressed == []
    assert report.cases_violated == []
    assert report.overall_passed is True
    # prompt 中应渲染了"无"占位
    sent_prompt = mock_llm_client.calls[0]["messages"][0]["content"]
    assert "（无）" in sent_prompt
