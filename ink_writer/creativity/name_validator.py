"""v16 US-009：书名 + 人名陈词黑名单校验器。

数据源：``data/naming/blacklist.json``：
- ``male`` / ``female``：网文通俗主角人名黑名单（完整 2-3 字名字）。
- ``name_combo_ban``：
  - ``surname_tokens``：高频主角姓氏。
  - ``given_suffix_tokens``：高频主角名末字。
  - ``combo_policy``：任何 {surname} + * + {suffix} 或 {surname} + {suffix} 直接判定命中。
- ``book_title_prefix_ban.tokens`` / ``book_title_suffix_ban.tokens``：书名陈词前后缀。

设计要点
--------
1. **数据延迟加载 + 模块级单例缓存**：首次调用时读一次 json，后续 O(1) 命中。
2. **hard 必须重抽 / soft 警告**：hard 违反让 Quick Mode 重抽方案；soft 只作提示。
3. **所有校验纯 Python 无 LLM**：可跨 session 复现、零 token 成本。
4. **不假设书名/人名语言**：非中文串直接 PASS（不误杀外文拼音角色）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class Severity(str, Enum):
    HARD = "hard"  # 必须重抽
    SOFT = "soft"  # 警告但可放行


@dataclass
class Violation:
    """单条违规记录。"""
    id: str
    severity: Severity
    description: str
    matched_token: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity.value,
            "description": self.description,
            "matched_token": self.matched_token,
        }


@dataclass
class ValidationResult:
    """校验结果。``passed`` 当且仅当没有任一 hard 违规。"""
    passed: bool
    violations: list[Violation] = field(default_factory=list)
    suggestion: str = ""

    @property
    def hard_violations(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == Severity.HARD]

    @property
    def soft_violations(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == Severity.SOFT]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "suggestion": self.suggestion,
        }


# ───────────────────────────── 数据加载 ─────────────────────────────

# ink_writer/creativity/name_validator.py → parents[2] = 仓库根。
_DEFAULT_BLACKLIST_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "naming" / "blacklist.json"
)
_BLACKLIST_CACHE: Optional[dict] = None


def _load_blacklist(path: Optional[Path] = None) -> dict:
    """加载黑名单 JSON；模块级单例缓存，可用 ``path`` 在测试里覆盖。"""
    global _BLACKLIST_CACHE
    if path is not None:
        # 显式覆盖不写缓存，避免污染全局
        return json.loads(path.read_text(encoding="utf-8"))
    if _BLACKLIST_CACHE is None:
        if _DEFAULT_BLACKLIST_PATH.exists():
            _BLACKLIST_CACHE = json.loads(
                _DEFAULT_BLACKLIST_PATH.read_text(encoding="utf-8")
            )
        else:
            _BLACKLIST_CACHE = {}
    return _BLACKLIST_CACHE


def reset_cache() -> None:
    """测试辅助：重置模块级缓存。"""
    global _BLACKLIST_CACHE
    _BLACKLIST_CACHE = None


# ───────────────────────── 书名校验 ─────────────────────────


def validate_book_title(
    title: str,
    *,
    blacklist_path: Optional[Path] = None,
) -> ValidationResult:
    """校验书名是否触犯陈词黑名单。

    规则：
    - 书名**以**任意 ``book_title_suffix_ban.tokens`` **结尾** → HARD。
    - 书名**以**任意 ``book_title_prefix_ban.tokens`` **开头** → HARD。
    - 空书名 / 纯空白 → HARD（另一类违规，便于工作流层快速识别）。

    ``suggestion`` 会附上替换方向提示，供 Quick Mode LLM 重抽时参考。
    """
    violations: list[Violation] = []
    suggestions: list[str] = []

    title_stripped = (title or "").strip()
    if not title_stripped:
        violations.append(
            Violation(
                id="BOOK_TITLE_EMPTY",
                severity=Severity.HARD,
                description="书名为空或仅含空白字符。",
            )
        )
        return ValidationResult(
            passed=False,
            violations=violations,
            suggestion="请重新抽取一个非空书名。",
        )

    data = _load_blacklist(blacklist_path)
    prefix_tokens: list[str] = (data.get("book_title_prefix_ban") or {}).get("tokens", [])
    suffix_tokens: list[str] = (data.get("book_title_suffix_ban") or {}).get("tokens", [])

    for tok in prefix_tokens:
        if tok and title_stripped.startswith(tok):
            violations.append(
                Violation(
                    id="BOOK_TITLE_PREFIX_BAN",
                    severity=Severity.HARD,
                    description=f"书名以陈词前缀「{tok}」开头",
                    matched_token=tok,
                )
            )
            suggestions.append(f"改写书名开头「{tok}」，改用具象动作/意象。")

    for tok in suffix_tokens:
        if tok and title_stripped.endswith(tok):
            violations.append(
                Violation(
                    id="BOOK_TITLE_SUFFIX_BAN",
                    severity=Severity.HARD,
                    description=f"书名以陈词后缀「{tok}」结尾",
                    matched_token=tok,
                )
            )
            suggestions.append(f"改写书名末尾「{tok}」，改用非战力标签/反讽/具象物象。")

    passed = not any(v.severity == Severity.HARD for v in violations)
    return ValidationResult(
        passed=passed,
        violations=violations,
        suggestion="；".join(suggestions),
    )


# ───────────────────────── 人名校验 ─────────────────────────


def _char_in_tokens(text: str, tokens: list[str]) -> Optional[str]:
    """返回 ``text`` 中首个命中的 token，未命中返回 None。"""
    for t in tokens:
        if t and t in text:
            return t
    return None


def validate_character_name(
    name: str,
    role: str = "main",
    *,
    blacklist_path: Optional[Path] = None,
) -> ValidationResult:
    """校验角色名是否触犯陈词黑名单。

    参数：
        name: 完整角色名（中文），如「萧尘」。
        role: ``"main"``（主角）/``"side"``（配角）。
            - main：combo_ban 触发 → HARD；
            - side：combo_ban 触发 → SOFT（允许偶发重复，但仍警告）。
        blacklist_path: 测试注入。

    规则：
    - 空名或纯空白 → HARD。
    - ``name`` 完全等于 ``male`` / ``female`` 黑名单条目 → HARD。
    - ``name`` 满足 surname × given_suffix 组合（首字 ∈ surname_tokens
      且末字 ∈ given_suffix_tokens）→ 按 role 判 HARD / SOFT。
    """
    violations: list[Violation] = []
    suggestions: list[str] = []

    name_stripped = (name or "").strip()
    if not name_stripped:
        violations.append(
            Violation(
                id="NAME_EMPTY",
                severity=Severity.HARD,
                description="角色名为空或仅含空白字符。",
            )
        )
        return ValidationResult(
            passed=False, violations=violations, suggestion="请重新抽取一个非空角色名。"
        )

    data = _load_blacklist(blacklist_path)
    male: list[str] = data.get("male", []) or []
    female: list[str] = data.get("female", []) or []
    combo = data.get("name_combo_ban", {}) or {}
    surname_tokens: list[str] = combo.get("surname_tokens", []) or []
    given_suffix_tokens: list[str] = combo.get("given_suffix_tokens", []) or []

    # 1) 完整命中 male / female 黑名单
    if name_stripped in male:
        violations.append(
            Violation(
                id="NAME_MALE_BAN",
                severity=Severity.HARD,
                description=f"角色名「{name_stripped}」命中 male 通俗名黑名单",
                matched_token=name_stripped,
            )
        )
        suggestions.append("换一个非 '叶辰/林默/萧寒' 系的姓名组合。")
    if name_stripped in female:
        violations.append(
            Violation(
                id="NAME_FEMALE_BAN",
                severity=Severity.HARD,
                description=f"角色名「{name_stripped}」命中 female 通俗名黑名单",
                matched_token=name_stripped,
            )
        )
        suggestions.append("换一个非 '苏婉清/沈清月/顾念' 系的姓名组合。")

    # 2) combo_ban：首字 ∈ surname_tokens 且末字 ∈ given_suffix_tokens
    if len(name_stripped) >= 2:
        first, last = name_stripped[0], name_stripped[-1]
        if first in surname_tokens and last in given_suffix_tokens:
            severity = Severity.HARD if role == "main" else Severity.SOFT
            violations.append(
                Violation(
                    id="NAME_COMBO_BAN",
                    severity=severity,
                    description=(
                        f"角色名「{name_stripped}」触发 surname×given_suffix 组合禁用"
                        f"（姓'{first}' × 名末'{last}'），role={role}"
                    ),
                    matched_token=f"{first}+{last}",
                )
            )
            suggestions.append(
                f"避免「{first}*{last}」模板，换一个非 surname_tokens 的姓 或 非 given_suffix_tokens 的末字。"
            )

    passed = not any(v.severity == Severity.HARD for v in violations)
    return ValidationResult(
        passed=passed,
        violations=violations,
        suggestion="；".join(suggestions),
    )


__all__ = [
    "Severity",
    "Violation",
    "ValidationResult",
    "validate_book_title",
    "validate_character_name",
    "reset_cache",
]
