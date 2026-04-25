"""conflict-skeleton-checker 单元测试 — spec §4.1 + Q6+Q7。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from ink_writer.checkers.conflict_skeleton import ConflictReport, check_conflict_skeleton
from tests.checkers.conftest import FakeLLMClient

LONG_CHAPTER = "正文段落。" * 200  # 约 1200 字，远超 500 字门槛
SHORT_CHAPTER = "短章节。" * 10  # 约 40 字


def _payload(
    *,
    has_conflict: bool = True,
    count: int = 1,
    three_stage: bool = True,
    conflicts: list[dict[str, Any]] | None = None,
    notes: str = "ok",
) -> str:
    if conflicts is None:
        conflicts = (
            [
                {
                    "friction_point": "对手出现",
                    "escalation": "争执升级为冲突",
                    "interim_resolution": "本章末暂时退场",
                }
            ]
            if three_stage
            else []
        )
    return json.dumps(
        {
            "has_explicit_conflict": has_conflict,
            "conflict_count": count,
            "has_three_stage_structure": three_stage,
            "conflicts": conflicts,
            "notes": notes,
        },
        ensure_ascii=False,
    )


def test_happy_path_with_clear_conflict(mock_llm_client: FakeLLMClient) -> None:
    mock_llm_client.queue(
        _payload(has_conflict=True, count=2, three_stage=True, notes="strong")
    )
    report = check_conflict_skeleton(
        chapter_text=LONG_CHAPTER,
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
    )
    assert isinstance(report, ConflictReport)
    assert report.has_explicit_conflict is True
    assert report.conflict_count == 2
    assert report.has_three_stage_structure is True
    # score = 0.5*1 + 0.3*1 + 0.2*min(2/2,1) = 1.0
    assert report.score == pytest.approx(1.0)
    assert report.block_threshold == 0.60
    assert report.blocked is False
    assert report.cases_hit == []
    assert report.notes == "strong"
    assert report.conflict_summaries  # 至少一条 summary


def test_no_explicit_conflict_blocks(mock_llm_client: FakeLLMClient) -> None:
    mock_llm_client.queue(
        _payload(has_conflict=False, count=0, three_stage=False, conflicts=[])
    )
    report = check_conflict_skeleton(
        chapter_text=LONG_CHAPTER,
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
    )
    # score = 0
    assert report.score == pytest.approx(0.0)
    assert report.blocked is True
    assert report.has_explicit_conflict is False


def test_partial_three_stage_structure(mock_llm_client: FakeLLMClient) -> None:
    # has_conflict=True (0.5), three_stage=False (0), count=1 → 0.2*0.5=0.1 → 0.6
    mock_llm_client.queue(
        _payload(
            has_conflict=True,
            count=1,
            three_stage=False,
            conflicts=[{"friction_point": "争执", "escalation": "", "interim_resolution": ""}],
        )
    )
    report = check_conflict_skeleton(
        chapter_text=LONG_CHAPTER,
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
    )
    # 0.5 + 0 + 0.2 * min(1/2, 1) = 0.5 + 0.1 = 0.60
    assert report.score == pytest.approx(0.60)
    # 0.60 not < 0.60 → 不阻断
    assert report.blocked is False


def test_score_threshold_boundary(mock_llm_client: FakeLLMClient) -> None:
    # has_conflict=True (0.5), three_stage=False (0), count=0 → 0.5 < 0.60 → blocked
    mock_llm_client.queue(
        _payload(has_conflict=True, count=0, three_stage=False, conflicts=[])
    )
    report = check_conflict_skeleton(
        chapter_text=LONG_CHAPTER,
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
    report = check_conflict_skeleton(
        chapter_text=LONG_CHAPTER,
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
        max_retries=3,
    )
    assert report.score == 0.0
    assert report.blocked is True
    assert report.notes == "checker_failed"
    assert report.has_explicit_conflict is False
    assert report.conflict_count == 0
    assert len(mock_llm_client.calls) == 3


def test_short_chapter_skips_check(mock_llm_client: FakeLLMClient) -> None:
    report = check_conflict_skeleton(
        chapter_text=SHORT_CHAPTER,
        book="书",
        chapter="0001",
        llm_client=mock_llm_client,
    )
    assert report.score == 0.0
    assert report.blocked is False
    assert report.notes == "skipped_short_chapter"
    # 不应调用 LLM
    assert mock_llm_client.calls == []
