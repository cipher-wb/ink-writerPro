"""check_golden_finger_spec() — M4 ink-init 策划期金手指规格 checker（spec §3.2）。

输出 GoldenFingerSpecReport：
  - score = mean(4 dim) — clarity / falsifiability / boundary / growth_curve
  - blocked = score < block_threshold（默认 0.65）
  - description 缺失或 < 20 字 → blocked=True、notes='description_too_short'，不调 LLM
  - LLM/JSON 解析失败重试 max_retries 次后仍失败 → score=0.0、blocked=True、
    notes 形如 "checker_failed: <err>"。
  - cases_hit 默认空列表（由 planning_review 在阻断时按 config case_ids 注入）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ink_writer.checkers.golden_finger_spec.models import GoldenFingerSpecReport
from ink_writer.core.infra.json_util import parse_llm_json_object

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "check.txt"

_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_MODEL = "glm-4.6"
_DEFAULT_BLOCK_THRESHOLD = 0.65
_MIN_DESCRIPTION_LEN = 20

_DIMENSIONS: tuple[str, ...] = ("clarity", "falsifiability", "boundary", "growth_curve")


def _load_prompt_template() -> str:
    with open(PROMPT_PATH, encoding="utf-8") as fh:
        return fh.read()


def _build_prompt(*, description: str) -> str:
    return _load_prompt_template().format(description=description)


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


def check_golden_finger_spec(
    *,
    description: str,
    llm_client: Any,
    block_threshold: float = _DEFAULT_BLOCK_THRESHOLD,
    model: str = _DEFAULT_MODEL,
    max_retries: int = 2,
) -> GoldenFingerSpecReport:
    """spec §3.2 实现 — 见模块 docstring。"""
    if not isinstance(description, str) or len(description.strip()) < _MIN_DESCRIPTION_LEN:
        return GoldenFingerSpecReport(
            score=0.0,
            blocked=True,
            dim_scores={dim: 0.0 for dim in _DIMENSIONS},
            cases_hit=[],
            notes="description_too_short",
        )

    prompt = _build_prompt(description=description)

    _RETRY_SUFFIX = (
        "\n\nYour previous output was not valid JSON. "
        "Output ONLY the raw JSON object — no markdown fences, "
        "no explanation, no additional text. Start with `{` and end with `}`."
    )

    last_err: str = ""
    parsed: dict[str, Any] | None = None
    attempts = max(1, max_retries)
    for attempt in range(attempts):
        try:
            current_prompt = prompt if attempt == 0 else prompt + _RETRY_SUFFIX
            raw = _call_llm(llm_client, current_prompt, model)
            parsed = parse_llm_json_object(raw)
            break
        except Exception as exc:  # noqa: BLE001  LLM/JSON 失败统一降级
            last_err = str(exc) or exc.__class__.__name__
            parsed = None
            continue

    if parsed is None:
        return GoldenFingerSpecReport(
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

    return GoldenFingerSpecReport(
        score=score,
        blocked=blocked,
        dim_scores=dim_scores,
        cases_hit=[],
        notes=notes,
    )
