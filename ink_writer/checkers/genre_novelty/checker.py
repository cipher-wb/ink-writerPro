"""check_genre_novelty() — M4 ink-init 策划期题材新颖度 checker（spec §3.1）。

输出 GenreNoveltyReport：
  - score = 1.0 - max(top5 similarity)
  - blocked = score < block_threshold（默认 0.40）
  - empty top200 → score=1.0、blocked=False、notes="empty_top200_skipped"
    （上游数据缺失时直接放行，不调 LLM）
  - LLM/JSON 解析失败重试 max_retries 次后仍失败 → score=0.0、blocked=True、
    notes 形如 "checker_failed: <err>"。
  - cases_hit 默认空列表（由 planning_review 在阻断时按 config case_ids 注入）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ink_writer.checkers.genre_novelty.models import GenreNoveltyReport

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "check.txt"

_DEFAULT_MAX_TOKENS = 2048
_DEFAULT_MODEL = "glm-4.6"
_DEFAULT_BLOCK_THRESHOLD = 0.40


def _load_prompt_template() -> str:
    with open(PROMPT_PATH, encoding="utf-8") as fh:
        return fh.read()


def _build_prompt(
    *,
    genre_tags: list[str],
    main_plot_one_liner: str,
    top200: list[dict[str, Any]],
) -> str:
    top200_lines = [
        json.dumps(
            {
                "rank": item.get("rank"),
                "title": item.get("title", ""),
                "genre_tags": item.get("genre_tags", []),
                "intro_one_liner": item.get("intro_one_liner", ""),
            },
            ensure_ascii=False,
        )
        for item in top200
    ]
    return _load_prompt_template().format(
        genre_tags=json.dumps(list(genre_tags), ensure_ascii=False),
        main_plot_one_liner=main_plot_one_liner,
        top200_json="\n".join(top200_lines),
    )


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


def _enrich_top5(
    *,
    parsed: list[dict[str, Any]],
    top200: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_rank = {item.get("rank"): item for item in top200 if isinstance(item, dict)}
    enriched: list[dict[str, Any]] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        try:
            rank = int(entry.get("rank"))
        except (TypeError, ValueError):
            continue
        try:
            sim = float(entry.get("similarity", 0.0))
        except (TypeError, ValueError):
            sim = 0.0
        sim = max(0.0, min(1.0, sim))
        reason_value = entry.get("reason", "")
        reason = reason_value if isinstance(reason_value, str) else ""
        title = ""
        ref = by_rank.get(rank)
        if isinstance(ref, dict):
            title_value = ref.get("title", "")
            if isinstance(title_value, str):
                title = title_value
        enriched.append(
            {
                "rank": rank,
                "title": title,
                "similarity": sim,
                "reason": reason,
            }
        )
    enriched.sort(key=lambda x: x["similarity"], reverse=True)
    return enriched[:5]


def check_genre_novelty(
    *,
    genre_tags: list[str],
    main_plot_one_liner: str,
    top200: list[dict[str, Any]],
    llm_client: Any,
    block_threshold: float = _DEFAULT_BLOCK_THRESHOLD,
    model: str = _DEFAULT_MODEL,
    max_retries: int = 2,
) -> GenreNoveltyReport:
    """spec §3.1 实现 — 见模块 docstring。"""
    if not top200:
        return GenreNoveltyReport(
            score=1.0,
            blocked=False,
            top5_similar=[],
            cases_hit=[],
            notes="empty_top200_skipped",
        )

    prompt = _build_prompt(
        genre_tags=genre_tags,
        main_plot_one_liner=main_plot_one_liner,
        top200=top200,
    )

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
        return GenreNoveltyReport(
            score=0.0,
            blocked=True,
            top5_similar=[],
            cases_hit=[],
            notes=f"checker_failed: {last_err}",
        )

    top5 = _enrich_top5(parsed=parsed, top200=top200)
    max_sim = max((item["similarity"] for item in top5), default=0.0)
    score = max(0.0, 1.0 - max_sim)
    blocked = score < block_threshold

    return GenreNoveltyReport(
        score=score,
        blocked=blocked,
        top5_similar=top5,
        cases_hit=[],
        notes="",
    )
