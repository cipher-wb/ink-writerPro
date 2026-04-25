"""chapter-hook-density-checker 单元测试 — M4 spec §3.7 + PRD US-011。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from ink_writer.checkers.chapter_hook_density import (
    ChapterHookDensityReport,
    check_chapter_hook_density,
)
from tests.checkers.conftest import FakeLLMClient

SAMPLE_SKELETON: list[dict[str, Any]] = [
    {"chapter_idx": 1, "summary": "顾望安发现古卷一角，遭黑衣人围杀，悬崖坠落生死未卜。"},
    {"chapter_idx": 2, "summary": "醒来发现自己被裴惊戎所救，却被告知本派已遭灭门。"},
    {"chapter_idx": 3, "summary": "顾望安潜入敌国，意外撞见师妹蓝漪却不认得自己。"},
    {"chapter_idx": 4, "summary": "查到旧档：当年灭门主谋竟是自己亲生父亲。"},
]


def _payload(items: list[dict[str, Any]]) -> str:
    return json.dumps(items, ensure_ascii=False)


def test_high_density_passes(mock_llm_client: FakeLLMClient) -> None:
    # 4 章 strong=3（>=0.5） / total=4 = 0.75 >= 0.70 → pass
    mock_llm_client.queue(
        _payload(
            [
                {"chapter_idx": 1, "hook_strength": 0.9, "reason": "高危机+悬念"},
                {"chapter_idx": 2, "hook_strength": 0.8, "reason": "重大反转"},
                {"chapter_idx": 3, "hook_strength": 0.6, "reason": "信息差"},
                {"chapter_idx": 4, "hook_strength": 0.4, "reason": "弱钩子"},
            ]
        )
    )
    report = check_chapter_hook_density(
        outline_volume_skeleton=SAMPLE_SKELETON,
        llm_client=mock_llm_client,
    )
    assert isinstance(report, ChapterHookDensityReport)
    assert report.total_count == 4
    assert report.strong_count == 3
    assert report.score == pytest.approx(0.75)
    assert report.blocked is False
    assert len(report.per_chapter) == 4
    assert report.per_chapter[0]["strong"] is True
    assert report.per_chapter[3]["strong"] is False
    assert report.cases_hit == []


def test_low_density_blocks(mock_llm_client: FakeLLMClient) -> None:
    # 4 章 strong=1（仅第 1 章）/ total=4 = 0.25 < 0.70 → blocked
    mock_llm_client.queue(
        _payload(
            [
                {"chapter_idx": 1, "hook_strength": 0.7, "reason": "高危机"},
                {"chapter_idx": 2, "hook_strength": 0.3, "reason": "无悬念"},
                {"chapter_idx": 3, "hook_strength": 0.2, "reason": "仅交代结果"},
                {"chapter_idx": 4, "hook_strength": 0.1, "reason": "无钩子"},
            ]
        )
    )
    report = check_chapter_hook_density(
        outline_volume_skeleton=SAMPLE_SKELETON,
        llm_client=mock_llm_client,
    )
    assert report.total_count == 4
    assert report.strong_count == 1
    assert report.score == pytest.approx(0.25)
    assert report.blocked is True
    assert len(report.per_chapter) == 4


def test_empty_skeleton_blocks(mock_llm_client: FakeLLMClient) -> None:
    report = check_chapter_hook_density(
        outline_volume_skeleton=[],
        llm_client=mock_llm_client,
    )
    assert report.score == 0.0
    assert report.blocked is True
    assert report.notes == "empty_skeleton"
    assert report.per_chapter == []
    assert report.total_count == 0
    assert report.strong_count == 0
    assert mock_llm_client.calls == []


def test_llm_failure_blocks(mock_llm_client: FakeLLMClient) -> None:
    mock_llm_client.queue("not json at all")
    mock_llm_client.queue("still garbage")
    report = check_chapter_hook_density(
        outline_volume_skeleton=SAMPLE_SKELETON,
        llm_client=mock_llm_client,
        max_retries=2,
    )
    assert report.score == 0.0
    assert report.blocked is True
    assert report.notes.startswith("checker_failed:")
    assert report.per_chapter == []
    assert report.total_count == 0
    assert report.strong_count == 0
    assert len(mock_llm_client.calls) == 2
