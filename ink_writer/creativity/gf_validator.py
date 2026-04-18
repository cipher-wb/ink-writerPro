"""v16 US-010：金手指三重硬约束校验器。

参考 ``ink-writer/skills/ink-init/references/creativity/golden-finger-rules.md``：
- **GF-1** 非战力维度：dimension ∈ 8 类白名单；整体文本命中 20+ 禁用词 → HARD。
- **GF-2** 代价可视化：cost 字段必须同时满足 **可量化 + 可被反派利用 + 前 10 章可见**。
- **GF-3** 一句话爆点：one_liner ≤ 20 字 + 含具体动作/代价 + 含反直觉信号（但/除了/只/反而/必须/…）。

设计要点
--------
1. ``validate_golden_finger(gf_spec: dict) -> ValidationResult``：每条违规 severity=HARD；
   ``passed=True`` 当且仅当三重全过。调用方（retry_loop）另行判 2/3 阈值。
2. ``gf_spec`` 约定字段：``dimension`` / ``cost`` / ``one_liner``；允许多余字段，
   缺失 → 该项直接 HARD 标记 "missing"。
3. 所有检测纯 Python；无 LLM、无外网。
4. 与 ``name_validator`` 共用 ``Severity / Violation / ValidationResult`` 三元组。
"""

from __future__ import annotations

import re
from typing import Optional

from ink_writer.creativity.name_validator import (
    Severity,
    ValidationResult,
    Violation,
)

# ───────────────────────────── GF-1 ─────────────────────────────

# 8 类非战力维度白名单（严格字符串匹配或包含）。
VALID_DIMENSIONS: frozenset[str] = frozenset({
    "信息",
    "时间",
    "情感",
    "社交",
    "认知",
    "概率",
    "感知",
    "规则",
})

# 金手指禁止词（≥20，来自 golden-finger-rules.md §禁止词列表）。
BANNED_WORDS: tuple[str, ...] = (
    "修为暴涨",
    "无限金币",
    "系统签到",
    "作弊器",
    "外挂",
    "无限奖励",
    "吞噬天赋",
    "觉醒面板",
    "签到一万年",
    "熟练度+1",
    "属性+1",
    "经验值",
    "抽卡",
    "抽奖池",
    "每日任务奖励",
    "老爷爷传功",
    "万倍返还",
    "充值变强",
    "资源无限",
    "境界飞升",
    "丹药爆仓",
    "灵石自动产出",
    # 扩展：面板属性 / 纯战斗力倍率 / 修为暴涨等同义词
    "面板属性",
    "战斗力倍率",
)


# ───────────────────────────── GF-2 ─────────────────────────────

# 代价"可量化"信号：含数字 + 时长/次数单位。
_QUANTIFY_RE = re.compile(
    r"(\d+\s*(?:年|月|日|天|小时|分钟|秒|次|岁|倍|米|%|‰|点|章|页|枚|条)"
    r"|半(?:年|月|天|小时)"
    r"|(?:每|限)\s*\d+)"
)

# 反派可利用：关键词集合。
_ADVERSARY_KEYWORDS: tuple[str, ...] = (
    "反派",
    "对手",
    "定位",
    "暴露",
    "被追踪",
    "被监听",
    "被反噬",
    "被看见",
    "被同步",
    "血脉印记",
    "神级存在",
    "政敌",
    "仇家",
    "敌方",
    "宿敌",
    # 弱形式：任何"被 X"（被动语态）视为潜在可利用
)
_PASSIVE_RE = re.compile(r"被[\u4e00-\u9fff]{1,6}")

# 前 10 章可见：强度词（"立即/当场/每次/第一次"等）+ 显式 "前 N 章" 表述。
_VISIBILITY_KEYWORDS: tuple[str, ...] = (
    "立即",
    "当场",
    "每次",
    "一次",
    "第一次",
    "首次",
    "触发即",
    "开场",
    "前10章",
    "前 10 章",
    "章节内",
    "即刻",
    "瞬间",
    "随即",
)


def _cost_quantifiable(cost: str) -> bool:
    return bool(_QUANTIFY_RE.search(cost))


def _cost_adversary_exploitable(cost: str) -> bool:
    if any(kw in cost for kw in _ADVERSARY_KEYWORDS):
        return True
    return bool(_PASSIVE_RE.search(cost))


