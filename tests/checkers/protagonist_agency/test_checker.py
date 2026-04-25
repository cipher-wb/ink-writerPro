"""protagonist-agency-checker 单元测试 — spec §4.2 + Q8。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from ink_writer.checkers.protagonist_agency import AgencyReport, check_protagonist_agency
from tests.checkers.conftest import FakeLLMClient

LONG_CHAPTER = "正文段落。" * 200  # 约 1200 字，远超 500 字门槛
SHORT_CHAPTER = "短章节。" * 10  # 约 40 字
PROTAGONIST = "萧尘"


def _payload(
    *,
    has_active: bool = True,
    has_plot_drive: bool = True,
    count: int = 1,
    decisions: list[dict[str, Any]] | None = None,
    notes: str = "ok",
) -> str:
    if decisions is None:
        decisions = (
            [
                {
                    "decision": "主角主动出手干预",
                    "drives_plot": has_plot_drive,
                    "consequence": "局势改变，主线推进",
                }
            ]
            if has_active
            else []
        )
    return json.dumps(
        {
            "has_active_decision": has_active,
            "has_plot_drive": has_plot_drive,
            "decision_count": count,
            "decisions": decisions,
            "notes": notes,
        },
        ensure_ascii=False,
    )


def test_happy_path(mock_llm_client: FakeLLMClient) -> None:
    mock_llm_client.queue(
        _payload(has_active=True, has_plot_drive=True, count=2, notes="strong agency")
    )
    report = check_protagonist_agency(
        chapter_text=LONG_CHAPTER,
        protagonist_name=PROTAGONIST,
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
    )
    assert isinstance(report, AgencyReport)
    assert report.has_active_decision is True
    assert report.has_plot_drive is True
    assert report.decision_count == 2
    # score = 0.5*1 + 0.3*1 + 0.2*min(2/2,1) = 1.0
    assert report.score == pytest.approx(1.0)
    assert report.block_threshold == 0.60
    assert report.blocked is False
    assert report.cases_hit == []
    assert report.notes == "strong agency"
    assert report.decision_summaries  # 至少一条 summary
    # prompt 中应含主角名
    assert PROTAGONIST in mock_llm_client.calls[0]["messages"][0]["content"]


def test_no_active_decision_blocks(mock_llm_client: FakeLLMClient) -> None:
    mock_llm_client.queue(
        _payload(
            has_active=False,
            has_plot_drive=False,
            count=0,
            decisions=[],
        )
    )
    report = check_protagonist_agency(
        chapter_text=LONG_CHAPTER,
        protagonist_name=PROTAGONIST,
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
    )
    # score = 0
    assert report.score == pytest.approx(0.0)
    assert report.blocked is True
    assert report.has_active_decision is False


def test_partial_passes(mock_llm_client: FakeLLMClient) -> None:
    # has_active=True (0.5), has_plot_drive=False (0), count=1 → 0.2*0.5 = 0.1 → 0.60
    mock_llm_client.queue(
        _payload(
            has_active=True,
            has_plot_drive=False,
            count=1,
            decisions=[
                {"decision": "选择留下", "drives_plot": False, "consequence": ""},
            ],
        )
    )
    report = check_protagonist_agency(
        chapter_text=LONG_CHAPTER,
        protagonist_name=PROTAGONIST,
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
    )
    # 0.5 + 0 + 0.2 * min(1/2, 1) = 0.5 + 0.1 = 0.60
    assert report.score == pytest.approx(0.60)
    # 0.60 not < 0.60 → 不阻断
    assert report.blocked is False


def test_score_threshold_boundary(mock_llm_client: FakeLLMClient) -> None:
    # has_active=True (0.5), has_plot_drive=False (0), count=0 → 0.5 < 0.60 → blocked
    mock_llm_client.queue(
        _payload(
            has_active=True,
            has_plot_drive=False,
            count=0,
            decisions=[],
        )
    )
    report = check_protagonist_agency(
        chapter_text=LONG_CHAPTER,
        protagonist_name=PROTAGONIST,
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
    )
    assert report.score == pytest.approx(0.50)
    assert report.blocked is True


def test_llm_json_failure_blocks_with_score_zero(
    mock_llm_client: FakeLLMClient,
) -> None:
    mock_llm_client.queue("not json at all")
    mock_llm_client.queue("still garbage")
    mock_llm_client.queue("nope")
    report = check_protagonist_agency(
        chapter_text=LONG_CHAPTER,
        protagonist_name=PROTAGONIST,
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
        max_retries=3,
    )
    assert report.score == 0.0
    assert report.blocked is True
    assert report.notes == "checker_failed"
    assert report.has_active_decision is False
    assert report.decision_count == 0
    assert len(mock_llm_client.calls) == 3


def test_short_chapter_skips_check(mock_llm_client: FakeLLMClient) -> None:
    report = check_protagonist_agency(
        chapter_text=SHORT_CHAPTER,
        protagonist_name=PROTAGONIST,
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
    )
    assert report.score == 0.0
    assert report.blocked is False
    assert report.notes == "skipped_short_chapter"
    # 不应调用 LLM
    assert mock_llm_client.calls == []
