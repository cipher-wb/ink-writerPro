"""genre-novelty-checker 单元测试 — M4 spec §3.1 + Q3。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from ink_writer.checkers.genre_novelty import GenreNoveltyReport, check_genre_novelty
from tests.checkers.conftest import FakeLLMClient

SAMPLE_TOP200: list[dict[str, Any]] = [
    {
        "rank": 1,
        "title": "都市重生之巅峰人生",
        "genre_tags": ["都市", "重生"],
        "intro_one_liner": "重生回到 18 岁，前世是商业大佬，这一世要走向人生巅峰。",
    },
    {
        "rank": 2,
        "title": "玄幻之我能融合一切",
        "genre_tags": ["玄幻", "系统"],
        "intro_one_liner": "穿越到玄幻世界，觉醒万道融合系统。",
    },
    {
        "rank": 3,
        "title": "末世之超神进化",
        "genre_tags": ["末世", "进化"],
        "intro_one_liner": "末世来临，主角觉醒进化金手指。",
    },
]


def _payload(top5: list[dict[str, Any]]) -> str:
    return json.dumps(top5, ensure_ascii=False)


def test_high_similarity_blocks(mock_llm_client: FakeLLMClient) -> None:
    # max similarity 0.92 → score = 0.08 < 0.40 → blocked
    mock_llm_client.queue(
        _payload(
            [
                {"rank": 1, "similarity": 0.92, "reason": "题材+主线骨架几乎复刻"},
                {"rank": 3, "similarity": 0.55, "reason": "进化设定相似"},
                {"rank": 2, "similarity": 0.30, "reason": "玄幻系统稍有重叠"},
                {"rank": 1, "similarity": 0.20, "reason": "都市背景接近"},
                {"rank": 2, "similarity": 0.10, "reason": "弱相关"},
            ]
        )
    )
    report = check_genre_novelty(
        genre_tags=["都市", "重生"],
        main_plot_one_liner="重生回到大学，前世是商场失败者，这一世要逆袭",
        top200=SAMPLE_TOP200,
        llm_client=mock_llm_client,
    )
    assert isinstance(report, GenreNoveltyReport)
    assert report.score == pytest.approx(0.08)
    assert report.blocked is True
    assert len(report.top5_similar) == 5
    # 第 1 条相似度最高，应附带 title
    assert report.top5_similar[0]["rank"] == 1
    assert report.top5_similar[0]["title"] == "都市重生之巅峰人生"
    assert report.top5_similar[0]["similarity"] == pytest.approx(0.92)
    # cases_hit 由 planning_review 注入，本 checker 不主动填
    assert report.cases_hit == []


def test_low_similarity_passes(mock_llm_client: FakeLLMClient) -> None:
    # max similarity 0.30 → score = 0.70 >= 0.40 → pass
    mock_llm_client.queue(
        _payload(
            [
                {"rank": 1, "similarity": 0.30, "reason": "弱相关"},
                {"rank": 2, "similarity": 0.20, "reason": "弱相关"},
                {"rank": 3, "similarity": 0.15, "reason": "弱相关"},
                {"rank": 1, "similarity": 0.10, "reason": "弱相关"},
                {"rank": 2, "similarity": 0.05, "reason": "几乎无关"},
            ]
        )
    )
    report = check_genre_novelty(
        genre_tags=["科幻", "硬核"],
        main_plot_one_liner="星际深空考古队意外触发古文明遗物",
        top200=SAMPLE_TOP200,
        llm_client=mock_llm_client,
    )
    assert report.score == pytest.approx(0.70)
    assert report.blocked is False
    assert len(report.top5_similar) == 5


def test_empty_top200_skipped(mock_llm_client: FakeLLMClient) -> None:
    report = check_genre_novelty(
        genre_tags=["都市"],
        main_plot_one_liner="任意主线",
        top200=[],
        llm_client=mock_llm_client,
    )
    assert report.score == pytest.approx(1.0)
    assert report.blocked is False
    assert report.notes == "empty_top200_skipped"
    assert report.top5_similar == []
    # 不应调用 LLM
    assert mock_llm_client.calls == []


def test_llm_failure_blocks(mock_llm_client: FakeLLMClient) -> None:
    mock_llm_client.queue("not json at all")
    mock_llm_client.queue("still garbage")
    report = check_genre_novelty(
        genre_tags=["都市"],
        main_plot_one_liner="任意主线",
        top200=SAMPLE_TOP200,
        llm_client=mock_llm_client,
        max_retries=2,
    )
    assert report.score == 0.0
    assert report.blocked is True
    assert report.notes.startswith("checker_failed:")
    assert report.top5_similar == []
    assert len(mock_llm_client.calls) == 2
