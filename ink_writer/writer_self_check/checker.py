"""writer_self_check() — M3 写完比对（spec §3 + Q1+Q2+Q15）。

调用方传入：
  - chapter_text: 章节正文
  - injected_rules: list[dict]，每条至少含 ``rule_id`` 与 ``text``
  - injected_chunks: 范文 chunks（M3 期保留为 None / 空列表占位；chunk_borrowing
    始终为 None，spec §3.5 风险 8）
  - applicable_cases: list[dict]，每条至少含 ``case_id``；可选 ``failure_description``、
    ``observable``
  - llm_client: 兼容 ``llm_client.messages.create(...)`` 的对象，返回有 ``.content[0].text`` 的响应

输出 ComplianceReport。规则：
  - rule_compliance = mean(rule_scores)，漏给的 rule_id 按 0 计；injected_rules 为空 → 1.0
  - cases 二分：LLM 未给的 case 默认 addressed=False（保守）
  - chunk_borrowing 始终 None
  - LLM JSON 解析失败重试 max_retries 次；仍失败 → overall_passed=False、notes="self_check_failed"、
    cases_violated=全 applicable_cases、raw_scores={"missing": 全 rule_ids}
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ink_writer.writer_self_check.models import ComplianceReport

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "self_check.txt"

_DEFAULT_MAX_TOKENS = 2048
_DEFAULT_MODEL = "glm-4.6"


def _load_prompt_template() -> str:
    with open(PROMPT_PATH, encoding="utf-8") as fh:
        return fh.read()


def _format_rules(rules: list[dict[str, Any]]) -> str:
    if not rules:
        return "（无）"
    lines = []
    for rule in rules:
        rule_id = rule.get("rule_id", "<unknown>")
        text = rule.get("text", "")
        lines.append(f"- {rule_id}: {text}")
    return "\n".join(lines)


def _format_cases(cases: list[dict[str, Any]]) -> str:
    if not cases:
        return "（无）"
    lines = []
    for case in cases:
        case_id = case.get("case_id", "<unknown>")
        fd = case.get("failure_description", "")
        obs = case.get("observable", "")
        lines.append(f"- {case_id}\n  failure: {fd}\n  observable: {obs}")
    return "\n".join(lines)


def _build_prompt(
    chapter_text: str,
    injected_rules: list[dict[str, Any]],
    applicable_cases: list[dict[str, Any]],
) -> str:
    template = _load_prompt_template()
    return template.format(
        chapter_text=chapter_text,
        injected_rules=_format_rules(injected_rules),
        applicable_cases=_format_cases(applicable_cases),
    )


def _extract_json(raw: str) -> dict[str, Any]:
    """从 LLM 原始输出中抽取 JSON 对象；容忍 markdown 围栏与前后空白。"""
    if not isinstance(raw, str):
        raise ValueError("llm response is not a string")
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise ValueError("no JSON object found in llm response")
        text = m.group(0)
    return json.loads(text)


def _coerce_score(value: Any) -> float:
    """clamp [0, 1]；非数字返回 0.0。"""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score


def _failed_report(
    *,
    applicable_cases: list[dict[str, Any]],
    injected_rules: list[dict[str, Any]],
    notes: str,
) -> ComplianceReport:
    return ComplianceReport(
        rule_compliance=0.0,
        chunk_borrowing=None,
        cases_addressed=[],
        cases_violated=[c.get("case_id", "") for c in applicable_cases],
        raw_scores={"missing": [r.get("rule_id", "") for r in injected_rules]},
        overall_passed=False,
        notes=notes,
    )


def _call_llm(llm_client: Any, prompt: str, model: str) -> str:
    response = llm_client.messages.create(
        model=model,
        max_tokens=_DEFAULT_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def writer_self_check(
    *,
    chapter_text: str,
    injected_rules: list[dict[str, Any]],
    injected_chunks: list[dict[str, Any]] | None,  # noqa: ARG001  M3 期占位
    applicable_cases: list[dict[str, Any]],
    book: str,  # noqa: ARG001  仅用于上下文/日志，本函数当前未直接使用
    chapter: str,  # noqa: ARG001  仅用于上下文/日志，本函数当前未直接使用
    llm_client: Any,
    max_retries: int = 3,
    model: str = _DEFAULT_MODEL,
) -> ComplianceReport:
    """spec §3 实现 — 见模块 docstring。"""
    prompt = _build_prompt(chapter_text, injected_rules, applicable_cases)

    last_error: str | None = None
    parsed: dict[str, Any] | None = None
    attempts = max(1, max_retries)
    for _ in range(attempts):
        try:
            raw = _call_llm(llm_client, prompt, model)
            parsed = _extract_json(raw)
            break
        except Exception as exc:  # noqa: BLE001  LLM/JSON 失败统一降级
            last_error = str(exc)
            parsed = None
            continue

    if parsed is None:
        return _failed_report(
            applicable_cases=applicable_cases,
            injected_rules=injected_rules,
            notes="self_check_failed",
        )

    rule_scores_raw = parsed.get("rule_scores") or {}
    if not isinstance(rule_scores_raw, dict):
        rule_scores_raw = {}

    rule_ids = [r.get("rule_id", "") for r in injected_rules if r.get("rule_id")]
    if not rule_ids:
        rule_compliance = 1.0
        normalized_scores: dict[str, float] = {}
    else:
        normalized_scores = {}
        for rule_id in rule_ids:
            if rule_id in rule_scores_raw:
                normalized_scores[rule_id] = _coerce_score(
                    rule_scores_raw[rule_id]
                )
            else:
                normalized_scores[rule_id] = 0.0
        rule_compliance = sum(normalized_scores.values()) / len(rule_ids)

    case_eval_raw = parsed.get("case_evaluation") or []
    if not isinstance(case_eval_raw, list):
        case_eval_raw = []
    by_case: dict[str, dict[str, Any]] = {}
    for entry in case_eval_raw:
        if not isinstance(entry, dict):
            continue
        case_id = entry.get("case_id")
        if isinstance(case_id, str):
            by_case[case_id] = entry

    cases_addressed: list[str] = []
    cases_violated: list[str] = []
    for case in applicable_cases:
        case_id = case.get("case_id", "")
        if not case_id:
            continue
        entry = by_case.get(case_id)
        if entry is not None and bool(entry.get("addressed")):
            cases_addressed.append(case_id)
        else:
            cases_violated.append(case_id)

    notes_value = parsed.get("notes", "")
    notes = notes_value if isinstance(notes_value, str) else ""

    overall_passed = rule_compliance >= 0.70 and not cases_violated

    raw_scores: dict[str, Any] = {
        "rule_scores": normalized_scores,
        "case_evaluation": [dict(e) for e in case_eval_raw if isinstance(e, dict)],
    }
    if last_error is not None:
        raw_scores["last_error"] = last_error

    return ComplianceReport(
        rule_compliance=rule_compliance,
        chunk_borrowing=None,
        cases_addressed=cases_addressed,
        cases_violated=cases_violated,
        raw_scores=raw_scores,
        overall_passed=overall_passed,
        notes=notes,
    )
