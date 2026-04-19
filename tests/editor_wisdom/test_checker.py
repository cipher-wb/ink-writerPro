"""Tests for editor-wisdom checker module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import jsonschema
import pytest
from ink_writer.editor_wisdom.config import EditorWisdomConfig
from ink_writer.editor_wisdom.checker import (
    HEAD_TAIL_SPLIT_MARKER,
    SCHEMA_PATH,
    _build_user_prompt,
    _compute_score,
    _excerpt_chapter_text,
    _validate_result,
    check_chapter,
)
from ink_writer.editor_wisdom.retriever import Rule

SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _make_rule(
    id: str = "EW-0001",
    category: str = "opening",
    rule: str = "测试规则",
    why: str = "测试原因",
    severity: str = "hard",
) -> Rule:
    return Rule(
        id=id, category=category, rule=rule, why=why,
        severity=severity, applies_to=["all_chapters"], source_files=["test.md"],
    )


def _mock_llm_response(violations: list[dict], summary: str = "测试总结") -> MagicMock:
    result = {
        "agent": "editor-wisdom-checker",
        "chapter": 1,
        "score": 0.9,
        "violations": violations,
        "summary": summary,
    }
    content_block = MagicMock()
    content_block.text = json.dumps(result, ensure_ascii=False)
    response = MagicMock()
    response.content = [content_block]
    client = MagicMock()
    client.messages.create.return_value = response
    return client


def test_schema_file_exists() -> None:
    assert SCHEMA_PATH.exists()


def test_empty_rules_returns_perfect_score_when_disabled() -> None:
    config = EditorWisdomConfig(enabled=False)
    result = check_chapter("测试正文", 1, [], config=config)
    assert result["score"] == 1.0
    assert result["violations"] == []
    jsonschema.validate(instance=result, schema=SCHEMA)


def test_empty_rules_raises_when_enabled() -> None:
    from ink_writer.editor_wisdom.exceptions import EditorWisdomIndexMissingError

    config = EditorWisdomConfig(enabled=True)
    with pytest.raises(EditorWisdomIndexMissingError):
        check_chapter("测试正文", 1, [], config=config)


def test_check_with_violations_passes_schema() -> None:
    violations = [
        {
            "rule_id": "EW-0001",
            "quote": "这是违规的原文段落",
            "severity": "hard",
            "fix_suggestion": "删除空景开场，直接进入主角行动",
        },
        {
            "rule_id": "EW-0002",
            "quote": "另一段违规原文",
            "severity": "soft",
            "fix_suggestion": "缩短世界观说明",
        },
    ]
    client = _mock_llm_response(violations)
    rules = [_make_rule("EW-0001"), _make_rule("EW-0002", severity="soft")]

    result = check_chapter("测试正文内容" * 100, 1, rules, anthropic_client=client)
    jsonschema.validate(instance=result, schema=SCHEMA)
    assert result["agent"] == "editor-wisdom-checker"
    assert result["chapter"] == 1
    assert len(result["violations"]) == 2


def test_score_recalculated_from_violations() -> None:
    # US-015: exponential formula — 2 hard + 1 soft → 0.7^2 * 0.9^1 = 0.441 → 0.44
    violations = [
        {"rule_id": "EW-0001", "quote": "x", "severity": "hard", "fix_suggestion": "fix1"},
        {"rule_id": "EW-0002", "quote": "y", "severity": "hard", "fix_suggestion": "fix2"},
        {"rule_id": "EW-0003", "quote": "z", "severity": "soft", "fix_suggestion": "fix3"},
    ]
    client = _mock_llm_response(violations)
    rules = [_make_rule(f"EW-000{i}") for i in range(1, 4)]

    result = check_chapter("正文", 1, rules, anthropic_client=client)
    assert result["score"] == pytest.approx(0.44)


def test_compute_score_hard_only() -> None:
    # US-015: 0.7^3 = 0.343 → 0.34
    violations = [{"severity": "hard"}] * 3
    assert _compute_score(violations) == pytest.approx(0.34)


def test_compute_score_soft_only() -> None:
    # US-015: 0.9^4 = 0.6561 → 0.66
    violations = [{"severity": "soft"}] * 4
    assert _compute_score(violations) == pytest.approx(0.66)


def test_compute_score_info_no_penalty() -> None:
    violations = [{"severity": "info"}] * 10
    assert _compute_score(violations) == 1.0


def test_compute_score_mixed() -> None:
    # US-015: 1 hard + 1 soft + 1 info → 0.7 * 0.9 = 0.63
    violations = [
        {"severity": "hard"},
        {"severity": "soft"},
        {"severity": "info"},
    ]
    assert _compute_score(violations) == pytest.approx(0.63)


def test_compute_score_floor_at_zero() -> None:
    # US-015: 20 hard → 0.7^20 ≈ 0.00080 → round(0.00, 2) == 0.0
    violations = [{"severity": "hard"}] * 20
    assert _compute_score(violations) == 0.0


def test_llm_response_with_markdown_fence() -> None:
    violations = [
        {"rule_id": "EW-0001", "quote": "x", "severity": "hard", "fix_suggestion": "fix"},
    ]
    result_json = json.dumps({
        "agent": "editor-wisdom-checker",
        "chapter": 1,
        "score": 0.9,
        "violations": violations,
        "summary": "测试",
    }, ensure_ascii=False)
    fenced = f"```json\n{result_json}\n```"

    content_block = MagicMock()
    content_block.text = fenced
    response = MagicMock()
    response.content = [content_block]
    client = MagicMock()
    client.messages.create.return_value = response

    result = check_chapter("正文", 1, [_make_rule()], anthropic_client=client)
    jsonschema.validate(instance=result, schema=SCHEMA)
    assert len(result["violations"]) == 1


def test_validate_result_rejects_invalid() -> None:
    with pytest.raises(jsonschema.ValidationError):
        _validate_result({"agent": "wrong", "chapter": 1, "score": 2.0, "violations": [], "summary": "x"})


def test_chapter_no_overridden_in_result() -> None:
    violations = []
    client = _mock_llm_response(violations)
    result = check_chapter("正文", 5, [_make_rule()], anthropic_client=client)
    assert result["chapter"] == 5


def test_llm_score_ignored_server_computed() -> None:
    """US-003: LLM returns score=0.99 but server recomputes from violations."""
    violations = [
        {"rule_id": "EW-0001", "quote": "x", "severity": "hard", "fix_suggestion": "fix1"},
        {"rule_id": "EW-0002", "quote": "y", "severity": "hard", "fix_suggestion": "fix2"},
    ]
    result_with_bad_score = {
        "agent": "editor-wisdom-checker",
        "chapter": 1,
        "score": 0.99,
        "violations": violations,
        "summary": "LLM thinks score is 0.99",
    }
    content_block = MagicMock()
    content_block.text = json.dumps(result_with_bad_score, ensure_ascii=False)
    response = MagicMock()
    response.content = [content_block]
    client = MagicMock()
    client.messages.create.return_value = response

    rules = [_make_rule("EW-0001"), _make_rule("EW-0002")]
    result = check_chapter("正文", 1, rules, anthropic_client=client)
    # US-015: 2 hard → 0.7^2 = 0.49
    assert result["score"] == pytest.approx(0.49)


def test_agent_field_always_correct() -> None:
    client = _mock_llm_response([])
    result = check_chapter("正文", 1, [_make_rule()], anthropic_client=client)
    assert result["agent"] == "editor-wisdom-checker"


# ---------------------------------------------------------------------------
# US-009: 解除 5000 字硬截断，保留章末钩子
# ---------------------------------------------------------------------------


def test_excerpt_short_chapter_passes_through() -> None:
    """4500 字章节（< 7500 上限）原样返回，章末钩子必须保留。"""
    head = "正文开头。" * 300  # 1800 chars
    body = "主干剧情。" * 400  # 2400 chars
    tail = "主角猛然回头，只听一声炸响——欲知后事如何，且听下回分解。"
    chapter = head + body + tail
    assert len(chapter) < 7500

    excerpt = _excerpt_chapter_text(chapter, 7500)
    # 未超限：原样返回（未插入分隔 marker）
    assert HEAD_TAIL_SPLIT_MARKER not in excerpt
    assert excerpt == chapter
    assert "欲知后事" in excerpt


def test_excerpt_long_chapter_keeps_head_and_tail() -> None:
    """8000 字章节分段：头部 3750 + 中段 marker + 尾部 3750，关键首尾信息无丢失。"""
    head_marker = "【本章开篇】"
    tail_marker = "欲知后事如何，请看下章。"
    # 8000+ chars with stable head/tail markers
    filler = "中段枯燥铺垫。" * 1200  # ~8400 chars
    chapter = head_marker + filler + tail_marker
    assert len(chapter) > 7500

    excerpt = _excerpt_chapter_text(chapter, 7500)
    assert HEAD_TAIL_SPLIT_MARKER in excerpt
    assert head_marker in excerpt, "头部关键信息不能被丢弃"
    assert tail_marker in excerpt, "章末钩子必须保留（US-009 核心）"
    # 保留 head+tail 各 half = 3750，再加 marker 长度
    expected_body_len = (7500 // 2) * 2 + len(HEAD_TAIL_SPLIT_MARKER)
    assert len(excerpt) == expected_body_len


def test_build_user_prompt_default_max_chars_is_7500() -> None:
    """_build_user_prompt 的默认 max_chars 必须是 7500。"""
    rules = [_make_rule()]
    # 6000 字 < 7500：原文保留
    chapter = "段落。" * 2000  # 6000 chars
    prompt = _build_user_prompt(chapter, 1, rules)
    assert HEAD_TAIL_SPLIT_MARKER not in prompt
    assert chapter in prompt


def test_build_user_prompt_sees_tail_hook_on_4500_chapter() -> None:
    """4500 字章节 checker 必须看到尾段'欲知后事'钩子（AC 第 3 条）。"""
    hook = "暮色四合，他握紧剑柄——欲知后事如何，下章揭晓。"
    chapter = "正文段落。" * 1100 + hook  # ~5500 chars 正文 + hook
    # 把长度压回 4500 以内：截短正文
    chapter = ("正文段落。" * 800) + hook  # ~4000 + hook
    assert len(chapter) < 7500

    rules = [_make_rule("EW-0099", category="hook", rule="章末钩子不能平淡")]
    client = _mock_llm_response([
        {
            "rule_id": "EW-0099",
            "quote": "欲知后事如何，下章揭晓。",
            "severity": "hard",
            "fix_suggestion": "强化悬念。",
        }
    ])
    result = check_chapter(chapter, 1, rules, anthropic_client=client)

    # 断言 checker 实际发给 LLM 的 prompt 包含章末钩子
    sent_prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "欲知后事" in sent_prompt
    assert result["violations"][0]["rule_id"] == "EW-0099"


def test_build_user_prompt_keeps_endings_on_8000_chapter() -> None:
    """8000 字章节分段不丢头尾关键信息（AC 第 4 条）。"""
    opening = "【开篇标记·主角登场】"
    ending = "【章末钩子·身影消失在夜色里】"
    middle = "中段铺垫文字。" * 1200  # ~8400 chars
    chapter = opening + middle + ending
    assert len(chapter) > 8000

    rules = [_make_rule()]
    client = _mock_llm_response([])
    check_chapter(chapter, 1, rules, anthropic_client=client)

    sent_prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert opening in sent_prompt, "开篇关键信息被砍"
    assert ending in sent_prompt, "章末钩子被砍（US-009 核心问题）"
    assert HEAD_TAIL_SPLIT_MARKER in sent_prompt


def test_build_user_prompt_explicit_max_chars_override() -> None:
    """max_chars 是 kwarg-only 参数，可被调用方下调用于冒烟测试。"""
    chapter = "正文。" * 2000  # ~6000 chars
    prompt = _build_user_prompt(chapter, 1, [_make_rule()], max_chars=1000)
    assert HEAD_TAIL_SPLIT_MARKER in prompt  # 1000 < 6000 触发截断
    # head 500 + tail 500
    assert prompt.count("正文。") < 2000  # 不再全文保留
