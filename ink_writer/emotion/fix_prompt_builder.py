"""Build actionable fix prompts from emotion-curve-checker violations."""

from __future__ import annotations

VIOLATION_FIX_TEMPLATES: dict[str, str] = {
    "EMOTION_FLAT": "情绪曲线过平：{detail}段连续情绪无变化，读者代入感丧失。请在平淡段落中插入冲突触发、情绪反转或感官冲击，制造情绪起伏。",
    "EMOTION_VARIANCE_LOW": "全章情绪方差不足：valence方差={detail}，低于阈值。整章缺乏情绪波动，请增加至少一个情绪高峰和一个情绪低谷。",
    "EMOTION_AROUSAL_FLAT": "唤起度过平：arousal方差={detail}，整章节奏平淡无力。请在关键段落加入紧张、震惊或热血元素以提升阅读紧迫感。",
    "EMOTION_MONOTONE": "情绪单调：全章仅检测到「{detail}」一种情绪。请引入对比情绪（如紧张后的释然、愤怒中的温情），丰富情绪层次。",
    "EMOTION_CORPUS_MISMATCH": "情绪曲线与爆款偏差大：余弦相似度={detail}，低于0.8。请参考目标曲线调整情绪节奏——开头引入、中段升级、结尾爆发或悬停。",
}


def build_fix_prompt(violations: list[dict]) -> str:
    """Build a targeted fix prompt from emotion violation list."""
    if not violations:
        return ""

    lines: list[str] = ["【情绪曲线修复指令】请针对以下问题逐项修复：", ""]

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
            line += f"\n   \u2192 \u5efa\u8bae\uff1a{fix_hint}"
        lines.append(line)

    lines.append("")
    lines.append("修复时保持情绪变化自然流畅，不得生硬插入无关冲突。不得改变剧情事实或角色核心行为。")
    return "\n".join(lines)


def normalize_checker_output(raw: dict) -> dict:
    """Normalize emotion-curve-checker output to {score, violations, fix_prompt}."""
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
