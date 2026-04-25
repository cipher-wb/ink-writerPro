#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for hook contract schema validation and outline backfill."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from hook_contract import (
    VALID_HOOK_TYPES,
    HookContract,
    ValidationError,
    extract_hook_contract_from_outline,
    parse_hook_contract,
    validate_chapter_outline,
    validate_volume_outline,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_CONTRACT_LINE = "类型=mystery | 兑现锚点=第5章 | 兑现摘要=揭示身份"

VALID_CHAPTER_BLOCK = textwrap.dedent("""\
    ### 第 3 章：暗夜追踪
    - 目标: 跟踪线索
    - 阻力: 敌人埋伏
    - 代价: 受伤
    - 时间锚点: 末世第3天 夜间
    - 章内时间跨度: 3小时
    - 与上章时间差: 紧接
    - 倒计时状态: 无
    - 爽点: 战斗 - 主角反杀埋伏者→敌人震惊→围观佩服
    - 爽点执行: 铺垫来源:第2章 | 信息差:读者知主角有后手但敌人不知 | 预期读者情绪:解气
    - 压扬标记: 扬
    - Strand: Quest
    - 反派层级: 小
    - 视角/主角: 主角A
    - 关键实体: 暗夜猎手
    - 本章变化: 获得关键情报
    - 章末未闭合问题: 情报指向更大阴谋
    - 钩子: 悬念钩 - 情报揭示幕后黑手
    - 钩子契约: 类型=mystery | 兑现锚点=第5章 | 兑现摘要=揭示幕后黑手身份
""")

MISSING_CONTRACT_BLOCK = textwrap.dedent("""\
    ### 第 7 章：风暴前夕
    - 目标: 整合力量
    - 阻力: 内部分歧
    - 代价: 放弃部分利益
    - 钩子: 危机钩 - 敌军压境
""")

INVALID_TYPE_BLOCK = textwrap.dedent("""\
    ### 第 10 章：终极对决
    - 钩子契约: 类型=thriller | 兑现锚点=第11章 | 兑现摘要=最终决战
""")

TWO_CHAPTER_VOLUME = textwrap.dedent("""\
    ## 第一卷

    ### 第 1 章：开端
    - 目标: 引入世界
    - 钩子: 悬念钩 - 神秘人出现
    - 钩子契约: 类型=mystery | 兑现锚点=第3章 | 兑现摘要=神秘人身份揭晓

    ### 第 2 章：冲突
    - 目标: 首次冲突
    - 钩子: 危机钩 - 敌人来袭
""")


# ---------------------------------------------------------------------------
# parse_hook_contract
# ---------------------------------------------------------------------------

class TestParseHookContract:
    def test_valid_line(self):
        result = parse_hook_contract(VALID_CONTRACT_LINE)
        assert result is not None
        assert result.hook_type == "mystery"
        assert result.anchor_chapter == 5
        assert result.payoff_summary == "揭示身份"

    def test_all_valid_types(self):
        for hook_type in VALID_HOOK_TYPES:
            line = f"类型={hook_type} | 兑现锚点=第10章 | 兑现摘要=测试"
            result = parse_hook_contract(line)
            assert result is not None
            assert result.hook_type == hook_type

    def test_missing_type(self):
        line = "兑现锚点=第5章 | 兑现摘要=揭示身份"
        assert parse_hook_contract(line) is None

    def test_missing_anchor(self):
        line = "类型=mystery | 兑现摘要=揭示身份"
        assert parse_hook_contract(line) is None

    def test_missing_summary(self):
        line = "类型=mystery | 兑现锚点=第5章"
        assert parse_hook_contract(line) is None

    def test_empty_string(self):
        assert parse_hook_contract("") is None

    def test_case_insensitive_type(self):
        line = "类型=MYSTERY | 兑现锚点=第5章 | 兑现摘要=揭示身份"
        result = parse_hook_contract(line)
        assert result is not None
        assert result.hook_type == "mystery"


# ---------------------------------------------------------------------------
# extract_hook_contract_from_outline
# ---------------------------------------------------------------------------

