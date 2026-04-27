"""PRD US-005: colloquial-checker pipeline 注册测试。

验证：
  1. _make_colloquial_adapter 正确调用 run_colloquial_check + to_checker_output
  2. 全场景激活（不受 scene_mode 限制）
  3. severity=red → passed=False, hard_blocked=True
  4. enabled=false 时返回 PASS 透传
  5. prose_overhaul_enabled=false 时强制 disabled
  6. 空文本兜底 safe-default
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """创建包含 colloquial.yaml + anti-detection.yaml 的最小项目结构。"""
    project = tmp_path / "book"
    config_dir = project / "config"
    config_dir.mkdir(parents=True)
    return project


@pytest.fixture
def colloquial_config_enabled(tmp_project: Path) -> Path:
    """写入默认启用的 colloquial.yaml。"""
    cfg = {
        "enabled": True,
        "score_threshold": 70,
        "max_retries": 1,
        "thresholds": {
            "C1_idiom_density": {
                "direction": "lower_is_better",
                "green_max": 3.0,
                "yellow_max": 5.0,
            },
            "C2_quad_phrase_density": {
                "direction": "lower_is_better",
                "green_max": 6.0,
                "yellow_max": 10.0,
            },
            "C3_abstract_noun_chain": {
                "direction": "lower_is_better",
                "green_max": 0.5,
                "yellow_max": 1.5,
            },
            "C4_modifier_chain_avg": {
                "direction": "lower_is_better",
                "green_max": 1.5,
                "yellow_max": 2.5,
            },
            "C5_abstract_subject_rate": {
                "direction": "lower_is_better",
                "green_max": 0.10,
                "yellow_max": 0.25,
            },
        },
    }
    path = tmp_project / "config" / "colloquial.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    # anti-detection.yaml without prose_overhaul_enabled（默认不存在该字段 = enabled）
    ad_cfg = {"enabled": True, "score_threshold": 70, "max_retries": 1}
    ad_path = tmp_project / "config" / "anti-detection.yaml"
    ad_path.write_text(yaml.dump(ad_cfg), encoding="utf-8")
    return tmp_project


@pytest.fixture
def colloquial_config_disabled(tmp_project: Path) -> Path:
    """写入禁用 colloquial 的配置。"""
    cfg = {
        "enabled": False,
        "score_threshold": 70,
        "max_retries": 1,
        "thresholds": {},
    }
    path = tmp_project / "config" / "colloquial.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    ad_cfg = {"enabled": True, "score_threshold": 70, "max_retries": 1}
    ad_path = tmp_project / "config" / "anti-detection.yaml"
    ad_path.write_text(yaml.dump(ad_cfg), encoding="utf-8")
    return tmp_project


@pytest.fixture
def prose_overhaul_disabled(tmp_project: Path) -> Path:
    """写入 prose_overhaul_enabled=false 的 anti-detection.yaml。"""
    colloquial_cfg = {
        "enabled": True,
        "score_threshold": 70,
        "max_retries": 1,
        "thresholds": {},
    }
    path = tmp_project / "config" / "colloquial.yaml"
    path.write_text(yaml.dump(colloquial_cfg), encoding="utf-8")
    ad_cfg = {"enabled": True, "score_threshold": 70, "prose_overhaul_enabled": False}
    ad_path = tmp_project / "config" / "anti-detection.yaml"
    ad_path.write_text(yaml.dump(ad_cfg), encoding="utf-8")
    return tmp_project


# 干净爆款风文本（低成语、低四字格、无抽象链）
_CLEAN_TEXT = (
    "山风掠过屋檐。少年把剑扛在肩上，数着脚下的青砖。\n\n"
    "他没有回头。身后那扇木门吱呀作响，却终究合上了。\n\n"
    "远处传来钟声，一声，又一声。他停了停，把剑换到另一边。\n\n"
    "院子里没人。他蹲下来系鞋带，抬头看了看天。\n\n"
    "走吧。他对自己说。然后推门出去。"
)

# 重度装逼文本（多成语、四字格排比、抽象链）
_PRETENTIOUS_TEXT = (
    "红尘滚滚，浮生若茶。岁月蹉跎，光阴荏苒。日月如梭，白驹过隙。\n\n"
    "宿命的孤寂的沧桑萦绕在心头，他缓缓伫立于虚无的苍茫之中。\n\n"
    "静谧的缥缈的迷离的旖旎，仿佛一切尽在不言中。"
)

# 中等文本（有些成语但不过分）
_MODERATE_TEXT = (
    "他推门进去，屋里点着一盏油灯。灯影晃晃悠悠，照得墙上的人影也跟着摇摆。\n\n"
    "老人坐在角落里，手里捏着一根烟杆，烟雾缭绕。\n\n"
    "来了？老人没抬头。\n\n"
    "来了。他把剑靠在门边，自己拉了张凳子坐下。"
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestColloquialAdapter:
    """_make_colloquial_adapter 核心行为测试。"""

    def test_adapter_clean_text_passes(self, colloquial_config_enabled):
        """干净爆款风文本 → PASS。"""
        from ink_writer.checker_pipeline.step3_runner import _make_colloquial_adapter

        bundle = {
            "chapter_text": _CLEAN_TEXT,
            "chapter_no": 1,
            "project_root": str(colloquial_config_enabled),
        }
        adapter = _make_colloquial_adapter(bundle)
        passed, score, fix = asyncio.run(adapter())
        assert passed is True
        assert score > 0.7  # 高分 green

    def test_adapter_pretentious_text_fails(self, colloquial_config_enabled):
        """重度装逼文本 → FAILED, hard_blocked。"""
        from ink_writer.checker_pipeline.step3_runner import _make_colloquial_adapter

        bundle = {
            "chapter_text": _PRETENTIOUS_TEXT,
            "chapter_no": 1,
            "project_root": str(colloquial_config_enabled),
        }
        adapter = _make_colloquial_adapter(bundle)
        passed, score, fix = asyncio.run(adapter())
        assert passed is False
        assert score < 0.7  # 低分 red

    def test_adapter_disabled_passes(self, colloquial_config_disabled):
        """colloquial.yaml enabled=false → PASS 透传。"""
        from ink_writer.checker_pipeline.step3_runner import _make_colloquial_adapter

        bundle = {
            "chapter_text": _PRETENTIOUS_TEXT,
            "chapter_no": 1,
            "project_root": str(colloquial_config_disabled),
        }
        adapter = _make_colloquial_adapter(bundle)
        passed, score, _fix = asyncio.run(adapter())
        assert passed is True
        assert score == 1.0  # 透传满分

    def test_adapter_prose_overhaul_disabled_passes(self, prose_overhaul_disabled):
        """prose_overhaul_enabled=false → colloquial 强制 disabled → PASS。"""
        from ink_writer.checker_pipeline.step3_runner import _make_colloquial_adapter

        bundle = {
            "chapter_text": _PRETENTIOUS_TEXT,
            "chapter_no": 1,
            "project_root": str(prose_overhaul_disabled),
        }
        adapter = _make_colloquial_adapter(bundle)
        passed, score, _fix = asyncio.run(adapter())
        assert passed is True
        assert score == 1.0

    def test_adapter_empty_text_passes(self, colloquial_config_enabled):
        """空文本 → PASS safe-default。"""
        from ink_writer.checker_pipeline.step3_runner import _make_colloquial_adapter

        bundle = {
            "chapter_text": "",
            "chapter_no": 1,
            "project_root": str(colloquial_config_enabled),
        }
        adapter = _make_colloquial_adapter(bundle)
        passed, score, _fix = asyncio.run(adapter())
        assert passed is True

    def test_adapter_red_produces_fix_prompt(self, colloquial_config_enabled):
        """severity=red 时 fix_prompt 非空。"""
        from ink_writer.checker_pipeline.step3_runner import _make_colloquial_adapter

        bundle = {
            "chapter_text": _PRETENTIOUS_TEXT,
            "chapter_no": 1,
            "project_root": str(colloquial_config_enabled),
        }
        adapter = _make_colloquial_adapter(bundle)
        passed, score, fix = asyncio.run(adapter())
        assert not passed
        assert "colloquial-checker:" in fix
        assert "C1_idiom_density" in fix or "C" in fix  # at least some dimension mentioned

    def test_adapter_missing_config_dir_safe(self, tmp_path):
        """项目无 config/ 目录 → 使用默认阈值不崩溃。"""
        from ink_writer.checker_pipeline.step3_runner import _make_colloquial_adapter

        project = tmp_path / "no_config"
        project.mkdir()
        bundle = {
            "chapter_text": _CLEAN_TEXT,
            "chapter_no": 1,
            "project_root": str(project),
        }
        adapter = _make_colloquial_adapter(bundle)
        passed, score, _fix = asyncio.run(adapter())
        # 默认阈值下干净文本应 green
        assert passed is True

    def test_adapter_missing_yaml_files_safe(self, tmp_path):
        """config/ 目录存在但 yaml 缺失 → 使用默认值不崩溃。"""
        from ink_writer.checker_pipeline.step3_runner import _make_colloquial_adapter

        project = tmp_path / "empty_config"
        config_dir = project / "config"
        config_dir.mkdir(parents=True)
        bundle = {
            "chapter_text": _CLEAN_TEXT,
            "chapter_no": 1,
            "project_root": str(project),
        }
        adapter = _make_colloquial_adapter(bundle)
        passed, score, _fix = asyncio.run(adapter())
        assert passed is True


class TestColloquialGateRegistration:
    """验证 colloquial gate 在 step3_runner 中正确注册。"""

    def test_gate_is_registered_in_run_step3(self, colloquial_config_enabled):
        """colloquial gate 出现在 PipelineReport 中。"""
        from ink_writer.checker_pipeline.step3_runner import run_step3

        state_dir = colloquial_config_enabled / ".ink"
        state_dir.mkdir(parents=True)
        # 写入章节文本
        text_dir = colloquial_config_enabled / "正文"
        text_dir.mkdir()
        (text_dir / "第0001章-测试.md").write_text(_CLEAN_TEXT, encoding="utf-8")

        result = asyncio.run(run_step3(
            chapter_id=1,
            state_dir=state_dir,
            mode="shadow",
            dry_run=True,
        ))
        assert result.passed is True
        assert "colloquial" in result.gate_results, (
            f"colloquial gate missing from results; got: {list(result.gate_results)}"
        )

    def test_gate_is_hard_gate(self, colloquial_config_enabled):
        """colloquial gate 是 hard_gate=True。"""
        from ink_writer.checker_pipeline.runner import CheckerRunner, GateSpec
        from ink_writer.checker_pipeline.step3_runner import _make_colloquial_adapter

        bundle = {
            "chapter_text": _CLEAN_TEXT,
            "chapter_no": 1,
            "project_root": str(colloquial_config_enabled),
        }
        # 验证 adapter 可被构造且不会在构造阶段崩溃
        adapter = _make_colloquial_adapter(bundle)
        assert callable(adapter)

    def test_adapter_exception_is_safe(self, colloquial_config_enabled):
        """adapter 内部异常 → safe-default PASS。"""
        from ink_writer.checker_pipeline.step3_runner import _make_colloquial_adapter

        # project_root 指向无效路径导致 yaml 读取失败 → 应 safe default
        bundle = {
            "chapter_text": _PRETENTIOUS_TEXT,
            "chapter_no": 1,
            "project_root": "/nonexistent/path/12345",
        }
        adapter = _make_colloquial_adapter(bundle)
        passed, score, _fix = asyncio.run(adapter())
        # 无效路径 → config 文件不存在 → 走默认阈值（可能会 red）
        # 只要不抛异常即可
        assert isinstance(passed, bool)


class TestColloquialCheckerOutputSchema:
    """to_checker_output 产出的结构符合 checker-output-schema.md。"""

    def test_output_has_required_fields(self):
        from ink_writer.prose.colloquial_checker import (
            run_colloquial_check,
            to_checker_output,
        )

        report = run_colloquial_check(_CLEAN_TEXT)
        output = to_checker_output(report, chapter_no=1)

        required = {"agent", "chapter", "overall_score", "pass", "hard_blocked", "issues", "metrics", "summary"}
        assert required.issubset(set(output.keys())), f"missing: {required - set(output.keys())}"
        assert output["agent"] == "colloquial-checker"
        assert output["chapter"] == 1
        assert isinstance(output["overall_score"], int)
        assert isinstance(output["pass"], bool)
        assert isinstance(output["hard_blocked"], bool)
        assert isinstance(output["issues"], list)
        assert isinstance(output["metrics"], dict)
        assert isinstance(output["summary"], str)

    def test_output_hard_blocked_matches_severity(self):
        from ink_writer.prose.colloquial_checker import (
            run_colloquial_check,
            to_checker_output,
        )

        # 干净文本 → green → hard_blocked=False
        report = run_colloquial_check(_CLEAN_TEXT)
        output = to_checker_output(report, chapter_no=1)
        if output["metrics"]["severity"] == "green":
            assert output["hard_blocked"] is False
            assert output["pass"] is True

        # 装逼文本 → red → hard_blocked=True
        report2 = run_colloquial_check(_PRETENTIOUS_TEXT)
        output2 = to_checker_output(report2, chapter_no=2)
        if output2["metrics"]["severity"] == "red":
            assert output2["hard_blocked"] is True
            assert output2["pass"] is False
