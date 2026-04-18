"""v16 US-011：L0-L3 敏感词密度校验器。

规则来自 ``ink-writer/skills/ink-init/references/creativity/style-voice-levels.md``：

- **L0** 中性俚语：V1/V2/V3 全档允许。
- **L1** 轻度粗口：仅 V2/V3 允许；V1 命中即 HARD。
- **L2** 擦边暗示：仅 V3 + aggression ∈ {3,4} 允许；其它情况命中即 HARD。
- **L3** 红线：全档禁用；命中任一条即 HARD，附带 matched_token。

密度矩阵（``aggression`` 档位 → 上限占比）：
- 档位 1 保守：总粗口密度 0%（零容忍）。
- 档位 2 平衡：≈0.2%。
- 档位 3 激进：0.8%（取 0.5-0.8 区间上限）。
- 档位 4 疯批：1.5%。

密度计算口径：matched_chars / total_chars（章内全部字符数，含中英标点）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ink_writer.creativity.name_validator import (
    Severity,
    ValidationResult,
    Violation,
)


# ───────────────────────── 常量与路径 ─────────────────────────

VALID_VOICES: frozenset[str] = frozenset({"V1", "V2", "V3"})
VALID_AGGRESSION_LEVELS: frozenset[int] = frozenset({1, 2, 3, 4})

# aggression → 总密度上限（占比 0-1）
_TOTAL_DENSITY_CAPS: dict[int, float] = {
    1: 0.0,
    2: 0.002,
    3: 0.008,
    4: 0.015,
}

# 各档位下各 level 的允许组合（aggression, voice） → True 表示允许。
# 该矩阵与 style-voice-levels.md §三密度矩阵对齐。
_LEVEL_ALLOWED: dict[tuple[int, str, str], bool] = {}
# 默认全部禁止
for agg in VALID_AGGRESSION_LEVELS:
    for voice in VALID_VOICES:
        for level in ("L0", "L1", "L2"):
            _LEVEL_ALLOWED[(agg, voice, level)] = False
# L0 除档位 1 外全档允许
for agg in (2, 3, 4):
    for voice in VALID_VOICES:
        _LEVEL_ALLOWED[(agg, voice, "L0")] = True
# L1：V2/V3 + 档位 2/3/4 允许（档位 1 零容忍）
for agg in (2, 3, 4):
    for voice in ("V2", "V3"):
        _LEVEL_ALLOWED[(agg, voice, "L1")] = True
# L2：仅 V3 + 档位 3/4 允许
for agg in (3, 4):
    _LEVEL_ALLOWED[(agg, "V3", "L2")] = True

# lexicon 默认路径（仓库根 = parents[2]）
_DEFAULT_LEXICON_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "sensitive_lexicon.json"
)
_LEXICON_CACHE: Optional[dict] = None


def _load_lexicon(path: Optional[Path] = None) -> dict:
    global _LEXICON_CACHE
    if path is not None:
        return json.loads(path.read_text(encoding="utf-8"))
    if _LEXICON_CACHE is None:
        if _DEFAULT_LEXICON_PATH.exists():
            _LEXICON_CACHE = json.loads(
                _DEFAULT_LEXICON_PATH.read_text(encoding="utf-8")
            )
        else:
            _LEXICON_CACHE = {"L0": [], "L1": [], "L2": [], "L3": []}
    return _LEXICON_CACHE


def reset_cache() -> None:
    global _LEXICON_CACHE
    _LEXICON_CACHE = None


# ───────────────────────── 扫描结果 dataclass ─────────────────────────


@dataclass
class LevelScan:
    """单 level 扫描结果。"""
    level: str
    matched_tokens: list[str] = field(default_factory=list)
    matched_chars: int = 0

    def density(self, total_chars: int) -> float:
        if total_chars <= 0:
            return 0.0
        return self.matched_chars / total_chars

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "matched_tokens": list(self.matched_tokens),
            "matched_chars": self.matched_chars,
        }


# ───────────────────────── 核心 API ─────────────────────────


def _scan_level(text: str, tokens: list[str], level: str) -> LevelScan:
    scan = LevelScan(level=level)
    # 简化：按 token 子串出现次数扫描（不回避重叠，足够用来近似密度）。
    for tok in tokens:
        if not tok:
            continue
        if tok in text:
            count = text.count(tok)
            scan.matched_tokens.append(tok)
            scan.matched_chars += count * len(tok)
    return scan


def validate_density(
    text: str,
    voice: str,
    aggression: int,
    *,
    lexicon_path: Optional[Path] = None,
) -> ValidationResult:
    """按密度矩阵 + voice/aggression 约束校验文本。

    Args:
        text: 章节正文文本。
        voice: ``"V1"`` / ``"V2"`` / ``"V3"``。
        aggression: 1 / 2 / 3 / 4。
        lexicon_path: 测试注入。

    Returns:
        ValidationResult，``passed=True`` 当且仅当：
        - L3 未命中任何 token；
        - L2 / L1 在对应 voice+aggression 允许组合内；
        - 总密度 ≤ 对应 aggression 上限。
    """
    violations: list[Violation] = []
    suggestions: list[str] = []

    # ---- 参数校验 ----
    if voice not in VALID_VOICES:
        violations.append(
            Violation(
                id="LEX_INVALID_VOICE",
                severity=Severity.HARD,
                description=(
                    f"voice「{voice}」非法，必须 ∈ {sorted(VALID_VOICES)}。"
                ),
            )
        )
    if aggression not in VALID_AGGRESSION_LEVELS:
        violations.append(
            Violation(
                id="LEX_INVALID_AGGRESSION",
                severity=Severity.HARD,
                description=(
                    f"aggression「{aggression}」非法，必须 ∈ "
                    f"{sorted(VALID_AGGRESSION_LEVELS)}。"
                ),
            )
        )
    if violations:
        return ValidationResult(
            passed=False, violations=violations,
            suggestion="修正 voice/aggression 后重试。",
        )

    data = _load_lexicon(lexicon_path)
    total_chars = len(text)

    l3_scan = _scan_level(text, data.get("L3", []), "L3")
    l2_scan = _scan_level(text, data.get("L2", []), "L2")
    l1_scan = _scan_level(text, data.get("L1", []), "L1")
    l0_scan = _scan_level(text, data.get("L0", []), "L0")

    # ---- L3 全档禁用 ----
    if l3_scan.matched_tokens:
        for tok in l3_scan.matched_tokens:
            violations.append(
                Violation(
                    id="LEX_L3_RED_LINE",
                    severity=Severity.HARD,
                    description=(
                        f"章节命中 L3 红线词「{tok}」，必须整章重写（不做替换）。"
                    ),
                    matched_token=tok,
                )
            )
        suggestions.append("删除 L3 红线词，整方案重写。")

    # ---- L2 voice/aggression 约束 ----
    if l2_scan.matched_tokens and not _LEVEL_ALLOWED.get(
        (aggression, voice, "L2"), False
    ):
        violations.append(
            Violation(
                id="LEX_L2_NOT_ALLOWED_IN_VOICE",
                severity=Severity.HARD,
                description=(
                    f"L2 擦边词命中（{l2_scan.matched_tokens[:3]}…），"
                    f"但当前 voice={voice}/aggression={aggression} 组合不允许（仅 V3+档位≥3）。"
                ),
                matched_token=l2_scan.matched_tokens[0],
            )
        )
        suggestions.append(
            "删除 L2 擦边词或切到 V3 + 激进档位（3/4）。"
        )

    # ---- L1 voice 约束 ----
    if l1_scan.matched_tokens and not _LEVEL_ALLOWED.get(
        (aggression, voice, "L1"), False
    ):
        violations.append(
            Violation(
                id="LEX_L1_NOT_ALLOWED_IN_VOICE",
                severity=Severity.HARD,
                description=(
                    f"L1 轻度粗口命中（{l1_scan.matched_tokens[:3]}…），"
                    f"但当前 voice={voice}/aggression={aggression} 组合不允许。"
                ),
                matched_token=l1_scan.matched_tokens[0],
            )
        )
        suggestions.append("替换 L1 粗口为 L0 俚语或切到 V2/V3 + 档位≥2。")

    # ---- L0 档位 1 零容忍 ----
    if l0_scan.matched_tokens and not _LEVEL_ALLOWED.get(
        (aggression, voice, "L0"), False
    ):
        violations.append(
            Violation(
                id="LEX_L0_NOT_ALLOWED_IN_LEVEL_1",
                severity=Severity.HARD,
                description=(
                    f"档位 1 保守禁止任何俚语/粗口，L0 命中"
                    f"（{l0_scan.matched_tokens[:3]}…）。"
                ),
                matched_token=l0_scan.matched_tokens[0],
            )
        )
        suggestions.append("档位 1 零容忍：删除 L0 俚语或升到档位 2+。")

    # ---- 总密度上限 ----
    total_matched_chars = (
        l0_scan.matched_chars
        + l1_scan.matched_chars
        + l2_scan.matched_chars
    )
    cap = _TOTAL_DENSITY_CAPS[aggression]
    density = total_matched_chars / total_chars if total_chars > 0 else 0.0
    if density > cap:
        violations.append(
            Violation(
                id="LEX_DENSITY_OVER_CAP",
                severity=Severity.HARD,
                description=(
                    f"总粗口密度 {density:.4f}（L0+L1+L2 共 {total_matched_chars} 字）"
                    f"超过档位 {aggression} 上限 {cap:.4f}。"
                ),
            )
        )
        suggestions.append(
            f"将总粗口密度降到 {cap*100:.2f}% 以内；建议先稀释 L1/L2 再考虑 L0。"
        )

    passed = not any(v.severity == Severity.HARD for v in violations)
    return ValidationResult(
        passed=passed,
        violations=violations,
        suggestion="；".join(suggestions),
    )


__all__ = [
    "VALID_VOICES",
    "VALID_AGGRESSION_LEVELS",
    "LevelScan",
    "validate_density",
    "reset_cache",
]
