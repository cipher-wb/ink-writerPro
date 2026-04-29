"""US-010: prose-impact / flow-naturalness 阈值微调的激活门控。

US-006 起直白模式全场景激活；所有自动场景下把
"感官丰富度 / 镜头多样性 / 对话比例" 相关的软规则豁免，避免与 directness-checker
+ simplification-pass 的直白目标冲突。

单源语义：激活判定复用
:func:`ink_writer.prose.directness_checker.is_activated` —— 与 writer / polish /
sensory-immersion-checker / directness-checker 对齐。

豁免集合（白名单）只覆盖"镜头多样性 / 感官丰富度 / 对话占比"三类，明确排除：

- ``SHOT_SINGLE_DOMINANCE`` / ``ABSENT_SCENE``（仍保持 hard block）
- ``POV_INTRA_PARAGRAPH`` / ``TABOO_VIOLATION`` / ``CV_CRITICAL``（文笔硬伤）
- proofreading-checker 域的弱动词 / AI 味检测
"""

from __future__ import annotations

from collections.abc import Iterable

from ink_writer.prose.directness_checker import is_activated as _directness_is_activated

PROSE_IMPACT_CHECKER_NAME: str = "prose-impact-checker"
FLOW_NATURALNESS_CHECKER_NAME: str = "flow-naturalness-checker"

# v26.2 平台感知文笔冲击力权重
def get_prose_impact_weights(platform: str) -> dict[str, float]:
    """Return dimension weights for prose-impact-checker per platform."""
    if platform == "fanqie":
        return {
            "lens_diversity": 0.10,
            "sensory_richness": 0.15,
            "sentence_rhythm": 0.20,
            "verb_sharpness": 0.25,
            "env_emotion_resonance": 0.10,
            "closeup_absence": 0.20,
        }
    return {
        "lens_diversity": 0.20,
        "sensory_richness": 0.20,
        "sentence_rhythm": 0.15,
        "verb_sharpness": 0.15,
        "env_emotion_resonance": 0.15,
        "closeup_absence": 0.15,
    }


PROSE_IMPACT_RELAXED_RULES: frozenset[str] = frozenset(
    {
        # 维度1 镜头多样性（战斗/高潮/爽点天然镜头单一，不追求多样性降级）
        "SHOT_MONOTONY",
        "COMBAT_THREE_STAGE_MISSING",
        "SCENE_NO_SWITCH",
        "CLOSEUP_ABSENT",
        # 维度2 感官丰富度（直白模式下 directness-checker 接管，不追求视觉比例/非视觉覆盖）
        "VISUAL_OVERLOAD",
        "NON_VISUAL_SPARSE",
        "SENSORY_PLAN_MISMATCH",
        "SENSORY_DESERT",
    }
)

FLOW_NATURALNESS_RELAXED_RULES: frozenset[str] = frozenset(
    {
        # 维度5 对话黄金比例（直白模式下对话比例常偏离目标区间；与 combat_heavy_chapter 豁免同逻辑）
        "RATIO_DEVIATION",
        "DIALOGUE_STARVATION",
        "DIALOGUE_FLOOD",
        "INNER_MONOLOGUE_BLOAT",
    }
)


def should_relax_prose_impact(
    scene_mode: str | None,
    chapter_no: int = 0,
) -> bool:
    """prose-impact-checker 是否应在本场景下对镜头/感官维度放宽（软豁免）。

    返回 ``True`` 时 :data:`PROSE_IMPACT_RELAXED_RULES` 内的规则代码被 arbitration
    过滤（不升级为 Red），其他维度（句式节奏 / 动词锐度 / 环境情绪 / 特写覆盖）
    保持 v21 行为。US-006 起默认返回 ``True``；仅历史 skip 入口会关闭。
    """
    return _directness_is_activated(scene_mode, int(chapter_no or 0))


def should_relax_flow_naturalness(
    scene_mode: str | None,
    chapter_no: int = 0,
) -> bool:
    """flow-naturalness-checker 是否应在本场景下对对话比例维度放宽。

    返回 ``True`` 时 :data:`FLOW_NATURALNESS_RELAXED_RULES` 内的规则代码被
    arbitration 过滤；其他六维（信息密度 / 融入方式 / 过渡 / 对话辨识 / 语气 /
    voice）保持 v21 行为。
    """
    return _directness_is_activated(scene_mode, int(chapter_no or 0))


def is_relaxed_issue(
    checker_name: str,
    rule_code: str | None,
    *,
    relax_prose_impact: bool,
    relax_flow_naturalness: bool,
) -> bool:
    """判定一条 checker issue 是否被直白模式豁免（软规则 → 不进入 arbitration）。

    用于 :func:`ink_writer.editor_wisdom.arbitration.collect_issues_from_review_metrics`
    过滤逻辑。约束：

    - ``rule_code`` 可能为空/``None`` → 返回 ``False``（保守不豁免）
    - 未命中本模块维护的 checker 白名单 → 返回 ``False``
    - ``relax_*`` 为 ``False`` → 直接返回 ``False``（兼容历史显式 skip）
    """
    if not rule_code or not checker_name:
        return False
    normalized = str(rule_code).strip().upper()
    if (
        relax_prose_impact
        and checker_name == PROSE_IMPACT_CHECKER_NAME
        and normalized in PROSE_IMPACT_RELAXED_RULES
    ):
        return True
    return (
        relax_flow_naturalness
        and checker_name == FLOW_NATURALNESS_CHECKER_NAME
        and normalized in FLOW_NATURALNESS_RELAXED_RULES
    )


def iter_relaxed_rules() -> Iterable[tuple[str, frozenset[str]]]:
    """返回 ``(checker_name, relaxed_rules_set)`` 对，供 spec 校验测试内省。"""
    yield PROSE_IMPACT_CHECKER_NAME, PROSE_IMPACT_RELAXED_RULES
    yield FLOW_NATURALNESS_CHECKER_NAME, FLOW_NATURALNESS_RELAXED_RULES


__all__ = [
    "FLOW_NATURALNESS_CHECKER_NAME",
    "FLOW_NATURALNESS_RELAXED_RULES",
    "PROSE_IMPACT_CHECKER_NAME",
    "PROSE_IMPACT_RELAXED_RULES",
    "is_relaxed_issue",
    "iter_relaxed_rules",
    "should_relax_flow_naturalness",
    "should_relax_prose_impact",
]
