"""US-008: seed_thresholds.yaml tiers 桶查找集成测试。

验证:
  1. tier=explosive_hit → 命中最严阈值桶
  2. tier=standard → 命中标准阈值桶
  3. tier=None → 沿用原 scenes bucket
  4. tier 不存在的桶 → 回退默认
"""

from __future__ import annotations

import textwrap

import pytest
from ink_writer.prose.directness_checker import (
    _DEFAULT_THRESHOLDS,
    _resolve_scene_bucket,
    clear_cache,
    load_thresholds,
    run_directness_check,
)

_CLEAN_PROSE = textwrap.dedent(
    """
    他推开门，走进屋子，看见桌上摆着三封信。
    "你来了。"老人抬起头，把茶杯推到他面前。
    他拉开椅子，坐下，伸手摸了一下最上面那封信的封口。
    "这封是林老板寄的。"老人慢慢开口，"他说账目对不上。"
    他没有立刻回答。他把信封翻了个面，看了看邮戳的日期。
    "我去一趟苏州。"他站起来，把剑扛上肩，"三天内回来。"
    老人点了点头，从抽屉里取出一袋银子，递过去：
    "路上小心，别惹钱帮的人。"
    """
).strip()


# ---------------------------------------------------------------------------
# Tier bucket resolution unit tests
# ---------------------------------------------------------------------------


class TestResolveSceneBucketTier:
    """_resolve_scene_bucket tier 参数单元测试。"""

    def setup_method(self) -> None:
        clear_cache()

    def _buckets(self) -> dict:
        """模拟 YAML scenes 段。"""
        return {
            "golden_three": {
                "thresholds": {
                    "D1_rhetoric_density": {
                        "direction": "lower_is_better",
                        "green_max": 0.02,
                        "yellow_max": 0.04,
                    },
                },
            },
            "other": {
                "thresholds": {
                    "D1_rhetoric_density": {
                        "direction": "lower_is_better",
                        "green_max": 0.03,
                        "yellow_max": 0.05,
                    },
                },
            },
            "combat": {"inherits_from": "golden_three"},
        }

    def _tiers(self) -> dict:
        """模拟 YAML tiers 段。"""
        return {
            "explosive_hit": {
                "thresholds": {
                    "D1_rhetoric_density": {
                        "direction": "lower_is_better",
                        "green_max": 0.01,
                        "yellow_max": 0.02,
                    },
                },
            },
            "standard": {
                "thresholds": {
                    "D1_rhetoric_density": {
                        "direction": "lower_is_better",
                        "green_max": 0.03,
                        "yellow_max": 0.05,
                    },
                },
            },
        }

    def test_tier_explosive_hit_resolves(self) -> None:
        """tier=explosive_hit → 命中最严桶。"""
        name, thresholds = _resolve_scene_bucket(
            "combat", 99, self._buckets(),
            directness_tier="explosive_hit", tiers=self._tiers(),
        )
        assert "explosive_hit" in name
        assert thresholds["D1_rhetoric_density"]["green_max"] == 0.01

    def test_tier_standard_resolves(self) -> None:
        """tier=standard → 命中标准桶。"""
        name, thresholds = _resolve_scene_bucket(
            "combat", 99, self._buckets(),
            directness_tier="standard", tiers=self._tiers(),
        )
        assert "standard" in name
        assert thresholds["D1_rhetoric_density"]["green_max"] == 0.03

    def test_tier_none_uses_scene_bucket(self) -> None:
        """tier=None → 沿用 scene bucket。"""
        name, thresholds = _resolve_scene_bucket(
            "golden_three", 1, self._buckets(),
            directness_tier=None, tiers=self._tiers(),
        )
        assert "golden_three" in name
        assert thresholds["D1_rhetoric_density"]["green_max"] == 0.02

    def test_tier_unknown_falls_back_to_default(self) -> None:
        """不存在的 tier → 回退默认阈值。"""
        name, thresholds = _resolve_scene_bucket(
            "combat", 99, self._buckets(),
            directness_tier="nonexistent", tiers=self._tiers(),
        )
        assert name == "default"
        assert thresholds is _DEFAULT_THRESHOLDS

    def test_tier_without_tiers_dict_falls_back(self) -> None:
        """tiers=None 时 tier 不生效，回退 scene bucket。"""
        name, _thresholds = _resolve_scene_bucket(
            "golden_three", 1, self._buckets(),
            directness_tier="explosive_hit", tiers=None,
        )
        # tiers=None → 跳过 tier lookup，走原 scene bucket
        assert "golden_three" in name

    def test_combat_inherits_from_golden_three_without_tier(self) -> None:
        """tier=None 时 combat 继承 golden_three。"""
        name, _thresholds = _resolve_scene_bucket(
            "combat", 99, self._buckets(),
            directness_tier=None, tiers=self._tiers(),
        )
        assert "golden_three" in name

    def test_chapter_1_to_3_without_scene_mode_resolves_golden_three(self) -> None:
        """chapter_no=1..3 + scene_mode=None → golden_three。"""
        name, _thresholds = _resolve_scene_bucket(
            None, 2, self._buckets(),
            directness_tier=None, tiers=self._tiers(),
        )
        assert "golden_three" in name

    def test_chapter_beyond_3_without_scene_mode_resolves_default(self) -> None:
        """chapter_no>3 + scene_mode=None → default。"""
        name, thresholds = _resolve_scene_bucket(
            None, 99, self._buckets(),
            directness_tier=None, tiers=self._tiers(),
        )
        assert name == "default"
        assert thresholds is _DEFAULT_THRESHOLDS


