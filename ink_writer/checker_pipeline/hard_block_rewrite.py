"""US-013: Hard Block Rewrite Mode — 全章重写 + 复检 + 退出码 2。

当三个硬门禁（anti-detection zero_tolerance / colloquial red / directness red）任一失败时，
执行全章重写（单次 LLM 调用），复检后仍失败则标记 hard_blocked。

Usage:
    from ink_writer.checker_pipeline.hard_block_rewrite import (
        HardBlockResult,
        run_hard_block_rewrite,
    )
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# US-013 关注的三个硬阻断 gate
_HARD_BLOCK_GATES = {"anti_detection", "colloquial", "directness"}


@dataclass
class HardBlockResult:
    """硬阻断重写结果。"""
    chapter_id: int
    hard_blocked: bool  # True = 重写后仍失败，需人工介入
    rewritten_text: str = ""  # 重写后的章节文本（成功时）
    original_text: str = ""
    retry_count: int = 0
    max_retries: int = 1
    failure_gates: list[str] = field(default_factory=list)  # 复检仍失败的 gate
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "chapter_id": self.chapter_id,
            "hard_blocked": self.hard_blocked,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "failure_gates": self.failure_gates,
            "error": self.error,
        }


def _load_max_hard_block_retries(project_root: Path) -> int:
    """从 config/anti-detection.yaml 读取 max_hard_block_retries。"""
    config_path = project_root / "config" / "anti-detection.yaml"
    if not config_path.exists():
        return 1
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return int(cfg.get("max_hard_block_retries", 1))
    except Exception:
        return 1


def _is_prose_overhaul_enabled(project_root: Path) -> bool:
    """检查 prose_overhaul_enabled 总开关。"""
    config_path = project_root / "config" / "anti-detection.yaml"
    if not config_path.exists():
        return True
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("prose_overhaul_enabled", True) is not False
    except Exception:
        return True


def _collect_violations(gate_results: dict) -> list[str]:
    """从 gate_results 收集三个硬阻断 gate 的违规详情。"""
    violations: list[str] = []
    for gate_name in _HARD_BLOCK_GATES:
        gr = gate_results.get(gate_name, {})
        if gr.get("status") == "failed":
            error = gr.get("error", "")
            score = gr.get("score", 0)
            violations.append(f"[{gate_name}] score={score:.2f} {error}")
    return violations


def _build_rewrite_prompt(
    chapter_text: str,
    violations: list[str],
    chapter_id: int,
) -> str:
    """构建全章重写 prompt（不含 LLM 调用，返回 prompt 字符串供外部使用）。"""
    violation_text = "\n".join(f"  - {v}" for v in violations)
    return (
        f"你是网文作家。以下章节被审查系统标记为有 AI 写作痕迹，请用更自然的爆款风格"
        f"全章重写。保持原章节的所有情节、人物、对话信息不变，只调整文笔和表达方式：\n\n"
        f"## 原章节（第{chapter_id}章）\n\n{chapter_text[:8000]}\n\n"
        f"## 违规清单\n{violation_text}\n\n"
        f"## 重写要求\n"
        f"1. 句式要有自然起伏，不能每句话都差不多长\n"
        f"2. 对话要能通过说话方式分辨角色，不要所有人说话都像同一个人\n"
        f"3. 减少成语堆砌和四字格排比\n"
        f"4. 避免双破折号（——），减少省略号密度\n"
        f"5. 保持 POV 角色视角，不要上帝视角全知叙述\n"
        f"6. 信息投放要有松有紧，不要每句话都在推进情节\n\n"
        f"请直接输出重写后的全文，不要加任何说明、注释或前缀。"
    )


def _build_chapter_report(chapter_id: int, violations: list[str], rewritten: str) -> str:
    """生成硬阻断章节的 markdown 报告。"""
    lines = [
        f"# 硬阻断报告 — 第{chapter_id}章",
        "",
        f"**状态**: HARD_BLOCKED",
        f"**重试次数**: 已用尽",
        "",
        "## 违规清单",
        "",
    ]
    for v in violations:
        lines.append(f"- {v}")
    lines.extend([
        "",
        "## 最后重写结果（前 500 字）",
        "",
        rewritten[:500] if rewritten else "(无)",
    ])
    return "\n".join(lines)


def run_hard_block_rewrite(
    chapter_text: str,
    chapter_id: int,
    gate_results: dict,
    project_root: Path | str,
    *,
    _mock_llm_rewrite: callable | None = None,
    _mock_check_fn: callable | None = None,
) -> HardBlockResult:
    """执行硬阻断全章重写逻辑。

    流程：
      1. 检查三个 hard block gate 是否有失败
      2. 有失败 → 构建 prompt → 调用 LLM 全章重写
      3. 重写后复检三个 gate → 仍失败 → hard_blocked
      4. 写 reports/blocked/chapter_NNN.md

    Args:
        chapter_text: 原始章节文本
        chapter_id: 章节号
        gate_results: 首次检查的 gate_results dict（key=gate_name, value={status, score, ...})
        project_root: 项目根目录
        _mock_llm_rewrite: (测试用) mock LLM 重写函数，签名为 (prompt: str) -> str
        _mock_check_fn: (测试用) mock 复检函数，签名为 (text: str) -> dict[gate_name, (passed, score)]

    Returns:
        HardBlockResult
    """
    project_root = Path(project_root)

    # 总开关关闭 → 跳过
    if not _is_prose_overhaul_enabled(project_root):
        logger.info("prose_overhaul_enabled=false，跳过 hard block rewrite")
        return HardBlockResult(
            chapter_id=chapter_id,
            hard_blocked=False,
            original_text=chapter_text,
        )

    max_retries = _load_max_hard_block_retries(project_root)
    if max_retries == 0:
        # 不重写，直接标 hard_blocked
        violations = _collect_violations(gate_results)
        return HardBlockResult(
            chapter_id=chapter_id,
            hard_blocked=True,
            original_text=chapter_text,
            max_retries=0,
            failure_gates=[g for g in _HARD_BLOCK_GATES
                           if gate_results.get(g, {}).get("status") == "failed"],
        )

    # 检查是否有关注的 gate 失败
    failed_gates = [
        g for g in _HARD_BLOCK_GATES
        if gate_results.get(g, {}).get("status") == "failed"
    ]
    if not failed_gates:
        return HardBlockResult(
            chapter_id=chapter_id,
            hard_blocked=False,
            original_text=chapter_text,
        )

    result = HardBlockResult(
        chapter_id=chapter_id,
        hard_blocked=False,
        original_text=chapter_text,
        max_retries=max_retries,
        failure_gates=failed_gates,
    )

    current_text = chapter_text

    for attempt in range(1, max_retries + 1):
        violations = _collect_violations(gate_results)
        prompt = _build_rewrite_prompt(current_text, violations, chapter_id)

        # 调用 LLM 重写
        try:
            if _mock_llm_rewrite:
                rewritten = _mock_llm_rewrite(prompt)
            else:
                rewritten = _call_llm_rewrite(prompt)
        except Exception as exc:
            logger.error("LLM 重写失败 (attempt %d/%d): %s", attempt, max_retries, exc)
            result.error = str(exc)
            result.retry_count = attempt
            result.hard_blocked = True
            break

        if not rewritten or len(rewritten) < 100:
            logger.warning("LLM 重写返回过短 (%d chars)，视为失败", len(rewritten))
            result.error = "LLM rewrite returned too short text"
            result.retry_count = attempt
            result.hard_blocked = True
            break

        result.rewritten_text = rewritten
        result.retry_count = attempt
        current_text = rewritten

        # 复检
        try:
            if _mock_check_fn:
                recheck_results = _mock_check_fn(rewritten)
            else:
                recheck_results = _recheck_gates(rewritten, chapter_id, project_root)
        except Exception as exc:
            logger.warning("复检失败 (attempt %d/%d): %s", attempt, max_retries, exc)
            # 复检异常 → 接受重写结果
            result.hard_blocked = False
            result.failure_gates = []
            break

        # 检查复检结果
        still_failed = [
            g for g in _HARD_BLOCK_GATES
            if not recheck_results.get(g, (True, 1.0))[0]
        ]
        if not still_failed:
            result.hard_blocked = False
            result.failure_gates = []
            break

        result.failure_gates = still_failed
        gate_results = {
            g: {"status": "failed" if g in still_failed else "passed"}
            for g in _HARD_BLOCK_GATES
        }

    else:
        result.hard_blocked = True

    # 硬阻断 → 写报告文件
    if result.hard_blocked:
        _write_blocked_report(project_root, chapter_id, violations, result.rewritten_text)

    return result


def _call_llm_rewrite(prompt: str) -> str:
    """调用 LLM 执行全章重写。

    使用项目现有的 call_claude 机制（ink_writer.core.infra.api_client）。
    如果 API key 不可用，返回空（由上层 graceful fallback）。
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY 未设置，无法执行 LLM 重写")
        return ""

    try:
        from ink_writer.core.infra.api_client import call_claude

        result = call_claude(
            system="你是网文作家，擅长爆款风格写作。请严格按照 prompt 要求重写章节全文。",
            messages=[{"role": "user", "content": prompt}],
            model="claude-sonnet-4-6",
            max_tokens=16000,
            temperature=0.7,
        )
        return result.strip() if result else ""
    except Exception as exc:
        logger.error("call_claude 失败: %s", exc)
        raise


