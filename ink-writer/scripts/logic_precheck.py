#!/usr/bin/env python3
"""Logic-checker 计算型预检模块 (US-003)

在 LLM logic-checker 之前执行 L1（数字算术）和 L3（属性一致）的快速预检。
预检结果注入 logic-checker 审查包的 precheck_results 字段，帮助 LLM
聚焦分析 —— 但 LLM 仍执行全部 8 层检查（双保险，非替代）。

用法:
    python3 logic_precheck.py --chapter-text <path> [--character-snapshot <json>]
    python3 logic_precheck.py --chapter-text <path> --bundle <review_bundle.json>

输出:
    JSON: {l1_precheck, l1_issues, l3_precheck, l3_issues}
"""

from __future__ import annotations

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio
_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    '.',
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# L1: Arithmetic pre-check
# ---------------------------------------------------------------------------

# Pattern: Chinese/Arabic numbers with units
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
              "百": 100, "千": 1000, "万": 10000}

# Time format: M:SS or MM:SS
_TIME_PATTERN = re.compile(r'(\d{1,2}):(\d{2})')

# Arabic numbers with optional units
_NUMBER_PATTERN = re.compile(
    r'(\d+(?:\.\d+)?)\s*'
    r'(秒|分钟|分|小时|时|天|日|米|公里|里|千米|块|元|万|亿|个|人|条|把|张|只|根|层|步|岁)?'
)

# Countdown / timer context keywords
_COUNTDOWN_KEYWORDS = ("倒计时", "计时", "读秒", "跳动", "归零", "数字")

# Money context keywords
_MONEY_KEYWORDS = ("元", "块", "钱", "找回", "付", "掏出", "支付", "大钞", "零钱", "找零")


