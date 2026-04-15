"""Build actionable fix prompts for plotline lifecycle violations."""

from __future__ import annotations

from ink_writer.plotline.tracker import PlotlineScanResult, InactiveInfo

VIOLATION_FIX_TEMPLATES: dict[str, str] = {
    "PLOTLINE_INACTIVE_CRITICAL": "主线「{title}」已{gap}章未推进（阈值{max_gap}章）。主线长期断更将导致读者失去方向感。请在本章通过关键事件、主角行动或核心冲突推进此主线。",
    "PLOTLINE_INACTIVE_HIGH": "支线「{title}」已{gap}章未推进（阈值{max_gap}章）。请在本章通过配角行动、侧面信息或场景关联推进此支线，保持叙事丰富度。",
    "PLOTLINE_INACTIVE_MEDIUM": "暗线「{title}」已{gap}章未推进（阈值{max_gap}章）。建议在本章通过暗示、伏笔或背景细节隐性推进，保持读者潜意识中的悬念。",
    "PLOTLINE_DENSITY_HIGH": "当前活跃线程{count}条，超过阈值{limit}条。叙事线过多会分散读者注意力，建议收束1-2条次要支线。",
}

TYPE_LABELS = {"main": "主线", "sub": "支线", "dark": "暗线"}


def build_fix_prompt(scan: PlotlineScanResult, warn_limit: int = 10) -> str:
    """Build a targeted fix prompt from plotline scan violations."""
    violations: list[str] = []

    for ia in scan.inactive:
        vid = f"PLOTLINE_INACTIVE_{ia.severity.upper()}"
        template = VIOLATION_FIX_TEMPLATES.get(vid, "")
        if template:
            text = template.format(
                title=ia.record.title,
                gap=ia.gap_chapters,
                max_gap=ia.max_gap,
            )
            violations.append(f"[{ia.severity}] {vid}：{text}")

    if scan.density_warning:
        template = VIOLATION_FIX_TEMPLATES["PLOTLINE_DENSITY_HIGH"]
        text = template.format(count=scan.total_active, limit=warn_limit)
        violations.append(f"[low] PLOTLINE_DENSITY_HIGH：{text}")

    if not violations:
        return ""

    lines = ["【明暗线推进修复指令】请针对以下问题逐项处理：", ""]
    for i, v in enumerate(violations, 1):
        lines.append(f"{i}. {v}")

    lines.append("")
    lines.append("修复时保持剧情自然流畅。线程推进应融入主线叙事中，不得为推进而强行切换场景。")
    return "\n".join(lines)


def build_inactive_violation_list(scan: PlotlineScanResult) -> list[dict]:
    """Build violation dicts compatible with checker-output-schema."""
    violations: list[dict] = []

    for ia in scan.inactive:
        label = TYPE_LABELS.get(ia.record.line_type, "支线")
        violations.append({
            "id": f"PLOTLINE_INACTIVE_{ia.severity.upper()}",
            "severity": ia.severity,
            "must_fix": ia.severity in ("critical", "high"),
            "description": f"{label}「{ia.record.title}」已{ia.gap_chapters}章未推进（阈值{ia.max_gap}章）",
            "thread_id": ia.record.thread_id,
            "line_type": ia.record.line_type,
            "suggestion": f"在本章推进 [{ia.record.thread_id}]（{label}）",
        })

    return violations
