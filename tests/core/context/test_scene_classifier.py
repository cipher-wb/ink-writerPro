#!/usr/bin/env python3
"""US-009 tests: scene_classifier + context pack scene_mode 暴露。

Acceptance 覆盖：
- 固定 7 取值 schema
- 7 种场景分类覆盖（golden_three/combat/climax/high_point/slow_build/emotional/other）
- 优先级 golden_three > climax > high_point > combat > emotional > slow_build > other
- 与 directness_checker.is_activated 行为一致（chapter∈[1,3] 强制激活）
- context pack _build_pack 暴露 meta.scene_mode 字段
- context-agent.md spec 文字契约锚点
"""
from __future__ import annotations

from pathlib import Path

import pytest
from ink_writer.core.context.context_manager import ContextManager
from ink_writer.core.context.scene_classifier import (
    CLIMAX,
    COMBAT,
    EMOTIONAL,
    GOLDEN_THREE,
    HIGH_POINT,
    OTHER,
    SCENE_MODES,
    SLOW_BUILD,
    classify_scene,
    resolve_scene_mode,
)
from ink_writer.core.infra.config import DataModulesConfig
from ink_writer.prose.directness_checker import (
    ACTIVATION_SCENE_MODES,
    is_activated,
)

# ---------------------------------------------------------------------------
# Schema / exports
# ---------------------------------------------------------------------------


def test_scene_modes_exact_seven_values():
    assert SCENE_MODES == (
        GOLDEN_THREE,
        CLIMAX,
        HIGH_POINT,
        COMBAT,
        EMOTIONAL,
        SLOW_BUILD,
        OTHER,
    )
    assert len(SCENE_MODES) == 7


def test_scene_mode_string_literals_are_canonical():
    # 确保字符串常量与 directness_checker / sensory_immersion_gate / writer-agent
    # 同源。ACTIVATION_SCENE_MODES 是这些 scene_mode 的子集。
    expected_active = {GOLDEN_THREE, COMBAT, CLIMAX, HIGH_POINT}
    assert expected_active == set(ACTIVATION_SCENE_MODES)


# ---------------------------------------------------------------------------
# classify_scene 7 场景覆盖
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "chapter,outline,expected",
    [
        (1, "random text", GOLDEN_THREE),
        (2, None, GOLDEN_THREE),
        (3, "战斗片段", GOLDEN_THREE),  # chapter 覆盖 outline
        (50, "第50章 主角与反派的决战终局", CLIMAX),
        (60, "### 爽点：主角反转打脸", HIGH_POINT),
        (70, "本章描写与对手的激战与斗法", COMBAT),
        (80, "主角与师父告别，心里满是思念", EMOTIONAL),
        (90, "日常修炼，铺垫下一阶段实力", SLOW_BUILD),
        (100, "这是一段普通的叙事没有特别信号", OTHER),
        (100, "", OTHER),
        (100, None, OTHER),
    ],
)
def test_classify_scene_category_coverage(chapter, outline, expected):
    assert classify_scene(chapter, outline) == expected


# ---------------------------------------------------------------------------
# 优先级矩阵：多 tag 命中时取最高优先级
# ---------------------------------------------------------------------------


def test_priority_climax_over_high_point_combat_emotional_slow():
    outline = "决战来临：战斗爽点、告别、日常铺垫" + "反转" + "日常"
    # climax ("决战") 优先级最高
    assert classify_scene(50, outline) == CLIMAX


def test_priority_high_point_over_combat_emotional_slow():
    outline = "本章核心是反转打脸，顺带一段激战与告别日常铺垫"
    assert classify_scene(50, outline) == HIGH_POINT


def test_priority_combat_over_emotional_slow():
    outline = "主角与反派交手，对方告别时日常闲聊被打断"
    assert classify_scene(50, outline) == COMBAT


def test_priority_emotional_over_slow_build():
    outline = "主角与旧友告别，日常回忆片段"
    assert classify_scene(50, outline) == EMOTIONAL


def test_slow_build_standalone():
    outline = "本章为过渡日常，主角调息修炼"
    assert classify_scene(50, outline) == SLOW_BUILD


def test_golden_three_hard_override_beats_any_keyword():
    # chapter 1/2/3 无论 outline 说什么都必须 golden_three
    outline = "决战终局，爽点反转打脸，激战对决告别日常"
    for ch in (1, 2, 3):
        assert classify_scene(ch, outline) == GOLDEN_THREE


# ---------------------------------------------------------------------------
# resolve_scene_mode：外部显式覆盖 + golden_three 硬锁
# ---------------------------------------------------------------------------


def test_resolve_honors_valid_explicit_scene_mode_when_not_golden_three():
    assert resolve_scene_mode(50, outline_text="", explicit_scene_mode=COMBAT) == COMBAT
    assert resolve_scene_mode(50, outline_text="", explicit_scene_mode=CLIMAX) == CLIMAX
    assert resolve_scene_mode(50, outline_text="", explicit_scene_mode=EMOTIONAL) == EMOTIONAL


def test_resolve_golden_three_overrides_explicit_for_ch1_to_3():
    # chapter ∈ [1,3] 时外部输入不能覆盖 golden_three
    for ch in (1, 2, 3):
        assert resolve_scene_mode(ch, explicit_scene_mode=COMBAT) == GOLDEN_THREE
        assert resolve_scene_mode(ch, explicit_scene_mode=CLIMAX) == GOLDEN_THREE
        assert resolve_scene_mode(ch, explicit_scene_mode="other") == GOLDEN_THREE


