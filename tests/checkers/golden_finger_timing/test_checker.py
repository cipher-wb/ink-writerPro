"""golden-finger-timing-checker 单元测试 — M4 spec §3.5 + Q9。"""

from __future__ import annotations

import json
from typing import Any

from ink_writer.checkers.golden_finger_timing import (
    GoldenFingerTimingReport,
    check_golden_finger_timing,
)
from tests.checkers.conftest import FakeLLMClient


def _llm_payload(*, matched: bool, matched_chapter: int | None, reason: str = "") -> str:
    obj: dict[str, Any] = {
        "matched": matched,
        "matched_chapter": matched_chapter,
        "reason": reason,
    }
    return json.dumps(obj, ensure_ascii=False)


_OUTLINE_5 = [
    {"chapter_idx": 1, "summary": "顾望安在战场上拾起一枚古玉佩，玉佩中浮现出万道归一的剑诀残影。"},
    {"chapter_idx": 2, "summary": "顾望安初步触发玉佩力量，第一次施展融合招式击退追兵。"},
    {"chapter_idx": 3, "summary": "顾望安遇到隐世剑修，得知玉佩牵连观之七境的命运。"},
    {"chapter_idx": 4, "summary": "顾望安进入裴家族学，开始系统修行。"},
    {"chapter_idx": 5, "summary": "顾望安与蓝漪初次相遇，结下因缘。"},
]


def test_regex_hit_passes(mock_llm_client: FakeLLMClient) -> None:
    # 关键词命中前 3 章 → 直通，不调 LLM
    report = check_golden_finger_timing(
        outline_volume_skeleton=_OUTLINE_5,
        golden_finger_keywords=["万道归一", "融合"],
        llm_client=mock_llm_client,
    )
    assert isinstance(report, GoldenFingerTimingReport)
    assert report.score == 1.0
    assert report.blocked is False
    assert report.regex_match is True
    assert report.llm_match is None
    assert report.matched_chapter in {1, 2}
    assert mock_llm_client.calls == []
    assert report.cases_hit == []


def test_regex_miss_llm_hit_passes(mock_llm_client: FakeLLMClient) -> None:
    # regex 未命中（关键词字面不在前 3 章 summary）→ 调 LLM；LLM 判定语义命中 → 通过
    mock_llm_client.queue(
        _llm_payload(matched=True, matched_chapter=2, reason="第 2 章已展示金手指融合能力的语义等价")
    )
    report = check_golden_finger_timing(
        outline_volume_skeleton=_OUTLINE_5,
        golden_finger_keywords=["天地同心剑诀"],
        llm_client=mock_llm_client,
    )
    assert report.score == 1.0
    assert report.blocked is False
    assert report.regex_match is False
    assert report.llm_match is True
    assert report.matched_chapter == 2
    assert len(mock_llm_client.calls) == 1


def test_regex_miss_llm_miss_blocks(mock_llm_client: FakeLLMClient) -> None:
    # regex 未命中 + LLM 判定不命中 → 阻断
    mock_llm_client.queue(
        _llm_payload(matched=False, matched_chapter=None, reason="前 3 章未出现金手指")
    )
    report = check_golden_finger_timing(
        outline_volume_skeleton=_OUTLINE_5,
        golden_finger_keywords=["天地同心剑诀"],
        llm_client=mock_llm_client,
    )
    assert report.score == 0.0
    assert report.blocked is True
    assert report.regex_match is False
    assert report.llm_match is False
    assert report.matched_chapter is None
    assert len(mock_llm_client.calls) == 1


def test_outline_too_short_blocks(mock_llm_client: FakeLLMClient) -> None:
    # < 3 章 → 直接 blocked，不调 LLM
    report = check_golden_finger_timing(
        outline_volume_skeleton=_OUTLINE_5[:2],
        golden_finger_keywords=["万道归一"],
        llm_client=mock_llm_client,
    )
    assert report.blocked is True
    assert report.score == 0.0
    assert report.notes.startswith("outline_too_short:")
    assert "2" in report.notes
    assert mock_llm_client.calls == []


def test_empty_keywords_blocks(mock_llm_client: FakeLLMClient) -> None:
    # 空 keywords → 直接 blocked，不调 LLM
    report = check_golden_finger_timing(
        outline_volume_skeleton=_OUTLINE_5,
        golden_finger_keywords=[],
        llm_client=mock_llm_client,
    )
    assert report.blocked is True
    assert report.score == 0.0
    assert report.notes == "empty_keywords"
    assert mock_llm_client.calls == []
