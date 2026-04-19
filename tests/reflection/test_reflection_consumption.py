#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""US-008: reflection agent 消费链路显式 wire 测试。

验证 `_build_pack` 显式调 `_load_reflections(project_root)`，TEMPLATE_WEIGHTS
给 reflections 最小权重 0.05，并端到端验证 writer-agent prompt（即
`build_context` 装配出的 `sections.reflections.text`）含 reflection bullets。

所有测试覆盖 ACCEPT CRITERIA:
1. ``_build_pack`` 显式调用 ``_load_reflections(project_root)``
2. ``context_weights.py`` 给 reflections 最小权重 0.05（全部 4+12 模板组合）
3. 端到端：writer-agent prompt 含 reflection bullets
4. 空 reflections.json / 缺失 reflections.json 不 crash
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ink_writer.core.context.context_manager import ContextManager
from ink_writer.core.context.context_weights import (
    REFLECTIONS_WEIGHT_FLOOR,
    TEMPLATE_WEIGHTS,
    TEMPLATE_WEIGHTS_DYNAMIC_DEFAULT,
)
from ink_writer.core.infra.config import DataModulesConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _bootstrap_min_project(tmp_path: Path) -> DataModulesConfig:
    """构造最小可用项目结构供 ContextManager 装配 pack。"""
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    state = {
        "protagonist_state": {"name": "测试主角", "location": {"current": "起始地"}},
        "chapter_meta": {},
        "disambiguation_warnings": [],
        "disambiguation_pending": [],
    }
    cfg.state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return cfg


