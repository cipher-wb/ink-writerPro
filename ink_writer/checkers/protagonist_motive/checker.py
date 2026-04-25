"""check_protagonist_motive() — M4 ink-init 策划期主角动机 checker（spec §3.4）。

输出 ProtagonistMotiveReport：
  - score = mean(3 dim) — resonance / specific_goal / inner_conflict
  - blocked = score < block_threshold（默认 0.65）
  - description 缺失或 strip 后 < 20 字 → blocked=True、notes='description_too_short'，
    不调 LLM。
  - LLM/JSON 解析失败重试 max_retries 次后仍失败 → score=0.0、blocked=True、
    notes 形如 "checker_failed: <err>"。
  - cases_hit 默认空列表（由 planning_review 在阻断时按 config case_ids 注入）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ink_writer.checkers.protagonist_motive.models import ProtagonistMotiveReport

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "check.txt"

_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_MODEL = "glm-4.6"
_DEFAULT_BLOCK_THRESHOLD = 0.65
_MIN_DESCRIPTION_LEN = 20

_DIMENSIONS: tuple[str, ...] = ("resonance", "specific_goal", "inner_conflict")


def _load_prompt_template() -> str:
    with open(PROMPT_PATH, encoding="utf-8") as fh:
        return fh.read()


def _build_prompt(*, description: str) -> str:
    return _load_prompt_template().format(description=description)


def _extract_json_object(raw: str) -> dict[str, Any]:
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
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("llm response is not a JSON object")
    return parsed


def _call_llm(llm_client: Any, prompt: str, model: str) -> str:
    response = llm_client.messages.create(
        model=model,
        max_tokens=_DEFAULT_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _normalize_dim_scores(parsed: dict[str, Any]) -> dict[str, float]:
    dim_scores: dict[str, float] = {}
    for dim in _DIMENSIONS:
        try:
            value = float(parsed.get(dim, 0.0))
        except (TypeError, ValueError):
            value = 0.0
        dim_scores[dim] = max(0.0, min(1.0, value))
    return dim_scores


def check_protagonist_motive(
    *,
    description: str,
    llm_client: Any,
    block_threshold: float = _DEFAULT_BLOCK_THRESHOLD,
    model: str = _DEFAULT_MODEL,
    max_retries: int = 2,
) -> ProtagonistMotiveReport:
    """spec §3.4 实现 — 见模块 docstring。"""
    if not isinstance(description, str) or len(description.strip()) < _MIN_DESCRIPTION_LEN:
        return ProtagonistMotiveReport(
            score=0.0,
            blocked=True,
            dim_scores={dim: 0.0 for dim in _DIMENSIONS},
            cases_hit=[],
            notes="description_too_short",
        )

    prompt = _build_prompt(description=description)

    last_err: str = ""
    parsed: dict[str, Any] | None = None
    attempts = max(1, max_retries)
    for _ in range(attempts):
        try:
            raw = _call_llm(llm_client, prompt, model)
            parsed = _extract_json_object(raw)
            break
        except Exception as exc:  # noqa: BLE001  LLM/JSON 失败统一降级
            last_err = str(exc) or exc.__class__.__name__
            parsed = None
            continue

    if parsed is None:
        return ProtagonistMotiveReport(
            score=0.0,
            blocked=True,
            dim_scores={dim: 0.0 for dim in _DIMENSIONS},
            cases_hit=[],
            notes=f"checker_failed: {last_err}",
        )

    dim_scores = _normalize_dim_scores(parsed)
    score = sum(dim_scores.values()) / len(_DIMENSIONS)
    blocked = score < block_threshold

    notes_value = parsed.get("notes", "")
    notes = notes_value if isinstance(notes_value, str) else ""

    return ProtagonistMotiveReport(
        score=score,
        blocked=blocked,
        dim_scores=dim_scores,
        cases_hit=[],
        notes=notes,
    )
