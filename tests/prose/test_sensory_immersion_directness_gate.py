"""US-007: sensory-immersion-checker 直白模式激活门控测试。

覆盖：
  1. ``should_skip_sensory_immersion`` 的场景判定矩阵（7 种 scene_mode + 黄金三章兜底）
  2. agent spec 文件 (writer-agent.md / sensory-immersion-checker.md) 的关键门控文本锁定
  3. ``arbitration.collect_issues_from_review_metrics`` 在直白模式下过滤 sensory-immersion
     issues（scene_mode=combat → 不产生 Red），非直白模式下保留（scene_mode=slow_build
     正常触发）——零退化硬约束
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ink_writer.editor_wisdom.arbitration import (
    arbitrate_generic,
    collect_issues_from_review_metrics,
)
from ink_writer.prose.sensory_immersion_gate import (
    SENSORY_IMMERSION_CHECKER_NAME,
    should_skip_sensory_immersion,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WRITER_AGENT_SPEC = _REPO_ROOT / "ink-writer" / "agents" / "writer-agent.md"
_SENSORY_SPEC = _REPO_ROOT / "ink-writer" / "agents" / "sensory-immersion-checker.md"


# ---------------- Section 1: should_skip_sensory_immersion ----------------


@pytest.mark.parametrize(
    "scene_mode, chapter_no, expected",
    [
        # Directness-active scene_mode — should skip at any chapter
        ("golden_three", 5, True),
        ("combat", 42, True),
        ("climax", 100, True),
        ("high_point", 7, True),
        # Non-directness scene_mode — should run even in ch1
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
def test_should_skip_sensory_immersion_matrix(scene_mode, chapter_no, expected):
    assert (
        should_skip_sensory_immersion(scene_mode, chapter_no) is expected
    ), f"scene_mode={scene_mode!r} chapter_no={chapter_no} expected={expected}"


def test_should_skip_sensory_immersion_checker_name_constant():
    # polish-agent / arbitration 都使用此常量作为 canonical name，防止拼写漂移
    assert SENSORY_IMMERSION_CHECKER_NAME == "sensory-immersion-checker"


def test_should_skip_sensory_immersion_handles_string_chapter_fallback():
    # chapter_no=0 应 fallback 到 False（非黄金三章）
    assert should_skip_sensory_immersion(None, 0) is False


# ---------------- Section 2: agent spec gating text ----------------


def test_writer_agent_l10b_marks_non_directness_only():
    text = _WRITER_AGENT_SPEC.read_text(encoding="utf-8")
    assert "L10b 感官锚点法则" in text
    # 关键短语锚定：US-007 要求 L10b 段显式标注"仅在非 Directness Mode 场景生效"
    l10b_idx = text.index("L10b 感官锚点法则")
    # 取本行为断言区间（标题后 400 字）
    l10b_slice = text[l10b_idx : l10b_idx + 400]
    assert "仅在非 Directness Mode 场景生效" in l10b_slice


def test_writer_agent_l10e_marks_non_directness_only():
    text = _WRITER_AGENT_SPEC.read_text(encoding="utf-8")
    assert "L10e 感官主导模态法则" in text
    l10e_idx = text.index("L10e 感官主导模态法则")
    l10e_slice = text[l10e_idx : l10e_idx + 400]
    assert "仅在非 Directness Mode 场景生效" in l10e_slice


def test_writer_agent_directness_suspension_protocol_explicit():
    text = _WRITER_AGENT_SPEC.read_text(encoding="utf-8")
    # 暂挂协议小节必须明示：不强求非视觉感官密度、不强求感官轮换
    assert "不强求" in text
    assert "非视觉感官" in text
    assert "主导感官轮换" in text
    # 交叉指向 sensory-immersion-checker skipped
    assert "sensory-immersion-checker" in text
    assert "skipped" in text


def test_sensory_immersion_spec_has_activation_gating_section():
    text = _SENSORY_SPEC.read_text(encoding="utf-8")
    # 必须在顶部（核心参考之后 / 检查范围之前）新增激活门控章节
    assert "直白模式激活门控" in text
    gate_idx = text.index("直白模式激活门控")
    range_idx = text.index("## 检查范围")
    assert gate_idx < range_idx, "激活门控章节必须在 ## 检查范围之前"
    # 跳过条件文字契约
    gate_slice = text[gate_idx:range_idx]
    assert "golden_three" in gate_slice
    assert "combat" in gate_slice
    assert "climax" in gate_slice
    assert "high_point" in gate_slice
    assert "slow_build" in gate_slice
    assert "emotional" in gate_slice
    # skipped JSON 契约
    assert '"status": "skipped"' in gate_slice
    assert '"reason": "directness_mode_active"' in gate_slice
    # 程序化对等提示
    assert "should_skip_sensory_immersion" in gate_slice


def test_sensory_immersion_spec_references_writer_agent_crosslink():
    text = _SENSORY_SPEC.read_text(encoding="utf-8")
    # 跨文件回指 writer-agent 顶部 Directness Mode
    assert "writer-agent.md" in text
    assert "Directness Mode" in text


# ---------------- Section 3: arbitration scene_mode filter ----------------


def _mk_metrics_with_sensory_violation() -> dict:
    """构造 review_metrics payload：只含 sensory-immersion-checker 的 high 违规。"""
    return {
        "critical_issues": [],
        "review_payload_json": {
            "checker_results": {
                "sensory-immersion-checker": {
                    "violations": [
                        {
                            "type": "ROTATION_STALL_SEVERE",
                            "severity": "high",
                            "suggestion": "scene 2/3/4 主导感官均为视觉，必须轮换",
                        }
                    ]
                }
            }
        },
    }


def _mk_metrics_multi_checker() -> dict:
    return {
        "critical_issues": [
            {
                "checker": "sensory-immersion-checker",
                "type": "ABSENT_SCENE",
                "severity": "critical",
                "suggestion": "非过渡 scene 完全无感官描写",
            },
            {
                "checker": "prose-impact-checker",
                "type": "SHOT_MONOTONY",
                "severity": "high",
                "suggestion": "连续 4 段同类型镜头",
            },
        ],
        "review_payload_json": {
            "checker_results": {
                "sensory-immersion-checker": {
                    "violations": [
                        {
                            "type": "DEFAULT_VISUAL_BIAS",
                            "severity": "critical",
                            "suggestion": "全 scene 主导视觉",
                        }
                    ]
                },
                "flow-naturalness-checker": {
                    "violations": [
                        {
                            "type": "TONE_DRIFT",
                            "severity": "medium",
                            "suggestion": "语气一致性降到 7.2",
                        }
                    ]
                },
            }
        },
    }


def test_collect_filters_sensory_in_combat_scene():
    metrics = _mk_metrics_with_sensory_violation()
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode="combat", chapter_no=42
    )
    # 直白模式激活 → sensory-immersion issues 全部过滤掉
    assert issues == []


def test_collect_filters_sensory_in_golden_three_fallback():
    metrics = _mk_metrics_with_sensory_violation()
    # scene_mode=None + chapter_no=2 → 黄金三章兜底激活
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode=None, chapter_no=2
    )
    assert issues == []


def test_collect_keeps_sensory_in_slow_build_scene():
    metrics = _mk_metrics_with_sensory_violation()
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode="slow_build", chapter_no=12
    )
    assert len(issues) == 1
    assert issues[0].source.startswith("sensory-immersion-checker#")
    assert "主导感官" in issues[0].fix_prompt


def test_collect_keeps_sensory_when_scene_mode_omitted():
    # 默认参数（未显式传 scene_mode/chapter_no）→ 保持 v18 US-011 原行为
    metrics = _mk_metrics_with_sensory_violation()
    issues = collect_issues_from_review_metrics(metrics)
    assert len(issues) == 1
    assert issues[0].source.startswith("sensory-immersion-checker#")


def test_collect_multi_checker_only_drops_sensory_in_combat():
    metrics = _mk_metrics_multi_checker()
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode="combat", chapter_no=50
    )
    # sensory 的 critical + violations 都被过滤，prose-impact / flow-naturalness 保留
    sources = [i.source for i in issues]
    assert not any(s.startswith("sensory-immersion-checker") for s in sources)
    assert any(s.startswith("prose-impact-checker") for s in sources)
    assert any(s.startswith("flow-naturalness-checker") for s in sources)


def test_collect_multi_checker_keeps_sensory_in_emotional_scene():
    metrics = _mk_metrics_multi_checker()
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode="emotional", chapter_no=50
    )
    sources = [i.source for i in issues]
    # emotional 是非直白场景 → sensory issues 正常保留（critical + violations 都在）
    assert any(s.startswith("sensory-immersion-checker#") for s in sources)
    assert any(s.startswith("prose-impact-checker") for s in sources)


def test_arbitrate_generic_no_sensory_red_in_combat_scene():
    """端到端：combat 场景下 arbitrate_generic 不产出 sensory-immersion 的 merged_fixes。"""
    metrics = _mk_metrics_multi_checker()
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode="combat", chapter_no=50
    )
    payload = arbitrate_generic(50, issues)
    assert payload is not None
    merged_sources_flat = [
        s for fix in payload["merged_fixes"] for s in fix["sources"]
    ]
    assert not any(
        "sensory-immersion-checker" in s for s in merged_sources_flat
    )


def test_arbitrate_generic_sensory_red_kept_in_slow_build():
    """零退化验证：slow_build 场景下 sensory-immersion 的 Red 正常走 arbitration。"""
    metrics = _mk_metrics_multi_checker()
    issues = collect_issues_from_review_metrics(
        metrics, scene_mode="slow_build", chapter_no=50
    )
    payload = arbitrate_generic(50, issues)
    assert payload is not None
    merged_sources_flat = [
        s for fix in payload["merged_fixes"] for s in fix["sources"]
    ]
    assert any(
        "sensory-immersion-checker" in s for s in merged_sources_flat
    )
