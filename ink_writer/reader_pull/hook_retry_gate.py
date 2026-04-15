"""Hard gate for ink-write: reader-pull hook check + polish retry loop."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from ink_writer.reader_pull.config import ReaderPullConfig, load_config
from ink_writer.reader_pull.fix_prompt_builder import normalize_checker_output


@dataclass
class HookGateAttempt:
    attempt: int
    score: float
    violations: list[dict]
    fix_prompt: str
    passed: bool


@dataclass
class HookGateResult:
    chapter_no: int
    passed: bool
    final_score: float
    threshold: float
    attempts: list[HookGateAttempt] = field(default_factory=list)
    blocked_path: str | None = None
    final_text: str | None = None


def _setup_logger(chapter_no: int, project_root: str) -> logging.Logger:
    log_dir = os.path.join(project_root, "logs", "reader-pull")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"chapter_{chapter_no}.log")

    logger = logging.getLogger(f"reader-pull-gate-ch{chapter_no}")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    return logger


def _write_hook_blocked(
    chapter_no: int,
    violations: list[dict],
    threshold: float,
    score: float,
    fix_prompt: str,
    project_root: str,
) -> str:
    chapter_dir = os.path.join(project_root, "chapters", str(chapter_no))
    os.makedirs(chapter_dir, exist_ok=True)
    blocked_path = os.path.join(chapter_dir, "hook_blocked.md")

    lines = [
        f"# 第{chapter_no}章 — 追读力门禁阻断",
        "",
        f"**最终得分**: {score}（阈值: {threshold}）",
        "**重试次数**: 2（已达上限）",
        "",
        "## 未解决违规",
        "",
    ]
    for v in violations:
        vid = v.get("id", v.get("rule_id", "?"))
        severity = v.get("severity", "?")
        desc = v.get("description", v.get("suggestion", ""))
        lines.append(f"- **[{vid}]** ({severity}): {desc}")
        fix = v.get("fix_suggestion", v.get("suggestion", ""))
        if fix and fix != desc:
            lines.append(f"  - 建议：{fix}")

    lines.extend(["", "## 修复提示", "", fix_prompt, ""])

    with open(blocked_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return blocked_path


def run_hook_gate(
    chapter_text: str,
    chapter_no: int,
    project_root: str,
    *,
    checker_fn: Callable[[str, int], dict],
    polish_fn: Callable[[str, str, int], str],
    config: ReaderPullConfig | None = None,
) -> HookGateResult:
    """Run reader-pull hook gate with polish retry loop.

    Args:
        chapter_text: Current chapter text.
        chapter_no: Chapter number.
        project_root: Project root directory.
        checker_fn: Callable(chapter_text, chapter_no) -> raw checker result dict.
        polish_fn: Callable(chapter_text, fix_prompt, chapter_no) -> polished text.
        config: Reader-pull config. If None, loads from default path.

    Returns:
        HookGateResult with pass/fail status and attempt history.
    """
    if config is None:
        config = load_config()

    if not config.enabled:
        return HookGateResult(
            chapter_no=chapter_no,
            passed=True,
            final_score=100.0,
            threshold=0.0,
            final_text=chapter_text,
        )

    threshold = config.score_threshold
    if chapter_no <= 3:
        threshold = config.golden_three_threshold

    max_retries = config.max_retries
    logger = _setup_logger(chapter_no, project_root)
    logger.info(
        "开始追读力门禁检查 chapter=%d threshold=%.1f max_retries=%d",
        chapter_no, threshold, max_retries,
    )

    current_text = chapter_text
    attempts: list[HookGateAttempt] = []
    violations: list[dict] = []
    fix_prompt = ""
    score: float = 0.0

    for attempt_num in range(1, max_retries + 1):
        logger.info("第 %d 次检查", attempt_num)

        raw_result = checker_fn(current_text, chapter_no)
        normalized = normalize_checker_output(raw_result)

        score = normalized["score"]
        violations = normalized["violations"]
        fix_prompt = normalized["fix_prompt"]
        passed = score >= threshold

        attempt = HookGateAttempt(
            attempt=attempt_num,
            score=score,
            violations=violations,
            fix_prompt=fix_prompt,
            passed=passed,
        )
        attempts.append(attempt)

        logger.info(
            "检查结果: score=%.1f violations=%d passed=%s",
            score, len(violations), passed,
        )

        if passed:
            logger.info("追读力门禁通过")
            return HookGateResult(
                chapter_no=chapter_no,
                passed=True,
                final_score=score,
                threshold=threshold,
                attempts=attempts,
                final_text=current_text,
            )

        if attempt_num < max_retries:
            logger.info("得分低于阈值，执行润色修复 (attempt %d)", attempt_num)
            current_text = polish_fn(current_text, fix_prompt, chapter_no)
            logger.info("润色完成，准备重新检查")

    logger.warning("追读力门禁 %d 次重试均未通过，章节被阻断", max_retries)
    blocked_path = _write_hook_blocked(
        chapter_no, violations, threshold, score, fix_prompt, project_root,
    )
    logger.info("阻断报告已写入: %s", blocked_path)

    return HookGateResult(
        chapter_no=chapter_no,
        passed=False,
        final_score=score,
        threshold=threshold,
        attempts=attempts,
        blocked_path=blocked_path,
        final_text=None,
    )
