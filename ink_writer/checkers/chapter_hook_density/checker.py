"""check_chapter_hook_density() — M4 ink-plan 策划期卷骨架钩子密度 checker（spec §3.7）。

输出 ChapterHookDensityReport：
  - per_chapter: LLM 给每章 summary 打的 hook_strength（0-1）
  - strong: hook_strength >= 0.5
  - score = strong_count / total_count
  - blocked = score < block_threshold（默认 0.70）
  - empty skeleton → score=0.0、blocked=True、notes="empty_skeleton"
    （上游卷骨架缺失时保守阻断，不调 LLM）
  - LLM/JSON 解析失败重试 max_retries 次后仍失败 → score=0.0、blocked=True、
    notes 形如 "checker_failed: <err>"。
  - cases_hit 默认空列表（由 planning_review 在阻断时按 config case_ids 注入）。

注意：与 protagonist_agency_skeleton 同形态（per_chapter LLM 打分），但聚合方式
不同：本 checker 把每章二值化（strong / weak）后取占比，而非算术平均。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ink_writer.checkers.chapter_hook_density.models import ChapterHookDensityReport

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "check.txt"

_DEFAULT_MAX_TOKENS = 2048
_DEFAULT_MODEL = "glm-4.6"
_DEFAULT_BLOCK_THRESHOLD = 0.70
_STRONG_THRESHOLD = 0.5


def _load_prompt_template() -> str:
    with open(PROMPT_PATH, encoding="utf-8") as fh:
        return fh.read()


def _build_prompt(*, outline_volume_skeleton: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for entry in outline_volume_skeleton:
        if not isinstance(entry, dict):
            continue
        try:
            idx = int(entry.get("chapter_idx"))
        except (TypeError, ValueError):
            continue
        summary = str(entry.get("summary", "")).strip()
        lines.append(f"第 {idx} 章 — {summary}")
    return _load_prompt_template().format(summaries_text="\n".join(lines))


def _extract_json_array(raw: str) -> list[dict[str, Any]]:
    if not isinstance(raw, str):
        raise ValueError("llm response is not a string")
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    if not text.startswith("["):
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            raise ValueError("no JSON array found in llm response")
        text = m.group(0)
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("llm response is not a JSON array")
    return parsed


def _call_llm(llm_client: Any, prompt: str, model: str) -> str:
    response = llm_client.messages.create(
        model=model,
        max_tokens=_DEFAULT_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _normalize_per_chapter(parsed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        try:
            idx = int(entry.get("chapter_idx"))
        except (TypeError, ValueError):
            continue
        try:
            strength = float(entry.get("hook_strength", 0.0))
        except (TypeError, ValueError):
            strength = 0.0
        strength = max(0.0, min(1.0, strength))
        reason_value = entry.get("reason", "")
        reason = reason_value if isinstance(reason_value, str) else ""
        out.append(
            {
                "chapter_idx": idx,
                "hook_strength": strength,
                "strong": strength >= _STRONG_THRESHOLD,
                "reason": reason,
            }
        )
    return out


def check_chapter_hook_density(
    *,
    outline_volume_skeleton: list[dict[str, Any]],
    llm_client: Any,
    block_threshold: float = _DEFAULT_BLOCK_THRESHOLD,
    model: str = _DEFAULT_MODEL,
    max_retries: int = 2,
) -> ChapterHookDensityReport:
    """spec §3.7 实现 — 见模块 docstring。"""
    if not outline_volume_skeleton:
        return ChapterHookDensityReport(
            score=0.0,
            blocked=True,
            per_chapter=[],
            strong_count=0,
            total_count=0,
            cases_hit=[],
            notes="empty_skeleton",
        )

    prompt = _build_prompt(outline_volume_skeleton=outline_volume_skeleton)

    last_err: str = ""
    parsed: list[dict[str, Any]] | None = None
    attempts = max(1, max_retries)
    for _ in range(attempts):
        try:
            raw = _call_llm(llm_client, prompt, model)
            parsed = _extract_json_array(raw)
            break
        except Exception as exc:  # noqa: BLE001  LLM/JSON 失败统一降级
            last_err = str(exc) or exc.__class__.__name__
            parsed = None
            continue

    if parsed is None:
        return ChapterHookDensityReport(
            score=0.0,
            blocked=True,
            per_chapter=[],
            strong_count=0,
            total_count=0,
            cases_hit=[],
            notes=f"checker_failed: {last_err}",
        )

    per_chapter = _normalize_per_chapter(parsed)
    if not per_chapter:
        return ChapterHookDensityReport(
            score=0.0,
            blocked=True,
            per_chapter=[],
            strong_count=0,
            total_count=0,
            cases_hit=[],
            notes="checker_failed: no valid per_chapter entries",
        )

    total_count = len(per_chapter)
    strong_count = sum(1 for item in per_chapter if item["strong"])
    score = strong_count / total_count
    blocked = score < block_threshold

    return ChapterHookDensityReport(
        score=score,
        blocked=blocked,
        per_chapter=per_chapter,
        strong_count=strong_count,
        total_count=total_count,
        cases_hit=[],
        notes="",
    )