def _parse_time_str(s: str) -> float | None:
    """Parse M:SS or MM:SS to seconds."""
    m = _TIME_PATTERN.search(s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def _extract_number_sequences(text: str) -> list[dict[str, Any]]:
    """Extract all number occurrences with position and context."""
    results = []
    for m in _NUMBER_PATTERN.finditer(text):
        value = float(m.group(1))
        unit = m.group(2) or ""
        pos = m.start()
        # Get surrounding context (60 chars each side)
        ctx_start = max(0, pos - 60)
        ctx_end = min(len(text), m.end() + 60)
        context = text[ctx_start:ctx_end]
        results.append({
            "value": value,
            "unit": unit,
            "position": pos,
            "raw": m.group(0),
            "context": context,
        })

    # Also extract M:SS time formats
    for m in _TIME_PATTERN.finditer(text):
        seconds = int(m.group(1)) * 60 + int(m.group(2))
        pos = m.start()
        ctx_start = max(0, pos - 60)
        ctx_end = min(len(text), m.end() + 60)
        context = text[ctx_start:ctx_end]
        results.append({
            "value": seconds,
            "unit": "秒(时间格式)",
            "position": pos,
            "raw": m.group(0),
            "context": context,
        })

    results.sort(key=lambda x: x["position"])
    return results


def _is_countdown_context(nums: list[dict], text: str) -> bool:
    """Check if numbers appear in a countdown/timer context."""
    return any(any(kw in n["context"] for kw in _COUNTDOWN_KEYWORDS) for n in nums)


def _is_money_context(nums: list[dict], text: str) -> bool:
    """Check if numbers appear in a money context."""
    return any(any(kw in n["context"] for kw in _MONEY_KEYWORDS) for n in nums)


def precheck_arithmetic(chapter_text: str) -> dict[str, Any]:
    """Pre-check L1: extract number sequences and verify arithmetic consistency.

    Returns:
        {
            "l1_precheck": "pass" | "issues_found",
            "l1_issues": [...]
        }
    """
    issues: list[dict[str, str]] = []
    numbers = _extract_number_sequences(chapter_text)

    if not numbers:
        return {"l1_precheck": "pass", "l1_issues": []}

    # Group numbers by proximity and unit type for sequence analysis
    # Check 1: Countdown sequences — values should decrease monotonically
    time_nums = [n for n in numbers if n["unit"] in ("秒", "秒(时间格式)", "分钟", "分")]
    if len(time_nums) >= 2 and _is_countdown_context(time_nums, chapter_text):
        for i in range(len(time_nums) - 1):
            curr = time_nums[i]
            nxt = time_nums[i + 1]
            # In a countdown, values should decrease
            if curr["value"] > nxt["value"]:
                gap = curr["value"] - nxt["value"]
                text_between = chapter_text[curr["position"]:nxt["position"]]
                # Rough narrative time estimate (very conservative)
                # Count dialogue rounds, action paragraphs
                dialogue_count = len(re.findall(r'[「""][^」""]*[」""]', text_between))
                action_sentences = len(re.findall(r'[。！？]', text_between))
                estimated_seconds = dialogue_count * 7.5 + action_sentences * 4
                if gap > 0 and estimated_seconds > 0:
                    # Only flag when narrative is SHORTER than countdown gap
                    # (not enough content to fill the elapsed time)
                    if estimated_seconds >= gap:
                        continue  # narrative covers the gap — no issue
                    deviation = (gap - estimated_seconds) / gap
                    if deviation > 0.5:
                        issues.append({
                            "type": "COUNTDOWN_GAP",
                            "location": f"第{curr['position']}字-第{nxt['position']}字",
                            "description": (
                                f"倒计时从{curr['raw']}到{nxt['raw']}，"
                                f"差值{gap:.0f}秒，叙事估算仅{estimated_seconds:.0f}秒，"
                                f"偏差{deviation:.0%}"
                            ),
                            "severity": "critical" if deviation > 0.7 else "high",
                        })

    # Check 2: Money arithmetic — sum checks in payment contexts
    money_nums = [n for n in numbers if n["unit"] in ("元", "块", "万", "亿")]
    if len(money_nums) >= 3 and _is_money_context(money_nums, chapter_text):
        # Look for payment patterns: paid X, change Y, left Z
        # Simple heuristic: if 3+ money values in close proximity, flag for LLM review
        for i in range(len(money_nums) - 2):
            trio = money_nums[i:i + 3]
            span = trio[-1]["position"] - trio[0]["position"]
            if span < 500:  # within 500 chars
                vals = [t["value"] for t in trio]
                # Check if any simple arithmetic holds
                a, b, c = vals[0], vals[1], vals[2]
                if not (
                    abs(a + b - c) < 0.01
                    or abs(a - b - c) < 0.01
                    or abs(a * b - c) < 0.01
                ):
                    # No obvious arithmetic relationship — flag for review
                    issues.append({
                        "type": "MONEY_ARITHMETIC_CHECK",
                        "location": f"第{trio[0]['position']}字-第{trio[-1]['position']}字",
                        "description": (
                            f"金额序列 {vals}，未发现明显算术关系，建议LLM深入验证"
                        ),
                        "severity": "medium",
                    })

    # Check 3: Numeric value contradictions — same unit, close proximity, conflicting values
    unit_groups: dict[str, list[dict]] = {}
    for n in numbers:
        if n["unit"] and n["unit"] not in ("秒(时间格式)",):
            unit_groups.setdefault(n["unit"], []).append(n)

    for unit, group in unit_groups.items():
        if len(group) < 2:
            continue
        for i in range(len(group) - 1):
            curr = group[i]
            nxt = group[i + 1]
            span = nxt["position"] - curr["position"]
            if span < 200 and curr["value"] != nxt["value"]:
                # Same unit, close together, different values — could be intentional
                # Only flag if context suggests they refer to the same thing
                text_between = chapter_text[curr["position"]:nxt["position"]]
                if not any(kw in text_between for kw in ("变成", "增加", "减少", "后来", "之后", "变为")):
                    issues.append({
                        "type": "NUMERIC_PROXIMITY_CHECK",
                        "location": f"第{curr['position']}字-第{nxt['position']}字",
                        "description": (
                            f"相邻{unit}数值 {curr['value']}{unit} → {nxt['value']}{unit}，"
                            f"间距{span}字，无明确变化描写"
                        ),
                        "severity": "medium",
                    })

    status = "issues_found" if issues else "pass"
    return {"l1_precheck": status, "l1_issues": issues}


# ---------------------------------------------------------------------------
# L3: Attribute consistency pre-check
# ---------------------------------------------------------------------------

# Attribute keywords to extract
_OCCUPATION_PATTERNS = [
    r'(?:是个?|当过?|做过?|身为|作为)\s*([^\s，。！？「」""、]{2,8}(?:员|师|生|者|工|官|手|长|士|家|人))',
]
_GENDER_MALE = re.compile(r'他(?:的|是|说|道|看|听|想|走|跑|站|坐|笑|叹|喊|叫)')
_GENDER_FEMALE = re.compile(r'她(?:的|是|说|道|看|听|想|走|跑|站|坐|笑|叹|喊|叫)')


def _extract_character_mentions(
    chapter_text: str,
    character_names: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """Extract attribute mentions for each known character.

    Searches for occupation patterns within the same sentence as the character name.
    """
    mentions: dict[str, list[dict[str, Any]]] = {}

    # Split text into sentences for sentence-level attribution
    sentences = re.split(r'(?<=[。！？])', chapter_text)

    for name in character_names:
        if len(name) < 2:
            continue
        char_mentions: list[dict[str, Any]] = []

        # Track position through sentences
        pos = 0
        for sentence in sentences:
            if name in sentence:
                for pattern in _OCCUPATION_PATTERNS:
                    occ_match = re.search(pattern, sentence)
                    if occ_match:
                        char_mentions.append({
                            "position": pos,
                            "attribute": "occupation",
                            "value": occ_match.group(1),
                        })
            pos += len(sentence)

        if char_mentions:
            mentions[name] = char_mentions

    return mentions


def _extract_names_from_snapshot(character_snapshot: dict | list | None) -> list[str]:
    """Extract character names from snapshot data (supports various formats)."""
    names: list[str] = []
    if not character_snapshot:
        return names

    if isinstance(character_snapshot, dict):
        # protagonist_snapshot format
        if "name" in character_snapshot:
            names.append(character_snapshot["name"])
        # appearing_characters list
        chars = character_snapshot.get("appearing_characters", [])
        if isinstance(chars, list):
            for c in chars:
                if isinstance(c, dict):
                    n = c.get("name") or c.get("canonical_name") or c.get("display_name")
                    if n:
                        names.append(n)
    elif isinstance(character_snapshot, list):
        for c in character_snapshot:
            if isinstance(c, dict):
                n = c.get("name") or c.get("canonical_name") or c.get("display_name")
                if n:
                    names.append(n)

    return [n for n in names if isinstance(n, str) and len(n) >= 2]


def precheck_attributes(
    chapter_text: str,
    character_snapshot: dict | list | None = None,
) -> dict[str, Any]:
    """Pre-check L3: extract character attribute descriptions, cross-validate consistency.

    Args:
        chapter_text: The chapter text.
        character_snapshot: Character data from review bundle (scene_context or core_context).

    Returns:
        {
            "l3_precheck": "pass" | "issues_found",
            "l3_issues": [...]
        }
    """
    issues: list[dict[str, str]] = []

    # Get character names from snapshot
    names = _extract_names_from_snapshot(character_snapshot)

    if not names:
        return {"l3_precheck": "pass", "l3_issues": []}

    # Check 1: Same character with conflicting occupations in chapter
    mentions = _extract_character_mentions(chapter_text, names)
    for name, attrs in mentions.items():
        occupations = [a for a in attrs if a["attribute"] == "occupation"]
        if len(occupations) >= 2:
            unique_values = set(a["value"] for a in occupations)
            if len(unique_values) > 1:
                issues.append({
                    "type": "ATTRIBUTE_OCCUPATION_CONFLICT",
                    "location": f"角色「{name}」",
                    "description": (
                        f"角色「{name}」在章内有多个职业描述：{', '.join(unique_values)}"
                    ),
                    "severity": "critical",
                })

    # Check 2: Gender pronoun consistency — same character referred with both 他/她
    for name in names:
        # Find all contexts where name appears and check surrounding pronouns
        positions = [m.start() for m in re.finditer(re.escape(name), chapter_text)]
        male_refs = 0
        female_refs = 0
        for pos in positions:
            window_start = max(0, pos - 5)
            window_end = min(len(chapter_text), pos + len(name) + 20)
            window = chapter_text[window_start:window_end]
            if _GENDER_MALE.search(window):
                male_refs += 1
            if _GENDER_FEMALE.search(window):
                female_refs += 1
        if male_refs > 0 and female_refs > 0:
            issues.append({
                "type": "ATTRIBUTE_GENDER_CONFLICT",
                "location": f"角色「{name}」",
                "description": (
                    f"角色「{name}」被同时用'他'({male_refs}次)和'她'({female_refs}次)指代"
                ),
                "severity": "critical",
            })

    # Check 3: Character snapshot attribute vs chapter text
    if isinstance(character_snapshot, dict):
        protagonist = character_snapshot.get("protagonist_snapshot", {})
        if isinstance(protagonist, dict) and protagonist.get("name"):
            pname = protagonist["name"]
            attrs = protagonist.get("attributes", {})
            if isinstance(attrs, dict):
                identity = attrs.get("identity") or attrs.get("职业")
                if identity and isinstance(identity, str) and len(identity) >= 2:
                    # Check if chapter text contradicts the canonical identity
                    for pattern in _OCCUPATION_PATTERNS:
                        for m_occ in re.finditer(pattern, chapter_text):
                            found_occ = m_occ.group(1)
                            # Check if this refers to the protagonist
                            pre_text = chapter_text[max(0, m_occ.start() - 20):m_occ.start()]
                            if pname in pre_text and found_occ != identity:
                                issues.append({
                                    "type": "ATTRIBUTE_VS_SNAPSHOT",
                                    "location": f"第{m_occ.start()}字",
                                    "description": (
                                        f"角色「{pname}」档案身份为「{identity}」，"
                                        f"但章内描述为「{found_occ}」"
                                    ),
                                    "severity": "high",
                                })

    status = "issues_found" if issues else "pass"
    return {"l3_precheck": status, "l3_issues": issues}


# ---------------------------------------------------------------------------
# Combined entry point
# ---------------------------------------------------------------------------

def run_precheck(
    chapter_text: str,
    character_snapshot: dict | list | None = None,
) -> dict[str, Any]:
    """Run both L1 and L3 pre-checks, return combined results."""
    l1 = precheck_arithmetic(chapter_text)
    l3 = precheck_attributes(chapter_text, character_snapshot)
    return {**l1, **l3}


def main() -> None:
    parser = argparse.ArgumentParser(description="Logic-checker 计算型预检")
    parser.add_argument("--chapter-text", required=True, help="Path to chapter text file")
    parser.add_argument("--character-snapshot", help="JSON string of character snapshot data")
    parser.add_argument("--bundle", help="Path to review bundle JSON (extracts snapshot automatically)")
    args = parser.parse_args()

    text_path = Path(args.chapter_text)
    if not text_path.exists():
        print(json.dumps({"error": f"File not found: {text_path}"}, ensure_ascii=False))
        sys.exit(1)

    chapter_text = text_path.read_text(encoding="utf-8")

    character_snapshot = None
    if args.bundle:
        bundle_path = Path(args.bundle)
        if bundle_path.exists():
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            # Build combined snapshot from bundle
            character_snapshot = {
                "protagonist_snapshot": (bundle.get("core_context") or {}).get("protagonist_snapshot", {}),
                "appearing_characters": (bundle.get("scene_context") or {}).get("appearing_characters", []),
            }
    elif args.character_snapshot:
        character_snapshot = json.loads(args.character_snapshot)

    result = run_precheck(chapter_text, character_snapshot)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
