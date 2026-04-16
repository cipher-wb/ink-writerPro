"""Hard gate for ink-write: anti-detection sentence diversity check + polish retry loop."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ink_writer.anti_detection.config import AntiDetectionConfig, load_config
from ink_writer.anti_detection.fix_prompt_builder import normalize_checker_output


@dataclass
class AntiDetectionAttempt:
    attempt: int
    score: float
    violations: list[dict]
    fix_prompt: str
    passed: bool


@dataclass
class AntiDetectionResult:
    chapter_no: int
    passed: bool
    final_score: float
    threshold: float
    attempts: list[AntiDetectionAttempt] = field(default_factory=list)
    blocked_path: str | None = None
    final_text: str | None = None
    zero_tolerance_hit: str | None = None


def _setup_logger(chapter_no: int, project_root: str) -> logging.Logger:
    log_dir = os.path.join(project_root, "logs", "anti-detection")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"chapter_{chapter_no}.log")

    logger = logging.getLogger(f"anti-detection-gate-ch{chapter_no}")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    return logger


def check_zero_tolerance(text: str, config: AntiDetectionConfig) -> str | None:
    """Check text against zero-tolerance rules.

    Returns the rule ID if any rule is violated, None otherwise.
    Zero-tolerance violations cause immediate block with no retry.
    """
    if not text or not config.zero_tolerance:
        return None

    first_line = ""
    for line in text.strip().splitlines():
        stripped = line.strip()
        if stripped:
            first_line = stripped
            break

    for rule in config.zero_tolerance:
        for pattern in rule.patterns:
            if rule.id == "ZT_TIME_OPENING":
                if re.search(pattern, first_line):
                    return rule.id
            else:
                if re.search(pattern, text):
                    return rule.id
    return None


def _write_blocked(
    chapter_no: int,
    violations: list[dict],
    threshold: float,
    score: float,
    fix_prompt: str,
    project_root: str,
    *,
    zero_tolerance_hit: str | None = None,
) -> str:
    chapter_dir = os.path.join(project_root, "chapters", str(chapter_no))
    os.makedirs(chapter_dir, exist_ok=True)
    blocked_path = os.path.join(chapter_dir, "anti_detection_blocked.md")

    if zero_tolerance_hit:
        lines = [
            f"# 第{chapter_no}章 — AI味硬门禁阻断（零容忍）",
            "",
            f"**触发规则**: {zero_tolerance_hit}",
            "**处理方式**: 立即阻断，不触发 polish 重试",
            "",
            "## 说明",
            "",
            "零容忍项匹配即阻断。必须手动修复后重新运行。",
            "",
        ]
    else:
        lines = [
            f"# 第{chapter_no}章 — AI味硬门禁阻断",
            "",
            f"**最终得分**: {score}（阈值: {threshold}）",
            f"**重试次数**: 已达上限",
            "",
            "## 未解决违规",
            "",
        ]
        for v in violations:
            vid = v.get("id", "?")
            severity = v.get("severity", "?")
            desc = v.get("description", v.get("suggestion", ""))
            lines.append(f"- **[{vid}]** ({severity}): {desc}")
            fix = v.get("fix_suggestion", "")
            if fix and fix != desc:
                lines.append(f"  - 建议：{fix}")

        lines.extend(["", "## 修复提示", "", fix_prompt, ""])

    with open(blocked_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return blocked_path


def run_anti_detection_gate(
    chapter_text: str,
    chapter_no: int,
    project_root: str,
    *,
    checker_fn: Callable[[str, int], dict],
    polish_fn: Callable[[str, str, int], str],
    config: AntiDetectionConfig | None = None,
) -> AntiDetectionResult:
    """Run anti-detection hard gate with zero-tolerance check + polish retry loop.

    Args:
        chapter_text: Current chapter text.
        chapter_no: Chapter number.
        project_root: Project root directory.
        checker_fn: Callable(chapter_text, chapter_no) -> raw checker result dict.
        polish_fn: Callable(chapter_text, fix_prompt, chapter_no) -> polished text.
        config: Anti-detection config. If None, loads from default path.

    Returns:
        AntiDetectionResult with pass/fail status and attempt history.
    """
    if config is None:
        config = load_config()

    if not config.enabled:
        return AntiDetectionResult(
            chapter_no=chapter_no,
            passed=True,
            final_score=100.0,
            threshold=0.0,
            final_text=chapter_text,
        )

    logger = _setup_logger(chapter_no, project_root)

    zt_hit = check_zero_tolerance(chapter_text, config)
    if zt_hit:
        logger.warning("零容忍规则触发: %s — 立即阻断", zt_hit)
        blocked_path = _write_blocked(
            chapter_no, [], 0, 0, "", project_root,
            zero_tolerance_hit=zt_hit,
        )
        return AntiDetectionResult(
            chapter_no=chapter_no,
            passed=False,
            final_score=0.0,
            threshold=0.0,
            blocked_path=blocked_path,
            zero_tolerance_hit=zt_hit,
        )

    threshold = config.score_threshold
    if chapter_no <= 3:
        threshold = config.golden_three_threshold

    max_retries = config.max_retries
    logger.info(
        "开始AI味硬门禁检查 chapter=%d threshold=%.1f max_retries=%d",
        chapter_no, threshold, max_retries,
    )

    current_text = chapter_text
    attempts: list[AntiDetectionAttempt] = []
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

        attempt = AntiDetectionAttempt(
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
            logger.info("AI味硬门禁通过")
            return AntiDetectionResult(
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

    logger.warning("AI味硬门禁 %d 次重试均未通过，章节被阻断", max_retries)
    blocked_path = _write_blocked(
        chapter_no, violations, threshold, score, fix_prompt, project_root,
    )
    logger.info("阻断报告已写入: %s", blocked_path)

    return AntiDetectionResult(
        chapter_no=chapter_no,
        passed=False,
        final_score=score,
        threshold=threshold,
        attempts=attempts,
        blocked_path=blocked_path,
    )
