"""Build actionable fix prompts from anti-detection violations."""

from __future__ import annotations

VIOLATION_FIX_TEMPLATES: dict[str, str] = {
    "AD_SENTENCE_CV": "句长节奏过于均匀：交替使用碎句（≤8字）和长流句（≥35字），制造心电图式波动。",
    "AD_SENTENCE_FRAGMENTATION": "句子碎片化严重：将连续短句合并为25-40字复合句，用逗号串联动作和细节。短句仅在冲击时刻使用。",
    "AD_SHORT_SENTENCE_EXCESS": "短句占比过高：减少≤8字碎句，合并为中长复合句。保留少量碎句用于冲击感。",
    "AD_LONG_SENTENCE_DEFICIT": "长句纵深不足：在描写/内心段落插入≥35字长句，展现细腻纹理。",
    "AD_PARAGRAPH_REGULAR": "段落结构过于工整：拆分长段为碎片段，增加单句段，让段落呈心电图分布。",
    "AD_PARAGRAPH_CV": "段落长度过于均匀：交替使用100+字长段和≤15字碎片段，增加视觉节奏。",
    "AD_DIALOGUE_LOW": "对话占比过低：将内心独白转化为角色对话，增加直接引语和角色互动。",
    "AD_EXCLAMATION_LOW": "感叹号密度不足：角色情绪爆发时使用感叹号，不要为追求冷静而压制情感表达。",
    "AD_ELLIPSIS_LOW": "省略号不足：欲言又止/震惊/沉默时使用省略号，增加戏剧停顿和留白。",
    "AD_EMOTION_PUNCT_LOW": "情感标点总量不足：增加感叹号/省略号/反问句，让角色情绪外化，文字有温度。",
    "AD_CAUSAL_DENSE": "因果逻辑链过密：删除中间因果环节，让读者自行推断，保留叙事跳跃感。",
    "ZT_TIME_OPENING": "【零容忍】章节以时间标记开头：必须改为行动/对话/感官感知/悬念切入。",
    "ZT_MEANWHILE": "【零容忍】使用'与此同时'全知转场：改为POV角色有限感知的自然转场。",
}


def build_fix_prompt(violations: list[dict]) -> str:
    """Build a targeted fix prompt from violation list."""
    if not violations:
        return ""

    lines: list[str] = ["【句式多样性修复指令】请针对以下问题逐项修复：", ""]

    for i, v in enumerate(violations, 1):
        vid = v.get("id", "UNKNOWN")
        detail = v.get("description", "") or v.get("suggestion", "") or ""
        template = VIOLATION_FIX_TEMPLATES.get(vid, "")

        instruction = template if template else detail

        fix_hint = v.get("fix_suggestion", "") or v.get("suggestion", "")
        severity = v.get("severity", "medium")

        line = f"{i}. [{severity}] {vid}：{instruction}"
        if fix_hint and fix_hint != instruction:
            line += f"\n   → 建议：{fix_hint}"
        lines.append(line)

    lines.append("")
    lines.append("修复时不得改变剧情事实、设定物理边界或角色核心行为。")
    return "\n".join(lines)


def normalize_checker_output(raw: dict) -> dict:
    """Normalize anti-detection-checker output to {score, violations, fix_prompt}.

    Accepts both the agent output format (overall_score, dimensions, fix_priority)
    and already-normalized format.
    """
    score = raw.get("score", raw.get("overall_score", 0.0))

    violations: list[dict] = []

    for fp in raw.get("fix_priority", []):
        entry = dict(fp)
        if "id" not in entry:
            entry["id"] = entry.get("type", "UNKNOWN")
        entry.setdefault("severity", "high")
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
