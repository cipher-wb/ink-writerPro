"""Hard gate for ink-review: editor-wisdom checker + polish retry loop."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from ink_writer.editor_wisdom.config import EditorWisdomConfig, load_config


@dataclass
class GateAttempt:
    attempt: int
    score: float
    violations: list[dict]
    passed: bool


@dataclass
class GateResult:
    chapter_no: int
    passed: bool
    final_score: float
    threshold: float
    attempts: list[GateAttempt] = field(default_factory=list)
    blocked_path: str | None = None
    final_text: str | None = None


def _setup_logger(chapter_no: int, project_root: str) -> logging.Logger:
    log_dir = os.path.join(project_root, "logs", "editor-wisdom")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"chapter_{chapter_no}.log")

    logger = logging.getLogger(f"editor-wisdom-gate-ch{chapter_no}")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    return logger


def _write_blocked(
    chapter_no: int,
    violations: list[dict],
    threshold: float,
    score: float,
    project_root: str,
) -> str:
    chapter_dir = os.path.join(project_root, "chapters", str(chapter_no))
    os.makedirs(chapter_dir, exist_ok=True)
    blocked_path = os.path.join(chapter_dir, "blocked.md")

    lines = [
        f"# 第{chapter_no}章 — 编辑智慧门禁阻断",
        "",
        f"**最终得分**: {score}（阈值: {threshold}）",
        "**重试次数**: 3（已达上限）",
        "",
        "## 未解决违规",
        "",
    ]
    for v in violations:
        lines.append(f"- **[{v.get('rule_id', '?')}]** ({v.get('severity', '?')})")
        lines.append(f"  - 引用：「{v.get('quote', '')}」")
        lines.append(f"  - 建议：{v.get('fix_suggestion', '')}")
    lines.append("")

    with open(blocked_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return blocked_path


def run_review_gate(
    chapter_text: str,
    chapter_no: int,
    project_root: str,
    *,
    checker_fn: Callable[[str, int], dict],
    polish_fn: Callable[[str, list[dict], int], str],
    config: EditorWisdomConfig | None = None,
    max_retries: int = 3,
) -> GateResult:
    """Run editor-wisdom hard gate with polish retry loop.

    Args:
        chapter_text: Current chapter text.
        chapter_no: Chapter number.
        project_root: Project root directory.
        checker_fn: Callable(chapter_text, chapter_no) -> checker result dict.
        polish_fn: Callable(chapter_text, violations, chapter_no) -> polished text.
        config: Editor wisdom config. If None, loads from default path.
        max_retries: Maximum polish+re-check attempts.

    Returns:
        GateResult with pass/fail status and attempt history.
    """
    if config is None:
        config = load_config()

    threshold = config.hard_gate_threshold
    if chapter_no <= 3:
        threshold = config.golden_three_threshold

    logger = _setup_logger(chapter_no, project_root)
    logger.info("开始编辑智慧门禁检查 chapter=%d threshold=%.2f", chapter_no, threshold)

    current_text = chapter_text
    attempts: list[GateAttempt] = []
    violations: list[dict] = []
    score: float = 1.0

    for attempt_num in range(1, max_retries + 1):
        logger.info("第 %d 次检查", attempt_num)

        result = checker_fn(current_text, chapter_no)
        score = result.get("score", 0.0)
        violations = result.get("violations", [])
        passed = score >= threshold

        attempt = GateAttempt(
            attempt=attempt_num,
            score=score,
            violations=violations,
            passed=passed,
        )
        attempts.append(attempt)

        logger.info(
            "检查结果: score=%.2f violations=%d passed=%s",
            score, len(violations), passed,
        )

        if passed:
            logger.info("门禁通过")
            return GateResult(
                chapter_no=chapter_no,
                passed=True,
                final_score=score,
                threshold=threshold,
                attempts=attempts,
                final_text=current_text,
            )

        if attempt_num < max_retries:
            logger.info("得分低于阈值，开始润色修复 (attempt %d)", attempt_num)
            current_text = polish_fn(current_text, violations, chapter_no)
            logger.info("润色完成，准备重新检查")

    logger.warning("3次重试均未通过门禁，章节被阻断")
    blocked_path = _write_blocked(
        chapter_no, violations, threshold, score, project_root
    )
    logger.info("阻断报告已写入: %s", blocked_path)

    return GateResult(
        chapter_no=chapter_no,
        passed=False,
        final_score=score,
        threshold=threshold,
        attempts=attempts,
        blocked_path=blocked_path,
        final_text=None,
    )
