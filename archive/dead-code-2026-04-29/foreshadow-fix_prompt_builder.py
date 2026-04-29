"""Build actionable fix prompts for foreshadow lifecycle violations."""

from __future__ import annotations

from ink_writer.foreshadow.tracker import ForeshadowScanResult, OverdueInfo, SilentInfo

VIOLATION_FIX_TEMPLATES: dict[str, str] = {
    "FORESHADOW_OVERDUE_CRITICAL": "核心伏笔「{title}」已逾期{overdue}章（目标ch{target}），读者期待已久。请在本章安排关键兑现：可以是完整揭晓，也可以是重大线索推进。注意与当前剧情自然衔接，不得生硬。",
    "FORESHADOW_OVERDUE_HIGH": "重要伏笔「{title}」已逾期{overdue}章（目标ch{target}）。请在本章通过对话、事件或回忆推进此线索，让读者看到进展。",
    "FORESHADOW_OVERDUE_MEDIUM": "次要伏笔「{title}」已逾期{overdue}章（目标ch{target}）。建议在本章自然提及或推进，避免长期悬而不决。",
    "FORESHADOW_SILENT": "伏笔「{title}」已沉默{silent}章（上次提及ch{last_touch}），面临读者遗忘风险。请在本章通过角色提及、环境暗示或情节关联重新激活此线索。",
    "FORESHADOW_DENSITY_HIGH": "当前活跃伏笔{count}条，超过阈值{limit}条。建议在本章至少解决1条次要伏笔，降低读者认知负担。",
}


def build_fix_prompt(scan: ForeshadowScanResult, warn_limit: int = 15) -> str:
    """Build a targeted fix prompt from foreshadow scan violations."""
    violations: list[str] = []

    for od in scan.overdue:
        vid = f"FORESHADOW_OVERDUE_{od.severity.upper()}"
        template = VIOLATION_FIX_TEMPLATES.get(vid, "")
        if template:
            text = template.format(
                title=od.record.title,
                overdue=od.overdue_chapters,
                target=od.record.target_payoff_chapter,
            )
            violations.append(f"[{od.severity}] {vid}：{text}")

    for si in scan.silent:
        template = VIOLATION_FIX_TEMPLATES["FORESHADOW_SILENT"]
        text = template.format(
            title=si.record.title,
            silent=si.silent_chapters,
            last_touch=si.record.last_touched_chapter,
        )
        violations.append(f"[medium] FORESHADOW_SILENT：{text}")

    if scan.density_warning:
        template = VIOLATION_FIX_TEMPLATES["FORESHADOW_DENSITY_HIGH"]
        text = template.format(count=scan.total_active, limit=warn_limit)
        violations.append(f"[low] FORESHADOW_DENSITY_HIGH：{text}")

    if not violations:
        return ""

    lines = ["【伏笔生命周期修复指令】请针对以下问题逐项处理：", ""]
    for i, v in enumerate(violations, 1):
        lines.append(f"{i}. {v}")

    lines.append("")
    lines.append("修复时保持剧情自然流畅。伏笔推进应融入角色行动和对话中，不得生硬插入无关内容。")
    return "\n".join(lines)


def build_overdue_violation_list(scan: ForeshadowScanResult) -> list[dict]:
    """Build violation dicts compatible with checker-output-schema."""
    violations: list[dict] = []

    for od in scan.overdue:
        violations.append({
            "id": f"FORESHADOW_OVERDUE_{od.severity.upper()}",
            "severity": od.severity,
            "must_fix": od.severity in ("critical", "high"),
            "description": f"伏笔「{od.record.title}」逾期{od.overdue_chapters}章",
            "thread_id": od.record.thread_id,
            "target_chapter": od.record.target_payoff_chapter,
            "suggestion": f"在本章安排兑现或推进 [{od.record.thread_id}]",
        })

    for si in scan.silent:
        violations.append({
            "id": "FORESHADOW_SILENT",
            "severity": "medium",
            "must_fix": False,
            "description": f"伏笔「{si.record.title}」沉默{si.silent_chapters}章",
            "thread_id": si.record.thread_id,
            "suggestion": f"在本章自然提及 [{si.record.thread_id}]",
        })

    return violations
