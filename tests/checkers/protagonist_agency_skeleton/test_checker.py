"""protagonist-agency-skeleton-checker 单元测试 — M4 spec §3.6 + PRD US-010。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from ink_writer.checkers.protagonist_agency_skeleton import (
    ProtagonistAgencySkeletonReport,
    check_protagonist_agency_skeleton,
)
from tests.checkers.conftest import FakeLLMClient

SAMPLE_SKELETON: list[dict[str, Any]] = [
    {"chapter_idx": 1, "summary": "顾望安主动潜入敌国军营寻找当年放走幸存者的军官。"},
    {"chapter_idx": 2, "summary": "顾望安做出关键决定：放弃复仇路径，转而保护战时孤儿。"},
    {"chapter_idx": 3, "summary": "顾望安主动联络旧识，组建情报网络。"},
]


def _payload(items: list[dict[str, Any]]) -> str:
    return json.dumps(items, ensure_ascii=False)


def test_high_agency_passes(mock_llm_client: FakeLLMClient) -> None:
    # mean(0.9, 0.85, 0.8) = 0.85 >= 0.55 → pass
    mock_llm_client.queue(
        _payload(
            [
                {"chapter_idx": 1, "agency_score": 0.9, "reason": "主动潜入"},
                {"chapter_idx": 2, "agency_score": 0.85, "reason": "关键决定"},
                {"chapter_idx": 3, "agency_score": 0.8, "reason": "主动联络"},
            ]
        )
    )
    report = check_protagonist_agency_skeleton(
        outline_volume_skeleton=SAMPLE_SKELETON,
        llm_client=mock_llm_client,
    )
    assert isinstance(report, ProtagonistAgencySkeletonReport)
    assert report.score == pytest.approx(0.85)
    assert report.blocked is False
    assert len(report.per_chapter) == 3
    assert report.per_chapter[0]["chapter_idx"] == 1
    assert report.per_chapter[0]["agency_score"] == pytest.approx(0.9)
    assert report.cases_hit == []


def test_low_agency_blocks(mock_llm_client: FakeLLMClient) -> None:
    # mean(0.3, 0.2, 0.4) ≈ 0.30 < 0.55 → blocked
    mock_llm_client.queue(
        _payload(
            [
                {"chapter_idx": 1, "agency_score": 0.3, "reason": "被动卷入"},
                {"chapter_idx": 2, "agency_score": 0.2, "reason": "工具人"},
                {"chapter_idx": 3, "agency_score": 0.4, "reason": "反应式"},
            ]
        )
    )
    report = check_protagonist_agency_skeleton(
        outline_volume_skeleton=SAMPLE_SKELETON,
        llm_client=mock_llm_client,
    )
    assert report.score == pytest.approx(0.3, abs=1e-3)
    assert report.blocked is True
    assert len(report.per_chapter) == 3


def test_empty_skeleton_blocks(mock_llm_client: FakeLLMClient) -> None:
    report = check_protagonist_agency_skeleton(
        outline_volume_skeleton=[],
        llm_client=mock_llm_client,
    )
    assert report.score == 0.0
    assert report.blocked is True
    assert report.notes == "empty_skeleton"
    assert report.per_chapter == []
    assert mock_llm_client.calls == []


def test_llm_failure_blocks(mock_llm_client: FakeLLMClient) -> None:
    mock_llm_client.queue("not json at all")
    mock_llm_client.queue("still garbage")
    report = check_protagonist_agency_skeleton(
        outline_volume_skeleton=SAMPLE_SKELETON,
        llm_client=mock_llm_client,
        max_retries=2,
    )
    assert report.score == 0.0
    assert report.blocked is True
    assert report.notes.startswith("checker_failed:")
    assert report.per_chapter == []
    assert len(mock_llm_client.calls) == 2
