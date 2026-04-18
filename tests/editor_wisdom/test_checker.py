"""Tests for editor-wisdom checker module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import jsonschema
import pytest
from ink_writer.editor_wisdom.config import EditorWisdomConfig
from ink_writer.editor_wisdom.checker import (
    SCHEMA_PATH,
    _compute_score,
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