def _cost_visible_in_first_10_chapters(cost: str) -> bool:
    return any(kw in cost for kw in _VISIBILITY_KEYWORDS)


# ───────────────────────────── GF-3 ─────────────────────────────

GF3_MAX_CHARS: int = 20

# 反直觉信号：转折 / 限定 / 例外 / 付出。
_COUNTERINTUITIVE_MARKERS: tuple[str, ...] = (
    "但",
    "除了",
    "只",
    "反而",
    "必须",
    "却",
    "连",
    "即使",
    "即便",
    "可",
    "不过",
    "要先",
    "代价",
    "扣减",
    "失去",
    "付出",
    "换取",
    "换",
    "代",
    "倒",
    "忘记",
    "失忆",
    "一次",
)

# 具体动作/代价词（金手指动作性信号）。
_ACTION_MARKERS: tuple[str, ...] = (
    "听见",
    "看见",
    "读",
    "说",
    "杀",
    "偷",
    "签",
    "写",
    "梦见",
    "倒流",
    "回溯",
    "复现",
    "哭",
    "送",
    "换",
    "忘",
    "触发",
    "改写",
    "注视",
    "吻",
    "取",
    "换走",
    "掠夺",
)


def _gf3_counts_chars(text: str) -> int:
    """统计"字数"：对中文按字符；英文字母按 0.5（向上取整），数字算 1 字符。

    Quick Mode 口径里"字数"默认是中文字符数；英文混写按 2 字母 = 1 字。
    """
    chars = 0
    eng_run = 0

    def flush_eng() -> int:
        # 2 个英文字母 = 1 字
        return (eng_run + 1) // 2

    for ch in text:
        if re.match(r"[A-Za-z]", ch):
            eng_run += 1
            continue
        # 非英文字母：先把累积英文 flush
        chars += flush_eng()
        eng_run = 0
        if ch.isspace() or ch in "，。！？；：、、,.;:!?\"'“”‘’（）()《》「」":
            continue
        chars += 1
    chars += flush_eng()
    return chars


def _gf3_has_action(text: str) -> bool:
    return any(m in text for m in _ACTION_MARKERS)


def _gf3_has_counterintuitive(text: str) -> bool:
    return any(m in text for m in _COUNTERINTUITIVE_MARKERS)


# ───────────────────────────── Main API ─────────────────────────────


