"""check_protagonist_agency() — M3 章节级主角能动性检查（spec §4.2 + Q8）。

输出 AgencyReport：
  - score = 0.5 * has_active_decision + 0.3 * has_plot_drive + 0.2 * min(count / 2, 1)
  - blocked = score < block_threshold（默认 0.60）
  - 短章节（< 500 字）直接跳过：score=0.0、blocked=False、notes="skipped_short_chapter"
  - LLM/JSON 解析失败重试 max_retries 次后仍失败 → score=0.0、blocked=True、
    notes="checker_failed"
  - cases_hit 默认空列表（由 rewrite_loop 在阻断时按 tag 注入）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ink_writer.checkers.protagonist_agency.models import AgencyReport
from ink_writer.core.infra.json_util import parse_llm_json_object

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "check.txt"

_DEFAULT_MAX_TOKENS = 2048
_DEFAULT_MODEL = "glm-4.6"
_SHORT_CHAPTER_CHARS = 500
_DEFAULT_BLOCK_THRESHOLD = 0.60


def _load_prompt_template() -> str:
    with open(PROMPT_PATH, encoding="utf-8") as fh:
        return fh.read()


def _build_prompt(*, chapter_text: str, protagonist_name: str) -> str:
    return _load_prompt_template().format(
        chapter_text=chapter_text,
        protagonist_name=protagonist_name,
    )


def _call_llm(llm_client: Any, prompt: str, model: str) -> str:
    response = llm_client.messages.create(
        model=model,
        max_tokens=_DEFAULT_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _compute_score(*, has_active: bool, has_plot_drive: bool, count: int) -> float:
    count_term = min(max(count, 0) / 2.0, 1.0)
    return 0.5 * float(has_active) + 0.3 * float(has_plot_drive) + 0.2 * count_term


def check_protagonist_agency(
    *,
    chapter_text: str,
    protagonist_name: str,
    book: str,  # noqa: ARG001  仅用于上下文/日志
    chapter: str,  # noqa: ARG001  仅用于上下文/日志
    llm_client: Any,
    max_retries: int = 3,
    block_threshold: float = _DEFAULT_BLOCK_THRESHOLD,
    model: str = _DEFAULT_MODEL,
) -> AgencyReport:
    """spec §4.2 实现 — 见模块 docstring。"""
    if len(chapter_text) < _SHORT_CHAPTER_CHARS:
        return AgencyReport(
            has_active_decision=False,
            has_plot_drive=False,
            decision_count=0,
            decision_summaries=[],
            score=0.0,
            block_threshold=block_threshold,
            blocked=False,
            cases_hit=[],
            notes="skipped_short_chapter",
        )

    prompt = _build_prompt(
        chapter_text=chapter_text,
        protagonist_name=protagonist_name,
    )

    _RETRY_SUFFIX = (
        "\n\nYour previous output was not valid JSON. "
        "Output ONLY the raw JSON object — no markdown fences, "
        "no explanation, no additional text. Start with `{` and end with `}`."
    )

    parsed: dict[str, Any] | None = None
    attempts = max(1, max_retries)
    for attempt in range(attempts):
        try:
            current_prompt = prompt if attempt == 0 else prompt + _RETRY_SUFFIX
            raw = _call_llm(llm_client, current_prompt, model)
            parsed = parse_llm_json_object(raw)
            break
        except Exception:  # noqa: BLE001  LLM/JSON 失败统一降级
            parsed = None
            continue

    if parsed is None:
        return AgencyReport(
            has_active_decision=False,
            has_plot_drive=False,
            decision_count=0,
            decision_summaries=[],
            score=0.0,
            block_threshold=block_threshold,
            blocked=True,
            cases_hit=[],
            notes="checker_failed",
        )

    has_active = bool(parsed.get("has_active_decision", False))
    has_plot_drive = bool(parsed.get("has_plot_drive", False))
    try:
        decision_count = int(parsed.get("decision_count", 0))
    except (TypeError, ValueError):
        decision_count = 0
    if decision_count < 0:
        decision_count = 0

    summaries: list[str] = []
    decisions_raw = parsed.get("decisions") or []
    if isinstance(decisions_raw, list):
        for entry in decisions_raw:
            if not isinstance(entry, dict):
                continue
            decision_text = str(entry.get("decision", "")).strip()
            consequence = str(entry.get("consequence", "")).strip()
            parts = [p for p in (decision_text, consequence) if p]
            summary = " → ".join(parts) if parts else ""
            if summary:
                summaries.append(summary)

    score = _compute_score(
        has_active=has_active,
        has_plot_drive=has_plot_drive,
        count=decision_count,
    )
    blocked = score < block_threshold

    notes_value = parsed.get("notes", "")
    notes = notes_value if isinstance(notes_value, str) else ""

    return AgencyReport(
        has_active_decision=has_active,
        has_plot_drive=has_plot_drive,
        decision_count=decision_count,
        decision_summaries=summaries,
        score=score,
        block_threshold=block_threshold,
        blocked=blocked,
        cases_hit=[],
        notes=notes,
    )
