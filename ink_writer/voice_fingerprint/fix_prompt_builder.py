"""Build actionable fix prompts for voice fingerprint violations."""

from __future__ import annotations

from ink_writer.voice_fingerprint.fingerprint import (
    ChapterVoiceReport,
    VoiceFingerprint,
    VoiceViolation,
)

VIOLATION_FIX_TEMPLATES: dict[str, str] = {
    "VOICE_FORBIDDEN_EXPRESSION": (
        "角色「{name}」使用了禁忌表达「{detail}」。"
        "该角色的语气指纹明确禁止此类表达。"
        "请替换为符合角色性格的说法：语气={tone}，用词层次={vocab}。"
    ),
    "VOICE_CATCHPHRASE_ABSENT": (
        "角色「{name}」已多章未使用标志性口头禅。"
        "已知口头禅：{detail}。"
        "请在本章对话中自然融入至少一个口头禅，不要生硬。"
    ),
    "VOICE_VOCAB_MISMATCH": (
        "角色「{name}」的对话用词层次偏离指纹。"
        "预期层次：{vocab}。"
        "请调整对话用词，使其贴合角色的说话习惯和教育背景。"
    ),
    "VOICE_INDISTINCT": (
        "角色「{name}」的对话风格与其他角色过于相似。"
        "请增大风格差异：{detail}。"
        "目标：去掉说话人名字后，仅从用词和句式就能判断是谁在说话。"
    ),
}


def build_fix_prompt(
    report: ChapterVoiceReport,
    fingerprints: dict[str, tuple[str, VoiceFingerprint]] | None = None,
) -> str:
    """Build a targeted fix prompt from voice violation report."""
    if not report.violations and not report.distinctiveness_issues:
        return ""

    all_violations = report.violations + report.distinctiveness_issues
    lines = ["【语气指纹修复指令】请针对以下角色语音一致性问题逐项处理：", ""]

    for i, v in enumerate(all_violations, 1):
        template = VIOLATION_FIX_TEMPLATES.get(v.violation_id, "")
        if not template:
            lines.append(f"{i}. [{v.severity}] {v.description}。建议：{v.suggestion}")
            continue

        fp = None
        if fingerprints and v.entity_id in fingerprints:
            _, fp = fingerprints[v.entity_id]

        detail = ""
        if v.violation_id == "VOICE_FORBIDDEN_EXPRESSION":
            detail = v.description.split("「")[-1].rstrip("」") if "「" in v.description else ""
        elif v.violation_id == "VOICE_CATCHPHRASE_ABSENT":
            detail = ", ".join(fp.catchphrases[:3]) if fp else "无"
        elif v.violation_id == "VOICE_INDISTINCT":
            detail = v.suggestion

        text = template.format(
            name=v.entity_name,
            detail=detail,
            tone=fp.tone if fp else "未知",
            vocab=fp.vocabulary_level if fp else "口语",
        )
        lines.append(f"{i}. [{v.severity}] {v.violation_id}：{text}")

    lines.append("")
    lines.append(
        "修复时保持角色个性鲜明。"
        "每个角色的对话应该具有辨识度：去掉人名后，仅从说话方式就能识别角色。"
    )
    return "\n".join(lines)


def normalize_checker_output(raw_result: dict) -> dict:
    """Normalize ooc-checker output into standard {score, violations, fix_prompt} format."""
    score = raw_result.get("score", raw_result.get("overall_score", 0.0))
    if isinstance(score, str):
        try:
            score = float(score)
        except ValueError:
            score = 0.0

    violations = raw_result.get("violations", [])
    if not isinstance(violations, list):
        violations = []

    normalized_violations = []
    for v in violations:
        if isinstance(v, dict):
            normalized_violations.append({
                "id": v.get("id", v.get("violation_id", "VOICE_UNKNOWN")),
                "severity": v.get("severity", "medium"),
                "must_fix": v.get("must_fix", False),
                "description": v.get("description", ""),
                "entity_id": v.get("entity_id", ""),
                "entity_name": v.get("entity_name", ""),
                "suggestion": v.get("suggestion", ""),
            })

    fix_prompt = raw_result.get("fix_prompt", "")

    return {
        "score": float(score),
        "violations": normalized_violations,
        "fix_prompt": fix_prompt,
    }
