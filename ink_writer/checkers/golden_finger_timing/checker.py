"""check_golden_finger_timing() — M4 ink-plan 策划期金手指出场时机 checker（spec §3.5）。

regex 主 + LLM 回退：
  - 不足 3 章 → blocked=True、notes='outline_too_short: <n> < 3'；
  - 空 keywords → blocked=True、notes='empty_keywords'；
  - regex 命中（前 3 章 summary）→ score=1.0、blocked=False、regex_match=True、
    llm_match=None、matched_chapter=<命中章 1~3>；不调 LLM；
  - regex miss → 调 LLM；matched=True → score=1.0、blocked=False、regex_match=False、
    llm_match=True、matched_chapter=<LLM 给的 1~3>；matched=False → score=0.0、
    blocked=True、regex_match=False、llm_match=False、matched_chapter=None；
  - LLM/JSON 解析失败重试 max_retries 次后仍失败 → score=0.0、blocked=True、
    notes 形如 "checker_failed: <err>"。

硬阻断（block_threshold=1.0）。cases_hit 默认空列表（由 planning_review 在阻断时按
config case_ids 注入）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ink_writer.checkers.golden_finger_timing.models import GoldenFingerTimingReport

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "check.txt"

_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_MODEL = "glm-4.6"
_DEFAULT_BLOCK_THRESHOLD = 1.0
_FIRST_N_CHAPTERS = 3


def _load_prompt_template() -> str:
    with open(PROMPT_PATH, encoding="utf-8") as fh:
        return fh.read()


def _first_n_chapters(
    outline_volume_skeleton: list[dict[str, Any]],
    n: int = _FIRST_N_CHAPTERS,
) -> list[dict[str, Any]]:
    return [item for item in outline_volume_skeleton[:n] if isinstance(item, dict)]


def _scan_regex(
    *,
    summaries: list[dict[str, Any]],
    keywords: list[str],
) -> int | None:
    """返回首个命中章节的 chapter_idx；未命中返回 None。"""
    cleaned = [str(kw) for kw in keywords if isinstance(kw, str) and kw.strip()]
    if not cleaned:
        return None
    pattern = re.compile("|".join(re.escape(kw) for kw in cleaned))
    for entry in summaries:
        summary = entry.get("summary", "")
        if not isinstance(summary, str):
            continue
        if pattern.search(summary):
            try:
                return int(entry.get("chapter_idx"))
            except (TypeError, ValueError):
                return None
    return None


def _build_prompt(*, keywords: list[str], summaries: list[dict[str, Any]]) -> str:
    keywords_json = json.dumps(list(keywords), ensure_ascii=False)
    lines: list[str] = []
    for entry in summaries:
        try:
            idx = int(entry.get("chapter_idx"))
        except (TypeError, ValueError):
            continue
        summary = entry.get("summary", "")
        if not isinstance(summary, str):
            summary = ""
        lines.append(f"第{idx}章：{summary}")
    summaries_text = "\n".join(lines)
    return _load_prompt_template().format(
        keywords=keywords_json,
        summaries_text=summaries_text,
    )


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


def check_golden_finger_timing(
    *,
    outline_volume_skeleton: list[dict[str, Any]],
    golden_finger_keywords: list[str],
    llm_client: Any,
    block_threshold: float = _DEFAULT_BLOCK_THRESHOLD,  # noqa: ARG001  保留 API 兼容
    model: str = _DEFAULT_MODEL,
    max_retries: int = 2,
) -> GoldenFingerTimingReport:
    """spec §3.5 实现 — 见模块 docstring。"""
    skeleton = list(outline_volume_skeleton or [])
    if len(skeleton) < _FIRST_N_CHAPTERS:
        return GoldenFingerTimingReport(
            score=0.0,
            blocked=True,
            regex_match=False,
            llm_match=None,
            matched_chapter=None,
            cases_hit=[],
            notes=f"outline_too_short: {len(skeleton)} < {_FIRST_N_CHAPTERS}",
        )

    cleaned_keywords = [
        str(kw) for kw in (golden_finger_keywords or []) if isinstance(kw, str) and kw.strip()
    ]
    if not cleaned_keywords:
        return GoldenFingerTimingReport(
            score=0.0,
            blocked=True,
            regex_match=False,
            llm_match=None,
            matched_chapter=None,
            cases_hit=[],
            notes="empty_keywords",
        )

    first3 = _first_n_chapters(skeleton)

    regex_chapter = _scan_regex(summaries=first3, keywords=cleaned_keywords)
    if regex_chapter is not None:
        return GoldenFingerTimingReport(
            score=1.0,
            blocked=False,
            regex_match=True,
            llm_match=None,
            matched_chapter=regex_chapter,
            cases_hit=[],
            notes="",
        )

    prompt = _build_prompt(keywords=cleaned_keywords, summaries=first3)

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
        return GoldenFingerTimingReport(
            score=0.0,
            blocked=True,
            regex_match=False,
            llm_match=None,
            matched_chapter=None,
            cases_hit=[],
            notes=f"checker_failed: {last_err}",
        )

    matched_raw = parsed.get("matched", False)
    llm_matched = bool(matched_raw) if isinstance(matched_raw, (bool, int)) else False

    matched_chapter: int | None = None
    if llm_matched:
        try:
            mc = int(parsed.get("matched_chapter"))
            if 1 <= mc <= _FIRST_N_CHAPTERS:
                matched_chapter = mc
        except (TypeError, ValueError):
            matched_chapter = None

    notes_value = parsed.get("reason", "")
    notes = notes_value if isinstance(notes_value, str) else ""

    if llm_matched and matched_chapter is not None:
        return GoldenFingerTimingReport(
            score=1.0,
            blocked=False,
            regex_match=False,
            llm_match=True,
            matched_chapter=matched_chapter,
            cases_hit=[],
            notes=notes,
        )

    return GoldenFingerTimingReport(
        score=0.0,
        blocked=True,
        regex_match=False,
        llm_match=False,
        matched_chapter=None,
        cases_hit=[],
        notes=notes,
    )
