#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anti-AI lint for chapter text.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    from .golden_three import analyze_golden_three_opening
except ImportError:  # pragma: no cover
    from golden_three import analyze_golden_three_opening


TEMPLATE_PHRASES = (
    "不由得",
    "嘴角微微上扬",
    "深吸一口气",
    "与此同时",
    "下一刻",
    "这一刻",
    "毫无疑问",
    "显然",
    "仿佛",
    "要知道",
    "某种程度上",
    "换句话说",
)

CONNECTORS = (
    "然后",
    "随后",
    "与此同时",
    "紧接着",
    "然而",
    "但是",
    "于是",
    "接着",
    "很快",
)

CLICHE_FOUR_CHAR = (
    "风轻云淡",
    "若有所思",
    "不动声色",
    "意味深长",
    "心中一动",
    "瞳孔一缩",
    "倒吸一口",
    "呼吸一滞",
    "微微一愣",
    "不由一怔",
    "不寒而栗",
    "面无表情",
)

HOOK_PATTERNS = (
    "究竟会",
    "到底是",
    "谁也没想到",
    "原来如此",
    "没想到",
    "真正的",
    "更大的危机",
)


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"[。！？!?；;\n]+", str(text or ""))
    return [part.strip() for part in parts if part.strip()]


def _paragraphs(text: str) -> List[str]:
    return [part.strip() for part in re.split(r"\n{2,}", str(text or "")) if part.strip()]


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    variance = sum((value - avg) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def anti_ai_lint_text(
    text: str,
    *,
    chapter: int = 0,
    genre_profile_key: str = "",
    golden_three_contract: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    text = str(text or "")
    compact = re.sub(r"\s+", "", text)
    length = len(compact)
    sentences = _split_sentences(text)
    sentence_lengths = [len(re.sub(r"\s+", "", sentence)) for sentence in sentences if sentence]
    paragraphs = _paragraphs(text)

    issues: List[Dict[str, Any]] = []
    penalty = 0.0

    template_hits = {phrase: text.count(phrase) for phrase in TEMPLATE_PHRASES if phrase in text}
    template_count = sum(template_hits.values())
    if template_count >= 3:
        issues.append(
            {
                "id": "template_phrases",
                "severity": "high" if template_count >= 6 else "medium",
                "message": "模板化表述偏多，容易出现程式化口气。",
                "count": template_count,
                "examples": list(template_hits.keys())[:5],
            }
        )
        penalty += min(0.28, 0.05 * template_count)

    connector_count = sum(text.count(token) for token in CONNECTORS)
    connector_density = connector_count / max(1, len(sentences))
    if len(sentences) >= 8 and connector_density >= 0.75:
        issues.append(
            {
                "id": "connector_overuse",
                "severity": "medium",
                "message": "连接词堆积，叙述推进过于像摘要。",
                "count": connector_count,
            }
        )
        penalty += min(0.16, 0.04 * connector_density)

    avg_sentence_len = _mean(sentence_lengths)
    sentence_cv = (_stddev(sentence_lengths) / avg_sentence_len) if avg_sentence_len else 0.0
    if len(sentence_lengths) >= 6 and avg_sentence_len >= 12 and sentence_cv < 0.22:
        issues.append(
            {
                "id": "sentence_homogeneity",
                "severity": "medium",
                "message": "句长变化过小，节奏发平。",
                "count": round(sentence_cv, 4),
            }
        )
        penalty += 0.12

    dialogue_blocks = re.findall(r"“[^”]{18,}”", text)
    exposition_dialogue = [
        line
        for line in dialogue_blocks
        if re.search(r"(因为|所以|首先|其次|换句话说|也就是说|总之|换言之)", line)
    ]
    if len(exposition_dialogue) >= 2:
        issues.append(
            {
                "id": "expository_dialogue",
                "severity": "high" if len(exposition_dialogue) >= 3 else "medium",
                "message": "对白解释味过重，像在给读者做说明书。",
                "count": len(exposition_dialogue),
            }
        )
        penalty += min(0.22, 0.08 * len(exposition_dialogue))

    cliche_hits = {phrase: text.count(phrase) for phrase in CLICHE_FOUR_CHAR if phrase in text}
    cliche_count = sum(cliche_hits.values())
    cliche_density = cliche_count / max(1, len(sentences))
    if cliche_count >= 3 and cliche_density >= 0.25:
        issues.append(
            {
                "id": "cliche_four_char",
                "severity": "medium",
                "message": "套语密度偏高，容易带出 AI 拼贴感。",
                "count": cliche_count,
                "examples": list(cliche_hits.keys())[:5],
            }
        )
        penalty += min(0.18, 0.05 * cliche_count)

    opening_fingerprints: Dict[str, int] = {}
    for paragraph in paragraphs:
        head = re.sub(r"[，。！？!?\s]", "", paragraph[:10])
        if len(head) >= 4:
            opening_fingerprints[head] = opening_fingerprints.get(head, 0) + 1
    repeated_openings = [key for key, count in opening_fingerprints.items() if count >= 3]
    if repeated_openings:
        issues.append(
            {
                "id": "repeated_openings",
                "severity": "medium",
                "message": "段落开头重复，章节展开像套模板。",
                "count": len(repeated_openings),
                "examples": repeated_openings[:3],
            }
        )
        penalty += 0.12

    last_section = "\n".join(paragraphs[-3:]) if paragraphs else text[-300:]
    hook_count = sum(last_section.count(pattern) for pattern in HOOK_PATTERNS)
    if hook_count >= 2:
        issues.append(
            {
                "id": "hook_cliche",
                "severity": "medium",
                "message": "章末钩子套话明显，悬念制造过于用力。",
                "count": hook_count,
            }
        )
        penalty += min(0.12, 0.04 * hook_count)

    golden_three_result = analyze_golden_three_opening(
        text=text,
        chapter=chapter,
        genre_profile_key=genre_profile_key,
        contract=golden_three_contract,
    )
    if golden_three_result.get("applied"):
        issues.extend(golden_three_result.get("issues") or [])
        if not golden_three_result.get("passed", True):
            golden_score = float((golden_three_result.get("metrics") or {}).get("score") or 0.0)
            penalty += max(0.0, 1.0 - golden_score) * 0.35

    score = round(max(0.0, 1.0 - penalty), 4)
    passed = (
        score >= 0.72
        and not any(issue["severity"] == "high" for issue in issues)
        and (not golden_three_result.get("applied") or bool(golden_three_result.get("passed")))
    )
    return {
        "passed": passed,
        "score": score,
        "issues": issues,
        "metrics": {
            "length": length,
            "sentence_count": len(sentences),
            "avg_sentence_len": round(avg_sentence_len, 2),
            "sentence_cv": round(sentence_cv, 4),
            "connector_density": round(connector_density, 4),
            "template_count": template_count,
            "dialogue_block_count": len(dialogue_blocks),
            "expository_dialogue_count": len(exposition_dialogue),
            "cliche_count": cliche_count,
            "hook_count": hook_count,
            "chapter": int(chapter or 0),
            "golden_three_applied": bool(golden_three_result.get("applied")),
            "golden_three_score": round(float((golden_three_result.get("metrics") or {}).get("score") or 0.0), 4),
            "golden_three_trigger_detected": bool(
                (golden_three_result.get("metrics") or {}).get("trigger_detected", False)
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Anti-AI lint")
    parser.add_argument("--text", help="直接传入文本")
    parser.add_argument("--file", help="从文件读取文本")
    parser.add_argument("--chapter", type=int, default=0, help="章节号，用于黄金三章检测")
    parser.add_argument("--genre-profile-key", default="", help="题材 profile key")
    args = parser.parse_args()

    text = args.text or ""
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")

    print(
        json.dumps(
            anti_ai_lint_text(
                text,
                chapter=args.chapter,
                genre_profile_key=args.genre_profile_key,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
