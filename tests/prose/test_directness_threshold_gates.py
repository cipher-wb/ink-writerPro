"""US-010: prose-impact / flow-naturalness 阈值微调激活门控测试。

覆盖：
  1. ``should_relax_prose_impact`` / ``should_relax_flow_naturalness`` 场景判定矩阵
  2. ``is_relaxed_issue`` 白名单命中（含 hard-block 不豁免护栏）
  3. ``PROSE_IMPACT_RELAXED_RULES`` / ``FLOW_NATURALNESS_RELAXED_RULES`` 常量稳定性
  4. ``arbitration.collect_issues_from_review_metrics`` 在直白模式下过滤两 checker
     白名单 rule code，非直白模式全量保留——零退化硬约束
  5. agent spec 文件（prose-impact-checker.md / flow-naturalness-checker.md）的
     关键门控文本锁定
  6. 端到端：combat 场景下 arbitrate_generic 不因 SHOT_MONOTONY / RATIO_DEVIATION
     产出 merged_fix
  7. 与 directness_checker / sensory_immersion_gate 的激活判定一致性
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ink_writer.editor_wisdom.arbitration import (
    arbitrate_generic,
    collect_issues_from_review_metrics,
)
from ink_writer.prose.directness_checker import is_activated as directness_is_activated
from ink_writer.prose.directness_threshold_gates import (
    FLOW_NATURALNESS_CHECKER_NAME,
    FLOW_NATURALNESS_RELAXED_RULES,
    PROSE_IMPACT_CHECKER_NAME,
    PROSE_IMPACT_RELAXED_RULES,
    is_relaxed_issue,
    iter_relaxed_rules,
    should_relax_flow_naturalness,
    should_relax_prose_impact,
)
from ink_writer.prose.sensory_immersion_gate import should_skip_sensory_immersion

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROSE_IMPACT_SPEC = _REPO_ROOT / "ink-writer" / "agents" / "prose-impact-checker.md"
_FLOW_SPEC = _REPO_ROOT / "ink-writer" / "agents" / "flow-naturalness-checker.md"


# ============================================================
# Section 1: constant + API integrity
# ============================================================


def test_checker_name_constants():
    assert PROSE_IMPACT_CHECKER_NAME == "prose-impact-checker"
    assert FLOW_NATURALNESS_CHECKER_NAME == "flow-naturalness-checker"


def test_relaxed_rule_sets_are_frozen():
    # frozenset 确保运行时不被意外 mutate（US-007 暴露的同类问题）
    assert isinstance(PROSE_IMPACT_RELAXED_RULES, frozenset)
    assert isinstance(FLOW_NATURALNESS_RELAXED_RULES, frozenset)


def test_prose_impact_relaxed_rules_cover_dim1_and_dim2():
    # 镜头多样性 (dim 1)
    assert "SHOT_MONOTONY" in PROSE_IMPACT_RELAXED_RULES
    assert "COMBAT_THREE_STAGE_MISSING" in PROSE_IMPACT_RELAXED_RULES
    assert "SCENE_NO_SWITCH" in PROSE_IMPACT_RELAXED_RULES
    assert "CLOSEUP_ABSENT" in PROSE_IMPACT_RELAXED_RULES
    # 感官丰富度 (dim 2)
    assert "VISUAL_OVERLOAD" in PROSE_IMPACT_RELAXED_RULES
    assert "NON_VISUAL_SPARSE" in PROSE_IMPACT_RELAXED_RULES
    assert "SENSORY_PLAN_MISMATCH" in PROSE_IMPACT_RELAXED_RULES
    assert "SENSORY_DESERT" in PROSE_IMPACT_RELAXED_RULES


def test_prose_impact_hard_block_rules_not_relaxed():
    # critical / hard-block 规则必须保留，哪怕直白场景
    forbidden_to_relax = {
        "SHOT_SINGLE_DOMINANCE",  # critical
        "CV_CRITICAL",  # 维度 3 句式节奏硬伤
        "WEAK_VERB_SEVERE",  # 维度 4 动词
        "ENV_EMOTION_DISSONANCE",  # 维度 5
        "CRITICAL_MOMENT_NO_CLOSEUP",  # 维度 6
        "COOL_POINT_NO_CLOSEUP",  # 维度 6
    }
    for rule in forbidden_to_relax:
        assert rule not in PROSE_IMPACT_RELAXED_RULES, (
            f"{rule} is a hard-block / non-dim1-2 rule — must NOT be relaxed"
        )


def test_flow_naturalness_relaxed_rules_only_dim5_subset():
    assert "RATIO_DEVIATION" in FLOW_NATURALNESS_RELAXED_RULES
    assert "DIALOGUE_STARVATION" in FLOW_NATURALNESS_RELAXED_RULES
    assert "DIALOGUE_FLOOD" in FLOW_NATURALNESS_RELAXED_RULES
    assert "INNER_MONOLOGUE_BLOAT" in FLOW_NATURALNESS_RELAXED_RULES


def test_flow_naturalness_hard_block_rules_not_relaxed():
    forbidden_to_relax = {
        "POV_INTRA_PARAGRAPH",
        "TRANSITION_HARD_CUT",
        "INFO_BUDGET_OVERFLOW_GOLDEN",
        "INFO_DUMP_SEVERE",
        "TABOO_VIOLATION",
        "VOICE_PROFILE_SEVERE",
        "VOICE_ABRUPT_SHIFT",
        "DIALOGUE_BLIND_FAIL",
        "DIALOGUE_BLIND_FAIL_SEVERE",
        "RATIO_DEVIATION_SEVERE",  # severe 变体必须保留
    }
    for rule in forbidden_to_relax:
        assert rule not in FLOW_NATURALNESS_RELAXED_RULES, (
            f"{rule} must never be relaxed — would regress "
            f"(非直白 checker 也依赖这些 rule 做 hard block)"
        )


def test_iter_relaxed_rules_yields_both_checkers():
    result = dict(iter_relaxed_rules())
    assert result[PROSE_IMPACT_CHECKER_NAME] is PROSE_IMPACT_RELAXED_RULES
    assert result[FLOW_NATURALNESS_CHECKER_NAME] is FLOW_NATURALNESS_RELAXED_RULES


# ============================================================
# Section 2: activation matrix
# ============================================================


@pytest.mark.parametrize(
    "scene_mode, chapter_no, expected",
    [
        # Directness-active scene_mode — always relax
        ("golden_three", 5, True),
        ("combat", 42, True),
        ("climax", 100, True),
        ("high_point", 7, True),
        # Non-directness scene_mode — never relax regardless of chapter
        ("slow_build", 1, False),
        ("emotional", 3, False),
        ("other", 2, False),
        # None + chapter bucket — golden-three fallback
        (None, 1, True),
        (None, 2, True),
        (None, 3, True),
        (None, 4, False),
        (None, 42, False),
        (None, 0, False),
    ],
)
def test_should_relax_prose_impact_matrix(scene_mode, chapter_no, expected):
    assert should_relax_prose_impact(scene_mode, chapter_no) is expected


@pytest.mark.parametrize(
    "scene_mode, chapter_no, expected",
    [
        ("golden_three", 5, True),
        ("combat", 42, True),
        ("climax", 100, True),
        ("high_point", 7, True),
        ("slow_build", 1, False),
        ("emotional", 3, False),
        ("other", 2, False),
        (None, 1, True),
        (None, 2, True),
        (None, 3, True),
        (None, 4, False),
        (None, 0, False),
    ],
)
def test_should_relax_flow_naturalness_matrix(scene_mode, chapter_no, expected):
    assert should_relax_flow_naturalness(scene_mode, chapter_no) is expected


def test_activation_is_same_as_directness_checker():
    # canonical single-source — modifying directness_checker.is_activated 必须同步 3 端
    for scene_mode in (
        "golden_three",
        "combat",
        "climax",
        "high_point",
        "slow_build",
        "emotional",
        "other",
        None,
    ):
        for chapter_no in (0, 1, 2, 3, 4, 50):
            expected = directness_is_activated(scene_mode, chapter_no)
            assert should_relax_prose_impact(scene_mode, chapter_no) is expected
            assert should_relax_flow_naturalness(scene_mode, chapter_no) is expected
            assert should_skip_sensory_immersion(scene_mode, chapter_no) is expected


def test_chapter_no_fallback_handles_none_and_negative():
    # chapter_no=None / 0 / 负数 → 按 0 处理
    assert should_relax_prose_impact(None, 0) is False
    assert should_relax_flow_naturalness(None, 0) is False


# ============================================================
# Section 3: is_relaxed_issue helper
# ============================================================


def test_is_relaxed_issue_hits_prose_impact_relaxed_rule():
    assert (
        is_relaxed_issue(
            PROSE_IMPACT_CHECKER_NAME,
            "SHOT_MONOTONY",
            relax_prose_impact=True,
            relax_flow_naturalness=True,
        )
        is True
    )


def test_is_relaxed_issue_hits_flow_naturalness_relaxed_rule():
    assert (
        is_relaxed_issue(
            FLOW_NATURALNESS_CHECKER_NAME,
            "RATIO_DEVIATION",
            relax_prose_impact=True,
            relax_flow_naturalness=True,
        )
        is True
    )


def test_is_relaxed_issue_hard_block_not_relaxed():
    # SHOT_SINGLE_DOMINANCE 不在白名单，即便 flag True 也不豁免
    assert (
        is_relaxed_issue(
            PROSE_IMPACT_CHECKER_NAME,
            "SHOT_SINGLE_DOMINANCE",
            relax_prose_impact=True,
            relax_flow_naturalness=True,
        )
        is False
    )


def test_is_relaxed_issue_non_directness_keeps_all_rules():
    # 非激活场景 → 即便命中白名单 rule code，也返回 False（保持原规则链路）
    assert (
        is_relaxed_issue(
            PROSE_IMPACT_CHECKER_NAME,
            "SHOT_MONOTONY",
            relax_prose_impact=False,
            relax_flow_naturalness=False,
        )
        is False
    )


def test_is_relaxed_issue_empty_rule_code_returns_false():
    assert (
        is_relaxed_issue(
            PROSE_IMPACT_CHECKER_NAME,
            "",
            relax_prose_impact=True,
            relax_flow_naturalness=True,
        )
        is False
    )
    assert (
        is_relaxed_issue(
            PROSE_IMPACT_CHECKER_NAME,
            None,
            relax_prose_impact=True,
            relax_flow_naturalness=True,
        )
        is False
    )


def test_is_relaxed_issue_unknown_checker_returns_false():
    assert (
        is_relaxed_issue(
            "reader-pull-checker",
            "SHOT_MONOTONY",
            relax_prose_impact=True,
            relax_flow_naturalness=True,
        )
        is False
    )


def test_is_relaxed_issue_case_insensitive_rule_code():
    # rule code 大小写归一（prose-impact 输出通常是 upper，但 shadow-safe 兜底）
    assert (
        is_relaxed_issue(
            PROSE_IMPACT_CHECKER_NAME,
            "shot_monotony",
            relax_prose_impact=True,
            relax_flow_naturalness=True,
        )
        is True
    )


def test_is_relaxed_issue_cross_checker_rule_not_honored():
    # RATIO_DEVIATION 属于 flow-naturalness，若 checker 填成 prose-impact 不应豁免
    assert (
        is_relaxed_issue(
            PROSE_IMPACT_CHECKER_NAME,
            "RATIO_DEVIATION",
            relax_prose_impact=True,
            relax_flow_naturalness=True,
        )
        is False
    )
    assert (
        is_relaxed_issue(
            FLOW_NATURALNESS_CHECKER_NAME,
            "SHOT_MONOTONY",
            relax_prose_impact=True,
            relax_flow_naturalness=True,
        )
        is False
    )


# ============================================================
# Section 4: arbitration integration
# ============================================================


def _mk_metrics_prose_impact_relaxed_only() -> dict:
    """review_metrics fixture：prose-impact 只有白名单内 rule codes 触发。"""
    return {
        "critical_issues": [],
        "review_payload_json": {
            "checker_results": {
                "prose-impact-checker": {
                    "violations": [
                        {
                            "type": "SHOT_MONOTONY",
                            "severity": "high",
                            "suggestion": "连续 4 段近景，建议切换远景",
                        },
                        {
                            "type": "VISUAL_OVERLOAD",
                            "severity": "warning",
                            "suggestion": "视觉占比 75%，建议加入触觉/听觉",
                        },
                    ]
                }
            }
        },
    }


def _mk_metrics_prose_impact_mixed() -> dict:
    """prose-impact 同时含白名单 + 非白名单 rule codes。"""
    return {
        "critical_issues": [
            {
                "checker": "prose-impact-checker",
                "type": "CV_CRITICAL",
                "severity": "critical",
                "suggestion": "章级 CV<0.35 必须 hard block",
            },
        ],
        "review_payload_json": {
            "checker_results": {
                "prose-impact-checker": {
                    "violations": [
                        {
                            "type": "SHOT_MONOTONY",
                            "severity": "high",
                            "suggestion": "连续 4 段近景（relaxed in directness mode）",
                        },
                        {
                            "type": "WEAK_VERB_OVERLOAD",
                            "severity": "warning",
                            "suggestion": "weak_verb_ratio 38%（仍保留）",
                        },
                    ]
                }
            }
        },
    }


def _mk_metrics_flow_naturalness_mixed() -> dict:
    return {
        "critical_issues": [],
        "review_payload_json": {
            "checker_results": {
                "flow-naturalness-checker": {
                    "violations": [
                        {
                            "type": "RATIO_DEVIATION",
                            "severity": "warning",
                            "suggestion": "对话占比偏离 15%（直白模式可豁免）",
                        },
                        {
                            "type": "DIALOGUE_STARVATION",
                            "severity": "high",
                            "suggestion": "对话占比 18%（直白模式豁免）",
                        },
                        {
                            "type": "RATIO_DEVIATION_SEVERE",
                            "severity": "high",
                            "suggestion": "对话占比 65%（severe 变体保留）",
                        },
                        {
                            "type": "POV_INTRA_PARAGRAPH",
                            "severity": "critical",
                            "suggestion": "单段内 POV 切换（永不豁免）",
                        },
                    ]
                }
            }
        },
    }


def test_collect_filters_prose_impact_relaxed_in_combat():
    metrics = _mk_metrics_prose_impact_relaxed_only()
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode="combat", chapter_no=42
    )
    # 全部属于白名单 → 激活场景下全部过滤，剩 0 条
    assert issues == []


def test_collect_filters_prose_impact_relaxed_in_golden_three_fallback():
    metrics = _mk_metrics_prose_impact_relaxed_only()
    # scene_mode=None + ch=2 → 黄金三章兜底
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode=None, chapter_no=2
    )
    assert issues == []


def test_collect_keeps_prose_impact_relaxed_in_slow_build():
    metrics = _mk_metrics_prose_impact_relaxed_only()
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode="slow_build", chapter_no=12
    )
    # 非直白场景 → SHOT_MONOTONY / VISUAL_OVERLOAD 正常保留
    sources = [i.source for i in issues]
    assert len(issues) == 2
    assert all(s.startswith("prose-impact-checker") for s in sources)


def test_collect_keeps_prose_impact_relaxed_when_scene_mode_omitted():
    metrics = _mk_metrics_prose_impact_relaxed_only()
    # 默认参数 → 保持 v21 行为（不豁免）
    issues = collect_issues_from_review_metrics(metrics)
    assert len(issues) == 2


def test_collect_mixed_prose_impact_drops_relaxed_keeps_retained():
    metrics = _mk_metrics_prose_impact_mixed()
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode="combat", chapter_no=50
    )
    types_seen = {i.source.split("#", 1)[1] for i in issues}
    # SHOT_MONOTONY 豁免，CV_CRITICAL 和 WEAK_VERB_OVERLOAD 保留
    assert "SHOT_MONOTONY" not in types_seen
    assert "WEAK_VERB_OVERLOAD" in types_seen
    assert any("CV_CRITICAL" in s for s in types_seen)


def test_collect_mixed_prose_impact_full_in_slow_build():
    metrics = _mk_metrics_prose_impact_mixed()
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode="slow_build", chapter_no=50
    )
    types_seen = {i.source.split("#", 1)[1] for i in issues}
    # 非直白场景 → 所有 3 条都保留
    assert "SHOT_MONOTONY" in types_seen
    assert "WEAK_VERB_OVERLOAD" in types_seen
    assert any("CV_CRITICAL" in s for s in types_seen)


def test_collect_flow_naturalness_drops_only_relaxed_codes():
    metrics = _mk_metrics_flow_naturalness_mixed()
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode="climax", chapter_no=80
    )
    types_seen = {i.source.split("#", 1)[1] for i in issues}
    # 豁免：RATIO_DEVIATION / DIALOGUE_STARVATION
    assert "RATIO_DEVIATION" not in types_seen
    assert "DIALOGUE_STARVATION" not in types_seen
    # 保留：severe 变体 + POV
    assert "RATIO_DEVIATION_SEVERE" in types_seen
    assert "POV_INTRA_PARAGRAPH" in types_seen


def test_collect_flow_naturalness_keeps_all_in_emotional():
    metrics = _mk_metrics_flow_naturalness_mixed()
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode="emotional", chapter_no=80
    )
    types_seen = {i.source.split("#", 1)[1] for i in issues}
    # emotional 是非直白场景 → 4 条全保留
    for code in (
        "RATIO_DEVIATION",
        "DIALOGUE_STARVATION",
        "RATIO_DEVIATION_SEVERE",
        "POV_INTRA_PARAGRAPH",
    ):
        assert code in types_seen


def test_collect_critical_issues_drops_relaxed_rule():
    # critical_issues 路径也走豁免
    metrics = {
        "critical_issues": [
            {
                "checker": "prose-impact-checker",
                "type": "CLOSEUP_ABSENT",
                "severity": "high",
                "suggestion": "整章无特写（relaxed in directness mode）",
            },
            {
                "checker": "prose-impact-checker",
                "type": "CV_CRITICAL",
                "severity": "critical",
                "suggestion": "章级 CV 0.33（硬伤保留）",
            },
        ],
        "review_payload_json": {},
    }
    combat_issues = collect_issues_from_review_metrics(
        metrics, scene_mode="combat", chapter_no=50
    )
    types_seen = {i.source.split("#", 1)[1] for i in combat_issues}
    assert not any("CLOSEUP_ABSENT" in s for s in types_seen)
    assert any("CV_CRITICAL" in s for s in types_seen)


def test_arbitrate_generic_no_shot_monotony_red_in_combat():
    """端到端：combat 场景下 arbitrate_generic 不产出 SHOT_MONOTONY merged_fix。"""
    metrics = _mk_metrics_prose_impact_relaxed_only()
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode="combat", chapter_no=50
    )
    payload = arbitrate_generic(50, issues)
    if payload is None:
        # 所有 issues 被过滤 → 无 merged_fixes 是合法结果
        return
    merged_sources_flat = [
        s for fix in payload["merged_fixes"] for s in fix["sources"]
    ]
    assert not any("SHOT_MONOTONY" in s for s in merged_sources_flat)
    assert not any("VISUAL_OVERLOAD" in s for s in merged_sources_flat)


def test_arbitrate_generic_shot_monotony_red_kept_in_slow_build():
    """零退化：slow_build 场景下 SHOT_MONOTONY 正常走 arbitration。"""
    metrics = _mk_metrics_prose_impact_relaxed_only()
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode="slow_build", chapter_no=50
    )
    payload = arbitrate_generic(50, issues)
    assert payload is not None
    merged_sources_flat = [
        s for fix in payload["merged_fixes"] for s in fix["sources"]
    ]
    assert any("SHOT_MONOTONY" in s for s in merged_sources_flat)


# ============================================================
# Section 5: agent spec gating text
# ============================================================


def test_prose_impact_spec_has_directness_mode_section():
    text = _PROSE_IMPACT_SPEC.read_text(encoding="utf-8")
    assert "## 直白模式阈值放宽 (v22 US-010)" in text
    # section 必须位于 ## 核心参考 之后、## 检查范围 之前（结构性门禁）
    idx_section = text.index("## 直白模式阈值放宽 (v22 US-010)")
    idx_core = text.index("## 核心参考")
    idx_range = text.index("## 检查范围")
    assert idx_core < idx_section < idx_range


def test_prose_impact_spec_lists_program_gate_name():
    text = _PROSE_IMPACT_SPEC.read_text(encoding="utf-8")
    # 程序化对等引用是单源契约锚点
    assert "should_relax_prose_impact" in text
    assert "directness_threshold_gates" in text


@pytest.mark.parametrize(
    "rule_code",
    ["SHOT_MONOTONY", "VISUAL_OVERLOAD", "NON_VISUAL_SPARSE", "SENSORY_DESERT"],
)
def test_prose_impact_spec_mentions_relaxed_rule_codes(rule_code):
    text = _PROSE_IMPACT_SPEC.read_text(encoding="utf-8")
    assert rule_code in text, (
        f"{rule_code} should be documented as relaxed in prose-impact-checker.md"
    )


def test_prose_impact_spec_mentions_retained_hard_block():
    text = _PROSE_IMPACT_SPEC.read_text(encoding="utf-8")
    # 必须显式提到 SHOT_SINGLE_DOMINANCE 仍 hard block，防止读者误解"直白 = 关闭所有 shot 规则"
    section_start = text.index("## 直白模式阈值放宽 (v22 US-010)")
    section_end = text.index("## 检查范围", section_start)
    section = text[section_start:section_end]
    assert "SHOT_SINGLE_DOMINANCE" in section
    assert "hard block" in section or "hard-block" in section


def test_flow_naturalness_spec_has_directness_mode_section():
    text = _FLOW_SPEC.read_text(encoding="utf-8")
    assert "## 直白模式阈值放宽 (v22 US-010)" in text
    idx_section = text.index("## 直白模式阈值放宽 (v22 US-010)")
    idx_core = text.index("## 核心参考")
    idx_range = text.index("## 检查范围")
    assert idx_core < idx_section < idx_range


def test_flow_naturalness_spec_lists_program_gate_name():
    text = _FLOW_SPEC.read_text(encoding="utf-8")
    assert "should_relax_flow_naturalness" in text
    assert "directness_threshold_gates" in text


@pytest.mark.parametrize(
    "rule_code",
    ["RATIO_DEVIATION", "DIALOGUE_STARVATION", "DIALOGUE_FLOOD"],
)
def test_flow_naturalness_spec_mentions_relaxed_rule_codes(rule_code):
    text = _FLOW_SPEC.read_text(encoding="utf-8")
    assert rule_code in text, (
        f"{rule_code} should be documented as relaxed in flow-naturalness-checker.md"
    )


def test_flow_naturalness_spec_mentions_retained_severe_variant():
    text = _FLOW_SPEC.read_text(encoding="utf-8")
    section_start = text.index("## 直白模式阈值放宽 (v22 US-010)")
    section_end = text.index("## 检查范围", section_start)
    section = text[section_start:section_end]
    # ±20% severe 变体必须保留
    assert "RATIO_DEVIATION_SEVERE" in section
    assert "POV_INTRA_PARAGRAPH" in section


# ============================================================
# Section 6: proofreading-checker untouched (零退化)
# ============================================================


def test_proofreading_checker_rules_not_in_relaxed_sets():
    # AC 明确：不放宽 proofreading-checker 的弱动词/AI 味检测
    proofreading_rules = {
        "WEAK_VERB",
        "AI_SMELL",
        "REPEATED_PHRASE",
        "MODAL_ABUSE",
        "TIME_STAMP_OPENER",
    }
    all_relaxed = PROSE_IMPACT_RELAXED_RULES | FLOW_NATURALNESS_RELAXED_RULES
    for rule in proofreading_rules:
        assert rule not in all_relaxed


# ============================================================
# Section 7: public API export
# ============================================================


def test_public_api_exports():
    # ink_writer.prose 顶层导出必须包含 US-010 符号
    from ink_writer import prose

    assert hasattr(prose, "PROSE_IMPACT_CHECKER_NAME")
    assert hasattr(prose, "FLOW_NATURALNESS_CHECKER_NAME")
    assert hasattr(prose, "PROSE_IMPACT_RELAXED_RULES")
    assert hasattr(prose, "FLOW_NATURALNESS_RELAXED_RULES")
    assert hasattr(prose, "should_relax_prose_impact")
    assert hasattr(prose, "should_relax_flow_naturalness")
    assert hasattr(prose, "is_relaxed_issue")
    # __all__ 一致性
    assert "PROSE_IMPACT_CHECKER_NAME" in prose.__all__
    assert "should_relax_prose_impact" in prose.__all__
    assert "should_relax_flow_naturalness" in prose.__all__