class TestExtractHookContract:
    def test_valid_block(self):
        contract = extract_hook_contract_from_outline(VALID_CHAPTER_BLOCK)
        assert contract is not None
        assert contract.hook_type == "mystery"
        assert contract.anchor_chapter == 5

    def test_missing_contract(self):
        contract = extract_hook_contract_from_outline(MISSING_CONTRACT_BLOCK)
        assert contract is None

    def test_bullet_variants(self):
        for bullet in ["- ", "* ", "· "]:
            block = f"{bullet}钩子契约: 类型=crisis | 兑现锚点=第2章 | 兑现摘要=危机爆发"
            contract = extract_hook_contract_from_outline(block)
            assert contract is not None
            assert contract.hook_type == "crisis"


# ---------------------------------------------------------------------------
# validate_chapter_outline
# ---------------------------------------------------------------------------

class TestValidateChapterOutline:
    def test_valid_chapter_no_errors(self):
        errors = validate_chapter_outline(VALID_CHAPTER_BLOCK, 3)
        assert errors == []

    def test_missing_contract_error(self):
        errors = validate_chapter_outline(MISSING_CONTRACT_BLOCK, 7)
        assert len(errors) == 1
        assert errors[0].chapter_num == 7
        assert "缺少钩子契约" in errors[0].message

    def test_invalid_type_error(self):
        errors = validate_chapter_outline(INVALID_TYPE_BLOCK, 10)
        assert len(errors) == 1
        assert errors[0].chapter_num == 10
        assert "thriller" in errors[0].message

    def test_empty_block(self):
        errors = validate_chapter_outline("### 第 99 章：空章\n", 99)
        assert len(errors) >= 1


# ---------------------------------------------------------------------------
# validate_volume_outline
# ---------------------------------------------------------------------------

class TestValidateVolumeOutline:
    def test_mixed_volume(self):
        errors = validate_volume_outline(TWO_CHAPTER_VOLUME)
        assert len(errors) == 1
        assert errors[0].chapter_num == 2

    def test_all_valid(self):
        vol = textwrap.dedent("""\
            ### 第 1 章：开端
            - 钩子契约: 类型=mystery | 兑现锚点=第3章 | 兑现摘要=悬念揭晓

            ### 第 2 章：发展
            - 钩子契约: 类型=crisis | 兑现锚点=第4章 | 兑现摘要=危机解除
        """)
        errors = validate_volume_outline(vol)
        assert errors == []

    def test_empty_text(self):
        errors = validate_volume_outline("")
        assert errors == []


# ---------------------------------------------------------------------------
# VALID_HOOK_TYPES constant
# ---------------------------------------------------------------------------

class TestHookTypes:
    def test_five_types(self):
        assert len(VALID_HOOK_TYPES) == 5

    def test_expected_types(self):
        expected = {"crisis", "mystery", "emotion", "choice", "desire"}
        assert VALID_HOOK_TYPES == expected

    def test_aligned_with_hook_patterns(self):
        patterns_path = Path(__file__).resolve().parents[2] / "data" / "hook_patterns.json"
        if not patterns_path.exists():
            pytest.skip("hook_patterns.json not found")
        data = json.loads(patterns_path.read_text(encoding="utf-8"))
        pattern_types = set(data["stats"]["by_type"].keys())
        assert pattern_types == VALID_HOOK_TYPES


# ---------------------------------------------------------------------------
# HookContract dataclass
# ---------------------------------------------------------------------------

class TestHookContractDataclass:
    def test_fields(self):
        c = HookContract(hook_type="crisis", anchor_chapter=10, payoff_summary="危机解除")
        assert c.hook_type == "crisis"
        assert c.anchor_chapter == 10
        assert c.payoff_summary == "危机解除"

    def test_equality(self):
        a = HookContract("mystery", 5, "身份揭晓")
        b = HookContract("mystery", 5, "身份揭晓")
        assert a == b


# ---------------------------------------------------------------------------
# migrate.py v7→v8
# ---------------------------------------------------------------------------

class TestMigrateV7toV8:
    def test_migration_adds_hook_contract_config(self, tmp_path):
        state = {
            "schema_version": 7,
            "harness_config": {
                "computational_gate_enabled": True,
                "reader_verdict_mode": "core",
                "reader_verdict_thresholds": {"pass": 32, "enhance": 25, "rewrite_min": 0},
            },
        }
        state_path = tmp_path / ".ink" / "state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps(state), encoding="utf-8")

        from migrate import run_migrations
        result = run_migrations(state_path)
        assert result["schema_version"] >= 8
        assert "hook_contract_config" in result
        config = result["hook_contract_config"]
        assert config["enabled"] is True
        assert set(config["valid_types"]) == VALID_HOOK_TYPES
        assert config["outline_backfilled"] is False