def _recheck_gates(
    chapter_text: str,
    chapter_id: int,
    project_root: Path,
) -> dict[str, tuple[bool, float]]:
    """复检三个 hard block gate。

    Returns:
        {gate_name: (passed: bool, score: float)}
    """
    results: dict[str, tuple[bool, float]] = {}

    # anti-detection
    try:
        from ink_writer.anti_detection.anti_detection_gate import run_anti_detection_gate

        ad_result = run_anti_detection_gate(
            chapter_text=chapter_text,
            chapter_no=chapter_id,
            project_root=str(project_root),
            checker_fn=None,  # uses default
            polish_fn=None,
        )
        results["anti_detection"] = (
            bool(getattr(ad_result, "passed", True)),
            float(getattr(ad_result, "final_score", 1.0)),
        )
    except Exception as exc:
        logger.warning("anti_detection recheck failed: %s", exc)
        results["anti_detection"] = (True, 1.0)

    # colloquial
    try:
        from ink_writer.prose.colloquial_checker import (
            run_colloquial_check,
            to_checker_output,
        )

        report = run_colloquial_check(chapter_text)
        output = to_checker_output(report, chapter_no=chapter_id)
        results["colloquial"] = (
            bool(output.get("pass", False)),
            float(output.get("overall_score", 100)) / 100.0,
        )
    except Exception as exc:
        logger.warning("colloquial recheck failed: %s", exc)
        results["colloquial"] = (True, 1.0)

    # directness
    try:
        from ink_writer.prose.directness_checker import run_directness_check

        d_report = run_directness_check(chapter_text, chapter_no=chapter_id)
        if not d_report.skipped:
            results["directness"] = (d_report.passed, d_report.overall_score / 10.0)
        else:
            results["directness"] = (True, 1.0)
    except Exception as exc:
        logger.warning("directness recheck failed: %s", exc)
        results["directness"] = (True, 1.0)

    return results


def _write_blocked_report(
    project_root: Path,
    chapter_id: int,
    violations: list[str],
    rewritten_text: str,
) -> None:
    """写入 hard_blocked 报告到 reports/blocked/chapter_NNN.md。"""
    reports_dir = project_root / "reports" / "blocked"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"chapter_{chapter_id:03d}.md"
    report_content = _build_chapter_report(chapter_id, violations, rewritten_text)
    report_path.write_text(report_content, encoding="utf-8")
    logger.info("硬阻断报告已写入: %s", report_path)
