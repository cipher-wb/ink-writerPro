"""golden-finger-spec-checker 单元测试 — M4 spec §3.2 + Q4。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from ink_writer.checkers.golden_finger_spec import (
    GoldenFingerSpecReport,
    check_golden_finger_spec,
)
from tests.checkers.conftest import FakeLLMClient


def _payload(dims: dict[str, Any], notes: str = "") -> str:
    obj = dict(dims)
    obj["notes"] = notes
    return json.dumps(obj, ensure_ascii=False)


GOOD_DESCRIPTION = (
    "主角觉醒『万道归一』之力：可融合任意两种已掌握的功法生成第三种新功法，"
    "代价是融合后 24 小时内无法再次融合，且只能保留一种结果，失败则双双失效。"
)
SHORT_DESCRIPTION = "主角有金手指。"


def test_high_score_passes(mock_llm_client: FakeLLMClient) -> None:
    # mean = (0.9 + 0.85 + 0.8 + 0.85) / 4 = 0.85 >= 0.65 → pass
    mock_llm_client.queue(
        _payload(
            {
                "clarity": 0.90,
                "falsifiability": 0.85,
                "boundary": 0.80,
                "growth_curve": 0.85,
            },
            notes="规格清晰，限制完整",
        )
    )
    report = check_golden_finger_spec(
        description=GOOD_DESCRIPTION,
        llm_client=mock_llm_client,
    )
    assert isinstance(report, GoldenFingerSpecReport)
    assert report.score == pytest.approx(0.85)
    assert report.blocked is False
    assert set(report.dim_scores.keys()) == {
        "clarity",
        "falsifiability",
        "boundary",
        "growth_curve",
    }
    assert report.dim_scores["clarity"] == pytest.approx(0.90)
    assert report.cases_hit == []


def test_low_score_blocks(mock_llm_client: FakeLLMClient) -> None:
    # mean = (0.5 + 0.4 + 0.5 + 0.4) / 4 = 0.45 < 0.65 → blocked
    mock_llm_client.queue(
        _payload(
            {
                "clarity": 0.50,
                "falsifiability": 0.40,
                "boundary": 0.50,
                "growth_curve": 0.40,
            },
            notes="边界模糊",
        )
    )
    report = check_golden_finger_spec(
        description="主角觉醒了某种神秘的逆天能力可以做很多事情很厉害",
        llm_client=mock_llm_client,
    )
    assert report.score == pytest.approx(0.45)
    assert report.blocked is True


def test_short_description_blocks(mock_llm_client: FakeLLMClient) -> None:
    report = check_golden_finger_spec(
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
    report = check_golden_finger_spec(
        description=GOOD_DESCRIPTION,
        llm_client=mock_llm_client,
        max_retries=2,
    )
    assert report.score == 0.0
    assert report.blocked is True
    assert report.notes.startswith("checker_failed:")
    assert len(mock_llm_client.calls) == 2
