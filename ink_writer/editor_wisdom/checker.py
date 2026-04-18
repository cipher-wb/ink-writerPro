"""Editor-wisdom checker: scores chapters against retrieved editor rules via LLM."""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema

from ink_writer.editor_wisdom.config import EditorWisdomConfig, load_config
from ink_writer.editor_wisdom.exceptions import EditorWisdomIndexMissingError
from ink_writer.editor_wisdom.models import HAIKU_MODEL
from ink_writer.editor_wisdom.retriever import Rule

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "editor-check.schema.json"

SYSTEM_PROMPT = """你是一名起点金牌编辑审查助手。你需要根据提供的编辑规则逐条审查章节正文。

对每条规则：
1. 判断正文是否违反该规则
2. 如果违反，引用原文中违规段落（不超过100字）
3. 给出具体的修复建议

只输出violations和summary，不要输出评分。最终输出严格JSON格式，不要输出其他内容。"""


def _build_user_prompt(chapter_text: str, chapter_no: int, rules: list[Rule]) -> str:
    rules_text = "\n".join(
        f"- [{r.severity}] {r.id}: {r.rule}" for r in rules
    )
    return f"""## 章节信息
章节号: {chapter_no}

## 编辑规则（按严重度排序）
{rules_text}

## 章节正文
{chapter_text[:5000]}

## 输出要求
输出严格JSON，格式如下（不要包含score字段，评分由服务端计算）：
{{
  "violations": [
    {{
      "rule_id": "<规则ID>",
      "quote": "<违规原文引用，不超过100字>",
      "severity": "<hard|soft|info>",
      "fix_suggestion": "<修复建议>"
    }}
  ],
  "summary": "<综合评价>"
}}"""


def _validate_result(result: dict) -> dict:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(instance=result, schema=schema)
    return result


def _compute_score(violations: list[dict]) -> float:
    """Sole source of truth for chapter score.

    US-015: switched from linear subtraction to exponential decay.
    Formula: score = 1.0 * (0.7 ** hard_count) * (0.9 ** soft_count).
    Rationale: prevents a handful of soft violations from dragging the score below the
    golden-three hard threshold; each additional violation hurts proportionally less.
    info-severity violations carry no penalty.
    """
    hard_count = 0
    soft_count = 0
    for v in violations:
        if v["severity"] == "hard":
            hard_count += 1
        elif v["severity"] == "soft":
            soft_count += 1
    score = 1.0 * (0.7 ** hard_count) * (0.9 ** soft_count)
    return max(0.0, round(score, 2))


def check_chapter(
    chapter_text: str,
    chapter_no: int,
    rules: list[Rule],
    *,
    anthropic_client: object | None = None,
    model: str = HAIKU_MODEL,
    config: EditorWisdomConfig | None = None,
) -> dict:
    """Score a chapter against editor-wisdom rules via LLM.

    Args:
        chapter_text: The chapter text to check.
        chapter_no: The chapter number.
        rules: Retrieved editor rules to check against.
        anthropic_client: An Anthropic client instance. If None, creates one.
        model: Model to use for the check.
        config: Editor wisdom config. If None, loads from default path.

    Returns:
        A validated result dict matching editor-check.schema.json.
    """
    if config is None:
        config = load_config()

    if not rules:
        if config.enabled:
            raise EditorWisdomIndexMissingError(
                "check_chapter called with empty rules while editor-wisdom is enabled. "
                "This indicates the index is missing or retrieval failed upstream."
            )
        result = {
            "agent": "editor-wisdom-checker",
            "chapter": chapter_no,
            "score": 1.0,
            "violations": [],
            "summary": "无可用编辑规则，跳过检查。",
        }
        _validate_result(result)
        return result

    user_prompt = _build_user_prompt(chapter_text, chapter_no, rules)

    if anthropic_client is not None:
        cached_system = [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=2048,
            system=cached_system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = response.content[0].text.strip()
        from .llm_backend import _record_cache_metrics
        _record_cache_metrics(response, model, agent="editor-wisdom-checker")
    else:
        from .llm_backend import call_llm
        raw_text = call_llm(model, SYSTEM_PROMPT, user_prompt, max_tokens=2048).strip()
    fence_match = re.match(r'^```(?:\w+)?\n([\s\S]*?)\n```$', raw_text)
    if fence_match:
        raw_text = fence_match.group(1).strip()

    result = json.loads(raw_text)

    result["chapter"] = chapter_no
    result["agent"] = "editor-wisdom-checker"
    result["score"] = _compute_score(result.get("violations", []))

    _validate_result(result)
    return result