def _write_reflections(root: Path, bullets: list[str], *, chapter: int = 50) -> None:
    """生成符合 reflection_agent 契约的 .ink/reflections.json 文件。"""
    ink = root / ".ink"
    ink.mkdir(parents=True, exist_ok=True)
    payload = {
        "latest": {
            "chapter": chapter,
            "window": 50,
            "bullets": bullets,
            "evidence": {},
            "mode": "heuristic",
        },
        "history": [],
    }
    (ink / "reflections.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# 1) 权重守门：reflections 最小权重 0.05（静态约束）
# ---------------------------------------------------------------------------


class TestReflectionsWeightFloor:
    def test_floor_constant_equals_0_05(self):
        assert REFLECTIONS_WEIGHT_FLOOR == pytest.approx(0.05)

    def test_all_static_templates_have_reflections_weight(self):
        for template_name, weights in TEMPLATE_WEIGHTS.items():
            assert "reflections" in weights, f"{template_name} 模板缺少 reflections 权重"
            assert weights["reflections"] >= 0.05, (
                f"{template_name} 模板的 reflections 权重 {weights['reflections']} 低于 0.05 下限"
            )

    def test_all_dynamic_stage_templates_have_reflections_weight(self):
        for stage, templates in TEMPLATE_WEIGHTS_DYNAMIC_DEFAULT.items():
            for template_name, weights in templates.items():
                assert "reflections" in weights, (
                    f"dynamic[{stage}][{template_name}] 缺少 reflections 权重"
                )
                assert weights["reflections"] >= 0.05, (
                    f"dynamic[{stage}][{template_name}] reflections 权重 "
                    f"{weights['reflections']} 低于 0.05 下限"
                )


# ---------------------------------------------------------------------------
# 2) _build_pack 显式调 _load_reflections(project_root)
# ---------------------------------------------------------------------------


class TestBuildPackExplicitWire:
    def test_build_pack_calls_load_reflections_with_project_root(self, tmp_path: Path):
        cfg = _bootstrap_min_project(tmp_path)
        _write_reflections(tmp_path, ["长程主题：孤独感递增"], chapter=50)

        manager = ContextManager(cfg)

        with patch.object(
            ContextManager,
            "_load_reflections",
            autospec=True,
            wraps=ContextManager._load_reflections,
        ) as spy:
            pack = manager._build_pack(1)

        # 至少被显式调用一次，且首次调用是从 _build_pack 走 kwarg project_root
        assert spy.call_count >= 1, "_build_pack 未调用 _load_reflections"
        # spy 首次调用的 kwargs 包含 project_root
        first_call_kwargs = spy.call_args_list[0].kwargs
        assert "project_root" in first_call_kwargs, (
            f"_build_pack 未以 kwarg 传入 project_root，实际 kwargs: {first_call_kwargs}"
        )
        assert first_call_kwargs["project_root"] == cfg.project_root
        # pack 顶层必须含 reflections
        assert "reflections" in pack
        assert pack["reflections"].get("bullets") == ["长程主题：孤独感递增"]

    def test_load_reflections_accepts_no_args_backcompat(self, tmp_path: Path):
        """向后兼容：不传 project_root 时应 fallback 到 self.config.project_root。"""
        cfg = _bootstrap_min_project(tmp_path)
        _write_reflections(tmp_path, ["bullet-a", "bullet-b"], chapter=30)
        manager = ContextManager(cfg)

        result = manager._load_reflections()  # 不传参

        assert result.get("bullets") == ["bullet-a", "bullet-b"]
        assert result.get("source") == ".ink/reflections.json"


# ---------------------------------------------------------------------------
# 3) 端到端：writer-agent prompt 含 reflection bullets
# ---------------------------------------------------------------------------


class TestEndToEndConsumption:
    def test_build_context_renders_reflection_bullets_in_section_text(self, tmp_path: Path):
        cfg = _bootstrap_min_project(tmp_path)
        bullets = [
            "情感主题：主角对往昔的眷恋频繁出现",
            "世界观伏笔：北境镜湖连续三章被提及",
            "冲突模式：单一误解多次复用",
        ]
        _write_reflections(tmp_path, bullets, chapter=50)

        manager = ContextManager(cfg)
        payload = manager.build_context(1, use_snapshot=False, save_snapshot=False)

        assert "sections" in payload
        assert "reflections" in payload["sections"], (
            "assembled context 缺少 reflections section（SECTION_ORDER 未接入）"
        )
        section = payload["sections"]["reflections"]
        # content 是 _build_pack 出来的 dict，text 是被 _compact_json_text 序列化
        content = section.get("content") or {}
        assert content.get("bullets") == bullets
        text = section.get("text") or ""
        # 每条 bullet 的中文必须出现在 writer-agent 可见的 text prompt 里
        for b in bullets:
            assert b in text, f"bullet 未出现在 section text：{b}"
        # budget 字段存在（weight=0.05 × max_chars(>=8000) >= 400）
        assert section.get("budget") is not None
        assert section["budget"] >= int(8000 * 0.05)

    def test_build_context_reflections_weight_takes_effect(self, tmp_path: Path):
        """验证 reflections section 被 TEMPLATE_WEIGHTS 中 0.05 权重真实配到预算。"""
        cfg = _bootstrap_min_project(tmp_path)
        _write_reflections(tmp_path, ["示例 bullet"], chapter=50)
        manager = ContextManager(cfg)
        payload = manager.build_context(
            1,
            template="plot",
            use_snapshot=False,
            save_snapshot=False,
            max_chars=10000,
        )
        section = payload["sections"]["reflections"]
        # 10000 × 0.05 = 500 chars
        assert section.get("budget") == 500


# ---------------------------------------------------------------------------
# 4) 空 / 缺失 reflections.json 不 crash
# ---------------------------------------------------------------------------


class TestEmptyOrMissingReflections:
    def test_missing_reflections_file_does_not_crash(self, tmp_path: Path):
        cfg = _bootstrap_min_project(tmp_path)
        # 注意：故意不写 .ink/reflections.json
        manager = ContextManager(cfg)

        payload = manager.build_context(1, use_snapshot=False, save_snapshot=False)

        # pack 装配不 crash；reflections section 存在但内容为空（空 dict）
        section = payload["sections"].get("reflections")
        assert section is not None
        content = section.get("content")
        # content 可以是 {} 或者包含空 bullets
        assert content == {} or not content.get("bullets")

    def test_empty_bullets_list_does_not_crash(self, tmp_path: Path):
        cfg = _bootstrap_min_project(tmp_path)
        _write_reflections(tmp_path, [], chapter=50)  # latest.bullets=[]
        manager = ContextManager(cfg)

        payload = manager.build_context(1, use_snapshot=False, save_snapshot=False)

        section = payload["sections"]["reflections"]
        content = section.get("content") or {}
        # bullets 为空时，_load_reflections 仍返回带 bullets=[] 的 compact dict
        assert content.get("bullets") == []
        # text 不 raise
        assert isinstance(section.get("text"), str)

    def test_corrupt_reflections_json_falls_back_to_empty(self, tmp_path: Path):
        """reflections.json 损坏时 load_reflections 返回 None → _load_reflections → {}。"""
        cfg = _bootstrap_min_project(tmp_path)
        ink = tmp_path / ".ink"
        ink.mkdir(parents=True, exist_ok=True)
        (ink / "reflections.json").write_text("{ not json", encoding="utf-8")
        manager = ContextManager(cfg)

        payload = manager.build_context(1, use_snapshot=False, save_snapshot=False)
        section = payload["sections"].get("reflections")
        assert section is not None
        assert section.get("content") == {}

    def test_missing_latest_key_does_not_crash(self, tmp_path: Path):
        """payload 结构异常（无 latest）不抛。"""
        cfg = _bootstrap_min_project(tmp_path)
        ink = tmp_path / ".ink"
        ink.mkdir(parents=True, exist_ok=True)
        (ink / "reflections.json").write_text(
            json.dumps({"history": []}, ensure_ascii=False), encoding="utf-8"
        )
        manager = ContextManager(cfg)

        pack = manager._build_pack(1)
        assert pack["reflections"] == {}