def test_resolve_ignores_unknown_explicit_value_falls_back_to_classifier():
    # 拼写错误不应激活错误场景；回落到 classify_scene
    outline = "主角出手交锋"
    assert resolve_scene_mode(50, outline, explicit_scene_mode="COMBATT") == COMBAT
    assert resolve_scene_mode(50, "", explicit_scene_mode="high-point") == OTHER


def test_resolve_no_explicit_uses_classifier():
    assert resolve_scene_mode(50, "主角与对手对决") == COMBAT
    assert resolve_scene_mode(50, "日常铺垫") == SLOW_BUILD
    assert resolve_scene_mode(50, None) == OTHER


# ---------------------------------------------------------------------------
# 与 directness_checker.is_activated 的一致性（US-006 全场景激活）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "chapter,outline,expect_active",
    [
        (1, "", True),   # golden_three
        (2, "", True),
        (3, "", True),
        (50, "决战终局", True),   # climax
        (50, "反转打脸", True),   # high_point
        (50, "对决激战", True),   # combat
        (50, "告别思念", True),   # emotional → US-006 后全场景激活
        (50, "日常铺垫", True),   # slow_build → US-006 后全场景激活
        (50, "普通叙事", True),   # other → US-006 后全场景激活
    ],
)
def test_classify_result_consistent_with_is_activated(chapter, outline, expect_active):
    mode = classify_scene(chapter, outline)
    assert is_activated(mode, chapter) is expect_active


# ---------------------------------------------------------------------------
# 输入鲁棒性
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("chapter", [0, -1, -100])
def test_non_positive_chapter_is_not_golden_three(chapter):
    # 非正章节号不触发 golden_three 硬锁（与 directness_checker 同语义）
    assert classify_scene(chapter, "决战") == CLIMAX
    assert classify_scene(chapter, None) == OTHER


def test_empty_or_none_outline_falls_back_to_other_when_not_golden():
    assert classify_scene(50, "") == OTHER
    assert classify_scene(50, None) == OTHER


# ---------------------------------------------------------------------------
# context pack 集成：meta.scene_mode 字段必须暴露
# ---------------------------------------------------------------------------


def _write_chapter(chapters_dir: Path, num: int, body: str) -> None:
    chapters_dir.mkdir(parents=True, exist_ok=True)
    (chapters_dir / f"第{num:04d}章.md").write_text(body, encoding="utf-8")


def _write_outline(project_root: Path, num: int, body: str) -> Path:
    outline_dir = project_root / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)
    path = outline_dir / f"第{num}章-草稿.md"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def manager(tmp_path: Path) -> ContextManager:
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return ContextManager(cfg)


def test_pack_exposes_scene_mode_field_golden_three(manager):
    _write_outline(manager.config.project_root, 1, "### 第1章：主角登场")
    pack = manager._build_pack(1)
    assert "scene_mode" in pack["meta"]
    assert pack["meta"]["scene_mode"] == GOLDEN_THREE


def test_pack_exposes_scene_mode_field_combat(manager):
    _write_outline(manager.config.project_root, 50, "### 第50章：主角与反派正面交锋，激战不止")
    pack = manager._build_pack(50)
    assert pack["meta"]["scene_mode"] == COMBAT


def test_pack_exposes_scene_mode_field_other(manager):
    _write_outline(manager.config.project_root, 50, "### 第50章：普通的一段叙事")
    pack = manager._build_pack(50)
    assert pack["meta"]["scene_mode"] == OTHER


def test_pack_scene_mode_always_in_canonical_7(manager):
    # 多样本确保不会漏字段或返回 None
    fixtures = [
        (10, "主角修炼铺垫", SLOW_BUILD),
        (20, "反转打脸爽点", HIGH_POINT),
        (30, "大结局决战", CLIMAX),
        (40, "告别思念", EMOTIONAL),
    ]
    for ch, body, expected in fixtures:
        _write_outline(manager.config.project_root, ch, f"### 第{ch}章：{body}")
        pack = manager._build_pack(ch)
        mode = pack["meta"]["scene_mode"]
        assert mode in SCENE_MODES
        assert mode == expected


# ---------------------------------------------------------------------------
# context-agent.md spec 文字契约锚点
# ---------------------------------------------------------------------------


def _context_agent_spec() -> str:
    spec_path = Path(__file__).resolve().parents[3] / "ink-writer" / "agents" / "context-agent.md"
    return spec_path.read_text(encoding="utf-8")


def test_context_agent_spec_documents_scene_mode():
    text = _context_agent_spec()
    assert "Scene Mode" in text, "必须有 Scene Mode 字段章节"
    assert "meta.scene_mode" in text
    # 7 种合法取值全部列出
    for mode in SCENE_MODES:
        assert mode in text, f"context-agent.md 缺少 scene_mode 值: {mode}"


def test_context_agent_spec_mentions_scene_classifier_source():
    text = _context_agent_spec()
    assert "scene_classifier" in text
    assert "resolve_scene_mode" in text


def test_context_agent_spec_mentions_downstream_consumers():
    text = _context_agent_spec()
    # PRD 要求下游统一以 scene_mode 为激活依据
    for consumer in (
        "writer-agent",
        "directness-checker",
        "sensory-immersion-checker",
        "polish-agent",
    ):
        assert consumer in text, f"context-agent.md 缺少下游消费者提及: {consumer}"
