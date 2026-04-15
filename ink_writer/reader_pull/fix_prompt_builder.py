"""Build actionable fix prompts from reader-pull-checker violations."""

from __future__ import annotations

VIOLATION_FIX_TEMPLATES: dict[str, str] = {
    "HARD-001": "可读性不足：确保读者能理解本章「发生了什么/谁/为什么」，补充关键交代。",
    "HARD-002": "承诺违背：上章钩子「{detail}」在本章无回应，必须在开头或中段回应。",
    "HARD-003": "节奏停滞：连续多章无推进，本章必须加入实质性剧情转折或冲突升级。",
    "HARD-004": "冲突真空：整章无问题/目标/代价，必须加入至少一个核心冲突。",
    "HARD-005": "开篇空洞：前500字缺乏冲突/风险/强情绪/悬念，改写开篇引入张力。",
    "SOFT_NEXT_REASON": "下章动机弱：章末读者无法明确「为何要点下一章」，强化期待锚点。",
    "SOFT_HOOK_ANCHOR": "期待锚点缺失：章末或后段需留下未闭合问题或悬念。",
    "SOFT_HOOK_STRENGTH": "钩子强度不足：将章末钩子从'{detail}'提升，增加紧迫感或好奇心。",
    "SOFT_MICROPAYOFF": "微兑现不足：本章需补充至少{detail}个微兑现（信息/关系/能力/认可等）。",
    "SOFT_HOOK_TYPE": "钩子类型不匹配题材偏好：考虑改用更匹配的钩子类型。",
    "SOFT_PATTERN_REPEAT": "模式重复：连续多章同类型钩子/开头，必须变换手法。",
    "SOFT_EXPECTATION_OVERLOAD": "期待过载：本章新增期待过多，精简至2个以内。",
    "SOFT_RHYTHM_NATURALNESS": "节奏机械：钩子/爽点打点过于均匀，调整间距使节奏更自然。",
}


def build_fix_prompt(violations: list[dict]) -> str:
    """Build a targeted fix prompt from violation list.

    Each violation dict should have at least ``id`` and optionally
    ``description`` / ``suggestion`` / ``fix_suggestion`` fields.
    """
    if not violations:
        return ""

    lines: list[str] = ["【追读力修复指令】请针对以下问题逐项修复：", ""]

    for i, v in enumerate(violations, 1):
        vid = v.get("id", "UNKNOWN")
        detail = v.get("description", "") or v.get("suggestion", "") or ""
        template = VIOLATION_FIX_TEMPLATES.get(vid, "")

        if template and "{detail}" in template:
            instruction = template.format(detail=detail)
        elif template:
            instruction = template
        else:
            instruction = detail

        fix_hint = v.get("fix_suggestion", "") or v.get("suggestion", "")
        severity = v.get("severity", "medium")

        line = f"{i}. [{severity}] {vid}：{instruction}"
        if fix_hint and fix_hint != detail:
            line += f"\n   → 建议：{fix_hint}"
        lines.append(line)

    lines.append("")
    lines.append("修复时不得改变剧情事实、设定物理边界或角色核心行为。")
    return "\n".join(lines)


def normalize_checker_output(raw: dict) -> dict:
    """Normalize reader-pull-checker output to {score, violations, fix_prompt}.

    Accepts both the existing agent output format (overall_score, hard_violations,
    soft_suggestions, issues) and already-normalized format.
    """
    score = raw.get("score", raw.get("overall_score", 0.0))

    violations: list[dict] = []

    for hv in raw.get("hard_violations", []):
        entry = dict(hv)
        if "id" not in entry:
            entry["id"] = entry.get("rule_id", "UNKNOWN")
        entry["must_fix"] = True
        violations.append(entry)

    for ss in raw.get("soft_suggestions", []):
        entry = dict(ss)
        if "must_fix" not in entry:
            entry["must_fix"] = False
        violations.append(entry)

    for issue in raw.get("issues", []):
        entry = dict(issue)
        if "id" not in entry:
            entry["id"] = entry.get("type", "UNKNOWN")
        violations.append(entry)

    existing_violations = raw.get("violations", [])
    if existing_violations and not violations:
        violations = list(existing_violations)

    fix_prompt = raw.get("fix_prompt", "")
    if not fix_prompt:
        fix_prompt = build_fix_prompt(violations)

    return {
        "score": float(score),
        "violations": violations,
        "fix_prompt": fix_prompt,
    }
