"""Hard gate for ink-review: editor-wisdom checker + polish retry loop.

US-015 updates:
- Dual-threshold logic for golden-three (chapters 1-3): `golden_three_hard_threshold`
  is the blocking bar; `golden_three_soft_threshold` is the target recorded as
  `soft_threshold` in the result (warning only, not blocking).
- Whole-chapter-rewrite escape hatch: when `allow_escape_hatch=True`, a chapter that
  fails 2 polish retries returns with `action="rewrite_step2a"` and
  `escape_hatch_triggered=True` instead of 3-attempt block. Backward compatible:
  default `allow_escape_hatch=False` preserves the original 3-attempt block behavior.
"""

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
    # US-015: dual-threshold + escape-hatch fields (optional, populated for golden-three paths).
    soft_threshold: float | None = None
    soft_passed: bool | None = None
    action: str = "continue"  # "continue" | "rewrite_step2a"
    escape_hatch_triggered: bool = False


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
    attempts: int = 3,
) -> str:
    chapter_dir = os.path.join(project_root, "chapters", str(chapter_no))
    os.makedirs(chapter_dir, exist_ok=True)
    blocked_path = os.path.join(chapter_dir, "blocked.md")

    lines = [
        f"# 第{chapter_no}章 — 编辑智慧门禁阻断",
        "",
        f"**最终得分**: {score}（阈值: {threshold}）",
        f"**重试次数**: {attempts}（已达上限）",
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


def _resolve_thresholds(
    chapter_no: int,
    config: EditorWisdomConfig,
) -> tuple[float, float | None]:
    """Resolve (hard_threshold, soft_threshold) for a chapter.

    US-015: for golden-three chapters (1-3), hard is the blocking bar;
    soft is the target reported as warning-only. Non-golden chapters use
    `hard_gate_threshold` with no soft component.

    Backward compat: if caller explicitly set legacy `golden_three_threshold`
    to a non-default value (!= 0.85) but left `golden_three_hard_threshold`
    at its default (0.75), treat the legacy value as the hard threshold.
    """
    if chapter_no > 3:
        return config.hard_gate_threshold, None

    hard = config.golden_three_hard_threshold
    soft = config.golden_three_soft_threshold

    # Legacy compat path: honor explicitly-set golden_three_threshold when new
    # hard field is still at its default. This keeps older call sites working
    # while letting new callers opt into the dual-threshold semantics.
    if (
        abs(config.golden_three_hard_threshold - 0.75) < 1e-9
        and abs(config.golden_three_threshold - 0.85) > 1e-9
    ):
        hard = config.golden_three_threshold

    return hard, soft


def run_review_gate(
    chapter_text: str,
    chapter_no: int,
    project_root: str,
    *,
    checker_fn: Callable[[str, int], dict],
    polish_fn: Callable[[str, list[dict], int], str],
    config: EditorWisdomConfig | None = None,
    max_retries: int = 3,
    allow_escape_hatch: bool = False,
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
        allow_escape_hatch: US-015. When True, after 2 failed retries (attempts 1 & 2
            both fail to reach the hard threshold) the gate stops polishing and
            returns a GateResult with `escape_hatch_triggered=True` and
            `action="rewrite_step2a"`, signalling the orchestrator to re-run Step 2A.
            Default False preserves legacy 3-attempt block behavior.

    Returns:
        GateResult with pass/fail status and attempt history.
    """
    if config is None:
        config = load_config()

    threshold, soft_threshold = _resolve_thresholds(chapter_no, config)

    logger = _setup_logger(chapter_no, project_root)
    logger.info(
        "开始编辑智慧门禁检查 chapter=%d hard_threshold=%.2f soft_threshold=%s allow_escape_hatch=%s",
        chapter_no,
        threshold,
        f"{soft_threshold:.2f}" if soft_threshold is not None else "n/a",
        allow_escape_hatch,
    )

    current_text = chapter_text
    attempts: list[GateAttempt] = []
    violations: list[dict] = []
    score: float = 1.0

    # US-015: when escape hatch enabled, cap attempts at 2 (initial + 1 retry).
    # If both fail the hard threshold, trigger escape hatch instead of blocking.
    effective_max = 2 if allow_escape_hatch else max_retries

    for attempt_num in range(1, effective_max + 1):
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
            soft_passed = (
                score >= soft_threshold if soft_threshold is not None else None
            )
            if soft_threshold is not None and not soft_passed:
                logger.info(
                    "门禁通过（硬阈值），但低于软阈值 %.2f，记录告警", soft_threshold
                )
            else:
                logger.info("门禁通过")
            return GateResult(
                chapter_no=chapter_no,
                passed=True,
                final_score=score,
                threshold=threshold,
                attempts=attempts,
                final_text=current_text,
                soft_threshold=soft_threshold,
                soft_passed=soft_passed,
                action="continue",
            )

        if attempt_num < effective_max:
            logger.info("得分低于阈值，开始润色修复 (attempt %d)", attempt_num)
            current_text = polish_fn(current_text, violations, chapter_no)
            logger.info("润色完成，准备重新检查")

    # All attempts exhausted without passing the hard threshold.
    if allow_escape_hatch:
        logger.warning(
            "2 次重试均未通过硬阈值，触发整章重写逃生门（action=rewrite_step2a）"
        )
        return GateResult(
            chapter_no=chapter_no,
            passed=False,
            final_score=score,
            threshold=threshold,
            attempts=attempts,
            blocked_path=None,
            final_text=None,
            soft_threshold=soft_threshold,
            soft_passed=False if soft_threshold is not None else None,
            action="rewrite_step2a",
            escape_hatch_triggered=True,
        )

    logger.warning("%d次重试均未通过门禁，章节被阻断", effective_max)
    blocked_path = _write_blocked(
        chapter_no, violations, threshold, score, project_root, attempts=effective_max
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
        soft_threshold=soft_threshold,
        soft_passed=False if soft_threshold is not None else None,
        action="continue",
    )