def validate_golden_finger(
    gf_spec: dict,
    *,
    banned_words: Optional[tuple[str, ...]] = None,
) -> ValidationResult:
    """验证金手指三重硬约束。

    Args:
        gf_spec: dict with keys ``dimension`` / ``cost`` / ``one_liner``。
            其它字段忽略；缺失字段视为空串并 HARD fail 对应 GF 项。
        banned_words: 测试注入的自定义禁用词；默认用 ``BANNED_WORDS``。

    Returns:
        ValidationResult。``passed=True`` 仅当 GF-1 + GF-2 + GF-3 三项全过。
        每条违规 severity=HARD，id 形如 ``GF1_*`` / ``GF2_*`` / ``GF3_*``。
    """
    if banned_words is None:
        banned_words = BANNED_WORDS

    violations: list[Violation] = []
    suggestions: list[str] = []

    dimension = (gf_spec.get("dimension") or "").strip()
    cost = (gf_spec.get("cost") or "").strip()
    one_liner = (gf_spec.get("one_liner") or "").strip()
    # 整合文本用于全局禁用词扫描
    all_text = " ".join(str(v) for v in gf_spec.values() if isinstance(v, str))

    # ---------- GF-1 ----------
    if not dimension:
        violations.append(
            Violation(
                id="GF1_MISSING_DIMENSION",
                severity=Severity.HARD,
                description="gf_spec 缺少 dimension 字段或为空。",
            )
        )
        suggestions.append("补齐 dimension（8 类非战力维度之一）。")
    else:
        matched = None
        for v in VALID_DIMENSIONS:
            if v in dimension:
                matched = v
                break
        if matched is None:
            violations.append(
                Violation(
                    id="GF1_DIMENSION_NOT_IN_WHITELIST",
                    severity=Severity.HARD,
                    description=(
                        f"dimension「{dimension}」不在 8 类非战力维度白名单内"
                        f"（{sorted(VALID_DIMENSIONS)}）。"
                    ),
                    matched_token=dimension,
                )
            )
            suggestions.append("改选 信息/时间/情感/社交/认知/概率/感知/规则 之一。")

    for bw in banned_words:
        if bw and bw in all_text:
            violations.append(
                Violation(
                    id="GF1_BANNED_WORD",
                    severity=Severity.HARD,
                    description=f"金手指描述命中禁用词「{bw}」。",
                    matched_token=bw,
                )
            )
            suggestions.append(f"删除陈词「{bw}」，改写为非战力维度表述。")

    # ---------- GF-2 ----------
    if not cost:
        violations.append(
            Violation(
                id="GF2_MISSING_COST",
                severity=Severity.HARD,
                description="gf_spec 缺少 cost 字段或为空。",
            )
        )
        suggestions.append("补齐 cost（可量化 + 可被反派利用 + 前 10 章可见）。")
    else:
        q = _cost_quantifiable(cost)
        a = _cost_adversary_exploitable(cost)
        v_ = _cost_visible_in_first_10_chapters(cost)

        if not q:
            violations.append(
                Violation(
                    id="GF2_COST_NOT_QUANTIFIABLE",
                    severity=Severity.HARD,
                    description=(
                        "cost 描述缺少可量化信号（数字 + 单位：年/次/秒/倍/米等）。"
                    ),
                )
            )
            suggestions.append("给 cost 加具体数字 + 时长/次数单位。")
        if not a:
            violations.append(
                Violation(
                    id="GF2_COST_NOT_ADVERSARY_EXPLOITABLE",
                    severity=Severity.HARD,
                    description=(
                        "cost 描述不体现反派/对手可利用性（被定位/被反噬/被追踪 等）。"
                    ),
                )
            )
            suggestions.append("写明代价如何能被敌方捕捉或反利用。")
        if not v_:
            violations.append(
                Violation(
                    id="GF2_COST_NOT_VISIBLE_EARLY",
                    severity=Severity.HARD,
                    description=(
                        "cost 描述未体现 '前 10 章可见' 的即时性（立即/当场/每次/触发即）。"
                    ),
                )
            )
            suggestions.append("让代价在开场/首次使用即触发，便于读者前 10 章感知。")

    # ---------- GF-3 ----------
    if not one_liner:
        violations.append(
            Violation(
                id="GF3_MISSING_ONE_LINER",
                severity=Severity.HARD,
                description="gf_spec 缺少 one_liner 字段或为空。",
            )
        )
        suggestions.append("补齐 one_liner（≤20 字，含动作/代价 + 反直觉信号）。")
    else:
        length = _gf3_counts_chars(one_liner)
        if length > GF3_MAX_CHARS:
            violations.append(
                Violation(
                    id="GF3_OVER_LENGTH",
                    severity=Severity.HARD,
                    description=f"one_liner 字数 {length} > {GF3_MAX_CHARS} 字上限。",
                )
            )
            suggestions.append("精简 one_liner，保留动作 + 代价 + 反直觉三要素。")
        if not _gf3_has_action(one_liner):
            violations.append(
                Violation(
                    id="GF3_NO_ACTION",
                    severity=Severity.HARD,
                    description="one_liner 缺少具体动作/代价动词（如听见/回溯/签下 等）。",
                )
            )
            suggestions.append("加一个具体动作/代价动词（动作→反馈）。")
        if not _gf3_has_counterintuitive(one_liner):
            violations.append(
                Violation(
                    id="GF3_NO_COUNTERINTUITIVE",
                    severity=Severity.HARD,
                    description="one_liner 缺少反直觉信号（但/除了/必须/代价/换取 等）。",
                )
            )
            suggestions.append("加一个反直觉转折（但/除了/只/必须/换/代价）。")

    passed = not any(v.severity == Severity.HARD for v in violations)
    return ValidationResult(
        passed=passed,
        violations=violations,
        suggestion="；".join(suggestions),
    )


__all__ = [
    "BANNED_WORDS",
    "VALID_DIMENSIONS",
    "GF3_MAX_CHARS",
    "validate_golden_finger",
]
