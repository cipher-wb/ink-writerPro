"""US-LR-012: ink-review Step 3.6 接入点 — master switch + 阈值 + polish 触发。

与 Step 3.5（editor-wisdom 硬门禁）OR 并列：两 checker 都不通过才阻断；任一通过即放行。
OR 合并发生在调用方（SKILL.md 提供组合逻辑）；本模块仅返回自己一路的判定。
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ink_writer.live_review.checker import run_live_review_checker
from ink_writer.live_review.config import LiveReviewConfig, load_config


def _disabled_review_response() -> dict:
    return {
        "passed": True,
        "score": 1.0,
        "threshold": 0.0,
        "violations": [],
        "cases_hit": [],
        "dimensions": {},
        "polish_triggered": False,
        "disabled": True,
    }


def _resolve_threshold(chapter_no: int, config: LiveReviewConfig) -> float:
    """黄金三章用 golden_three_threshold，其余用 hard_gate_threshold。"""
    if chapter_no <= 3:
        return float(config.golden_three_threshold)
    return float(config.hard_gate_threshold)


def check_review(
    chapter_text: str,
    chapter_no: int,
    genre_tags: list[str],
    *,
    mock_response: dict | None = None,
    llm_call: Callable[[str], str] | None = None,
    polish_fn: Callable[[str, list[dict], int], str] | None = None,
    config_path: Path | None = None,
    index_dir: Path | None = None,
) -> dict:
    """Step 3.6 主流程。

    1. master switch：``enabled`` / ``inject_into.review`` 任一 false → 早退（视为通行）。
    2. 调 ``run_live_review_checker`` 取评分。
    3. 选阈值：``chapter_no <= 3`` → ``golden_three_threshold``；其他 → ``hard_gate_threshold``。
    4. 若 ``score < threshold`` 且 ``polish_fn`` 给定 → 触发 polish 一次（修复循环由调用方控制）。

    OR 合并：本函数返回的 ``passed`` 仅是单路判定，调用方可与 Step 3.5 的 GateResult 取 OR。

    Returns:
        dict：``passed`` / ``score`` / ``threshold`` / ``violations`` / ``cases_hit`` /
        ``dimensions`` / ``polish_triggered`` / ``disabled``。
    """
    cfg: LiveReviewConfig = load_config(config_path)
    if not cfg.enabled or not cfg.inject_into.review:
        return _disabled_review_response()

    threshold = _resolve_threshold(chapter_no, cfg)

    result = run_live_review_checker(
        chapter_text,
        chapter_no=chapter_no,
        genre_tags=genre_tags,
        mock_response=mock_response,
        llm_call=llm_call,
        config_path=config_path,
        index_dir=index_dir,
    )

    score = float(result["score"])
    violations = result["violations"]
    passed = score >= threshold

    polish_triggered = False
    if not passed and polish_fn is not None:
        polish_fn(chapter_text, violations, chapter_no)
        polish_triggered = True

    return {
        "passed": passed,
        "score": score,
        "threshold": threshold,
        "violations": violations,
        "cases_hit": result["cases_hit"],
        "dimensions": result["dimensions"],
        "polish_triggered": polish_triggered,
        "disabled": False,
    }


__all__ = ["check_review"]