# ---------------------------------------------------------------------------
# End-to-end: real YAML + run_directness_check
# ---------------------------------------------------------------------------


class TestTierEndToEnd:
    """端到端：真实 YAML 加载 + run_directness_check tier 桶命中。"""

    def setup_method(self) -> None:
        clear_cache()

    def test_explosive_hit_uses_tighter_thresholds(self) -> None:
        """tier=explosive_hit 阈值比 standard 严格。"""
        loaded = load_thresholds()
        tiers = loaded.get("tiers", {})
        explosive = tiers.get("explosive_hit", {}).get("thresholds", {})
        standard = tiers.get("standard", {}).get("thresholds", {})

        assert explosive, "YAML 缺少 tiers.explosive_hit"
        assert standard, "YAML 缺少 tiers.standard"

        # explosive 所有 lower_is_better 维度都应 ≤ standard
        for key in ["D1_rhetoric_density", "D2_adj_verb_ratio",
                     "D3_abstract_per_100_chars", "D6_nesting_depth",
                     "D7_modifier_chain_length"]:
            e_g = explosive.get(key, {}).get("green_max", 999)
            s_g = standard.get(key, {}).get("green_max", 999)
            assert e_g <= s_g, (
                f"{key}: explosive green_max={e_g} > standard green_max={s_g}"
            )

    def test_run_with_explosive_hit_reports_tier_bucket(self) -> None:
        """run_directness_check(tier='explosive_hit') → bucket_used 含 tier:explosive_hit。"""
        report = run_directness_check(
            _CLEAN_PROSE,
            chapter_no=5,
            scene_mode="combat",
            directness_tier="explosive_hit",
        )
        assert not report.skipped
        bucket = report.metrics_raw.get("bucket_used", "")
        assert "explosive_hit" in bucket

    def test_run_with_standard_reports_tier_bucket(self) -> None:
        """run_directness_check(tier='standard') → bucket_used 含 tier:standard。"""
        report = run_directness_check(
            _CLEAN_PROSE,
            chapter_no=5,
            scene_mode="combat",
            directness_tier="standard",
        )
        assert not report.skipped
        bucket = report.metrics_raw.get("bucket_used", "")
        assert "standard" in bucket

    def test_run_without_tier_uses_scene_bucket(self) -> None:
        """run_directness_check(tier=None) → bucket_used 含 golden_three。"""
        report = run_directness_check(
            _CLEAN_PROSE,
            chapter_no=1,
            scene_mode="golden_three",
            directness_tier=None,
        )
        assert not report.skipped
        bucket = report.metrics_raw.get("bucket_used", "")
        assert "golden_three" in bucket

    def test_d6_d7_still_scored_in_tier_mode(self) -> None:
        """tier 模式下 D6/D7 仍然参与评分。"""
        report = run_directness_check(
            _CLEAN_PROSE,
            chapter_no=5,
            directness_tier="explosive_hit",
        )
        assert not report.skipped
        keys = {d.key for d in report.dimensions}
        assert "D6_nesting_depth" in keys
        assert "D7_modifier_chain_length" in keys
        assert "D6_nesting_depth" in report.metrics_raw
        assert "D7_modifier_chain_length" in report.metrics_raw
