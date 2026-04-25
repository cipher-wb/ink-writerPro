"""protagonist-motive-checker 单元测试 — M4 spec §3.4 + Q4。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from ink_writer.checkers.protagonist_motive import (
    ProtagonistMotiveReport,
    check_protagonist_motive,
)
from tests.checkers.conftest import FakeLLMClient


def _payload(dims: dict[str, Any], notes: str = "") -> str:
    obj = dict(dims)
    obj["notes"] = notes
    return json.dumps(obj, ensure_ascii=False)


GOOD_DESCRIPTION = (
    "顾望安是战争遗孤，亲眼见过家乡焚毁。他想找到当年放走幸存者的那位敌国军官，"
    "亲口问一句为什么；却又害怕一旦得到答案，自己十年来支撑活下去的恨意会瞬间崩塌。"
)
SHORT_DESCRIPTION = "主角想变强。"


def test_high_score_passes(mock_llm_client: FakeLLMClient) -> None:
    # mean = (0.9 + 0.85 + 0.8) / 3 = 0.85 >= 0.65 → pass
    mock_llm_client.queue(
        _payload(
            {
                "resonance": 0.90,
                "specific_goal": 0.85,
                "inner_conflict": 0.80,
            },
            notes="情感真挚目标具体",
        )
    )
    report = check_protagonist_motive(
        description=GOOD_DESCRIPTION,
        llm_client=mock_llm_client,
    )
    assert isinstance(report, ProtagonistMotiveReport)
    assert report.score == pytest.approx(0.85)
    assert report.blocked is False
    assert set(report.dim_scores.keys()) == {
        "resonance",
        "specific_goal",
        "inner_conflict",
    }
    assert report.dim_scores["resonance"] == pytest.approx(0.90)
    assert report.cases_hit == []


def test_low_score_blocks(mock_llm_client: FakeLLMClient) -> None:
    # mean = (0.5 + 0.4 + 0.5) / 3 ≈ 0.4667 < 0.65 → blocked
    mock_llm_client.queue(
        _payload(
            {
                "resonance": 0.50,
                "specific_goal": 0.40,
                "inner_conflict": 0.50,
            },
            notes="目标抽象，无内在矛盾",
        )
    )
    report = check_protagonist_motive(
        description="主角想要变得很强大去称霸天下走向人生巅峰开启逆天之路",
        llm_client=mock_llm_client,
    )
    assert report.score == pytest.approx(0.4666666, abs=1e-3)
    assert report.blocked is True


def test_short_description_blocks(mock_llm_client: FakeLLMClient) -> None:
    report = check_protagonist_motive(
        description=SHORT_DESCRIPTION,
        llm_client=mock_llm_client,
    )
    assert report.blocked is True
    assert report.notes == "description_too_short"
    assert report.score == 0.0
    # 不应调用 LLM
    assert mock_llm_client.calls == []


def test_llm_failure_blocks(mock_llm_client: FakeLLMClient) -> None:
    mock_llm_client.queue("not json at all")
    mock_llm_client.queue("still garbage")
    report = check_protagonist_motive(
        description=GOOD_DESCRIPTION,
        llm_client=mock_llm_client,
        max_retries=2,
    )
    assert report.score == 0.0
    assert report.blocked is True
    assert report.notes.startswith("checker_failed:")
    assert len(mock_llm_client.calls) == 2
