"""v26 US-014：金手指代价池校验器（GF-2 v2.0 + GF-4 + GF-5）。

参考 ``ink-writer/skills/ink-init/references/creativity/golden-finger-rules.md`` v2.0：

- **GF-2 v2.0** 代价池强制抽样：``main_cost`` + ``side_costs`` 必须从
  ``data/golden-finger-cost-pool.json`` 抽取，受 trope_freq / rarity / 跨大类配额硬约束。
- **GF-4** 反同源闭环：金手指 ``dimension`` 不得与 ``main_cost.dimension_taboo`` 同源；
  例外触发时需 ``gf4_exception_note ≥ 50 字``。
- **GF-5** 阶梯轴 T1-T4：``escalation_ladder`` 三阶段（ch1 / ch10 / late_game）必填，
  tier 严格递增，每阶段 ``scene_anchor ≥ 30 字``。

设计要点
--------
1. ``validate_cost_selection(gf_spec, pool=None)`` —— 主入口；缺省自动加载 cost-pool。
2. 所有违规 severity=HARD；``passed=True`` 仅当 GF-2 + GF-4 + GF-5 三项全过。
3. 与 ``gf_validator.validate_golden_finger`` 互补：那个跑 GF-1/GF-3，本模块跑
   GF-2(v2)/GF-4/GF-5。CLI 通过 ``--check-cost`` 开关按需启用 v2.0 模式。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from ink_writer.creativity.name_validator import (
    Severity,
    ValidationResult,
    Violation,
)


# ───────────────────────── 常量 ─────────────────────────

# trope_freq=high 中位数趋同区黑名单 — 不得作为唯一主代价。
# 编号同步自 data/golden-finger-cost-pool.json v1.0。
HIGH_FREQ_BLACKLIST_AS_MAIN: frozenset[str] = frozenset({
    "C02-MEM-016",  # 记忆/通用
    "C01-CON-001",  # 寿命削减
    "C04-RES-057",  # 灵石燃烧
    "C06-CD-076",   # 冷却/长冷
    "C06-CD-077",   # 冷却/单日单次
})

# Tier 等级排序（用于阶梯递增校验）。
TIER_RANK: dict[str, int] = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}

# cost-pool.json 自动查找路径（由近到远）。
_DEFAULT_LOOKUP_PATHS: tuple[Path, ...] = (
    Path(__file__).resolve().parents[2] / "data" / "golden-finger-cost-pool.json",
    Path.cwd() / "data" / "golden-finger-cost-pool.json",
)


# ───────────────────────── 加载 ─────────────────────────

def _resolve_pool_path(custom: Optional[Path] = None) -> Path:
    if custom and Path(custom).exists():
        return Path(custom)
    for p in _DEFAULT_LOOKUP_PATHS:
        if p.exists():
            return p
    raise FileNotFoundError(
        "cost-pool.json not found. Searched: "
        + ", ".join(str(p) for p in _DEFAULT_LOOKUP_PATHS)
    )


@lru_cache(maxsize=4)
def _load_cached(path_str: str) -> dict[str, dict]:
    raw = json.loads(Path(path_str).read_text(encoding="utf-8"))
    return {c["cost_id"]: c for c in raw["costs"]}


def load_cost_pool(path: Optional[Path] = None) -> dict[str, dict]:
    """加载 cost-pool.json 并返回 {cost_id → cost_obj} 字典。"""
    resolved = _resolve_pool_path(path)
    return _load_cached(str(resolved))


# ───────────────────────── 主校验 ─────────────────────────

def validate_cost_selection(
    gf_spec: dict,
    pool: Optional[dict[str, dict]] = None,
) -> ValidationResult:
    """校验金手指 v2.0 代价选择（GF-2 + GF-4 + GF-5）。

    Args:
        gf_spec: dict with keys::

            {
              "dimension": "感知",
              "main_cost": {"cost_id": "C03-FOR-037", "tier_target": "T2", "value": "..."},
              "side_costs": [
                {"cost_id": "C07-EXP-091", "tier_target": "T1"},
                {"cost_id": "C08-FAU-110", "tier_target": "T1"}
              ],
              "escalation_ladder": {
                "ch1":       {"main_cost_tier": "T1", "side_cost_tiers": ["T1","T1"], "scene_anchor": "..."},
                "ch10":      {"main_cost_tier": "T2", "side_cost_tiers": ["T2","T1"], "scene_anchor": "..."},
                "late_game": {"main_cost_tier": "T3", "side_cost_tiers": ["T3","T2"], "scene_anchor": "..."}
              },
              "gf4_exception_note": "（可选）刻意同源闭环时的剧情兑现路径"
            }

        pool: cost-pool 字典；缺省自动加载。

    Returns:
        ValidationResult。passed=True 仅当 GF-2 + GF-4 + GF-5 全部通过。
    """
    if pool is None:
        pool = load_cost_pool()

    violations: list[Violation] = []
    suggestions: list[str] = []

    main_cost = gf_spec.get("main_cost") or {}
    side_costs = gf_spec.get("side_costs") or []
    dimension = (gf_spec.get("dimension") or "").strip()
    ladder = gf_spec.get("escalation_ladder") or {}

    # ─── GF-2: 主代价校验 ───
    main_id = main_cost.get("cost_id")
    if not main_id or main_id not in pool:
        violations.append(Violation(
            id="GF2_MAIN_NOT_IN_POOL",
            severity=Severity.HARD,
            description=f"main_cost.cost_id={main_id!r} 未在 cost-pool 中（必须从 data/golden-finger-cost-pool.json 抽）",
        ))
        suggestions.append("从 cost-pool.json 选 1 条 cost_id 填入 main_cost")
        # 主代价缺失时跳过依赖它的后续校验
        return _result(violations, suggestions)

    main_obj = pool[main_id]

    if main_obj["trope_freq"] == "high":
        violations.append(Violation(
            id="GF2_MAIN_IS_HIGH_FREQ",
            severity=Severity.HARD,
            description=f"main_cost {main_id} (trope_freq=high) 在中位数趋同区，禁止作为唯一主代价",
            matched_token=main_id,
        ))
        suggestions.append("主代价改选 trope_freq ∈ {low, rare} 的条目")

    if main_obj["rarity"] < 3:
        violations.append(Violation(
            id="GF2_MAIN_RARITY_LOW",
            severity=Severity.HARD,
            description=f"main_cost {main_id} rarity={main_obj['rarity']} < 3",
        ))
        suggestions.append("主代价改选 rarity ≥ 3 的条目")

    if main_id in HIGH_FREQ_BLACKLIST_AS_MAIN:
        violations.append(Violation(
            id="GF2_MAIN_IS_BLACKLISTED",
            severity=Severity.HARD,
            description=f"main_cost {main_id} 命中 high-freq 黑名单，禁止作为主代价",
            matched_token=main_id,
        ))
        suggestions.append("把该 cost 移到 side_costs，并选另一条 low/rare 主代价")

    # ─── GF-2: 副代价校验 ───
    if len(side_costs) != 2:
        violations.append(Violation(
            id="GF2_SIDE_COUNT_INVALID",
            severity=Severity.HARD,
            description=f"side_costs 数量={len(side_costs)}，必须为 2",
        ))
        suggestions.append("从 cost-pool 抽 2 条作为 side_costs")

    side_objs: list[dict] = []
    for i, s in enumerate(side_costs):
        sid = s.get("cost_id") if isinstance(s, dict) else None
        if not sid or sid not in pool:
            violations.append(Violation(
                id="GF2_SIDE_NOT_IN_POOL",
                severity=Severity.HARD,
                description=f"side_costs[{i}].cost_id={sid!r} 未在 cost-pool 中",
            ))
            suggestions.append(f"side_costs[{i}] 改用 cost-pool 中的 cost_id")
        else:
            side_objs.append(pool[sid])

    # 至少 1 条副代价跨大类
    if side_objs:
        main_cat = main_obj["category"]
        cross = any(s["category"] != main_cat for s in side_objs)
        if not cross:
            violations.append(Violation(
                id="GF2_SIDE_NO_CROSS_CATEGORY",
                severity=Severity.HARD,
                description=f"所有副代价均在 main_cost 同大类 {main_cat}，至少需 1 条跨大类（C01-C08）",
            ))
            suggestions.append("把 ≥ 1 条副代价换成不同大类的条目（如 main=C01 时 side 选 C03/C07/C08）")

    # high 配额上限 1/3
    all_costs = [main_obj] + side_objs
    high_count = sum(1 for o in all_costs if o["trope_freq"] == "high")
    if high_count > 1:
        violations.append(Violation(
            id="GF2_HIGH_FREQ_QUOTA_EXCEEDED",
            severity=Severity.HARD,
            description=f"3 条代价里 trope_freq=high 数量={high_count} > 1（配额上限 1/3）",
        ))
        suggestions.append("把多余的 high 代价换成 low/rare/mid")

    # ─── GF-4: 反同源闭环 ───
    if dimension and main_obj.get("dimension_taboo"):
        if dimension in main_obj["dimension_taboo"]:
            exc_note = (gf_spec.get("gf4_exception_note") or "").strip()
            if not exc_note:
                violations.append(Violation(
                    id="GF4_DIMENSION_TABOO_LOOP",
                    severity=Severity.HARD,
                    description=(
                        f"金手指 dimension={dimension!r} 与 main_cost {main_id} 的 "
                        f"dimension_taboo={main_obj['dimension_taboo']} 同源闭环。"
                        "如刻意为之需补 gf4_exception_note ≥ 50 字"
                    ),
                ))
                suggestions.append(
                    "重抽 main_cost 避开 dimension_taboo；或补 gf4_exception_note "
                    "（≥ 50 字，含具体冲突情节）"
                )
            elif len(exc_note) < 50:
                violations.append(Violation(
                    id="GF4_EXCEPTION_NOTE_TOO_SHORT",
                    severity=Severity.HARD,
                    description=f"gf4_exception_note 字数 {len(exc_note)} < 50",
                ))
                suggestions.append("扩写 gf4_exception_note 至 ≥ 50 字（说明同源张力如何成为剧情看点）")

    # ─── GF-5: 阶梯轴 ───
    required_stages = ("ch1", "ch10", "late_game")
    missing = [s for s in required_stages if s not in ladder]
    if missing:
        violations.append(Violation(
            id="GF5_LADDER_MISSING_STAGES",
            severity=Severity.HARD,
            description=f"escalation_ladder 缺少阶段: {missing}",
        ))
        suggestions.append("补齐 ch1 / ch10 / late_game 三阶段")
    else:
        stage_tiers: list[int] = []
        for s in required_stages:
            stage = ladder[s] or {}
            mt = stage.get("main_cost_tier")
            if mt not in TIER_RANK:
                violations.append(Violation(
                    id="GF5_INVALID_TIER",
                    severity=Severity.HARD,
                    description=f"escalation_ladder.{s}.main_cost_tier={mt!r} 不在 T1-T4",
                ))
                suggestions.append(f"{s} 阶段 main_cost_tier 改为 T1/T2/T3/T4 之一")
                stage_tiers.append(0)
            else:
                stage_tiers.append(TIER_RANK[mt])

            anchor = stage.get("scene_anchor", "") or ""
            if len(anchor) < 30:
                violations.append(Violation(
                    id="GF5_SCENE_ANCHOR_TOO_SHORT",
                    severity=Severity.HARD,
                    description=f"escalation_ladder.{s}.scene_anchor 字数 {len(anchor)} < 30",
                ))
                suggestions.append(f"{s}.scene_anchor 扩写至 ≥ 30 字（具体场景描写）")

            sct = stage.get("side_cost_tiers")
            if not isinstance(sct, list) or any(t not in TIER_RANK for t in sct):
                violations.append(Violation(
                    id="GF5_INVALID_SIDE_TIER",
                    severity=Severity.HARD,
                    description=f"escalation_ladder.{s}.side_cost_tiers 含非法 tier: {sct!r}",
                ))
                suggestions.append(f"{s}.side_cost_tiers 全部改为 T1-T4 之一")

        # tier 严格递增
        if 0 not in stage_tiers and stage_tiers != sorted(stage_tiers):
            violations.append(Violation(
                id="GF5_LADDER_NOT_INCREASING",
                severity=Severity.HARD,
                description=(
                    f"escalation_ladder tier 必须递增 (ch1≤ch10≤late_game)；"
                    f"实际: ch1={stage_tiers[0]} / ch10={stage_tiers[1]} / late_game={stage_tiers[2]}"
                ),
            ))
            suggestions.append("调整阶段 tier 让 ch1 ≤ ch10 ≤ late_game")

    return _result(violations, suggestions)


def _result(violations: list[Violation], suggestions: list[str]) -> ValidationResult:
    passed = not any(v.severity == Severity.HARD for v in violations)
    return ValidationResult(
        passed=passed,
        violations=violations,
        suggestion="；".join(suggestions),
    )


__all__ = [
    "HIGH_FREQ_BLACKLIST_AS_MAIN",
    "TIER_RANK",
    "load_cost_pool",
    "validate_cost_selection",
]
