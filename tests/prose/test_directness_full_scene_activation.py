"""PRD US-006: directness-checker 全场景激活验证。

验证:
  1. slow_build / emotional / 普通章现在全部激活并打分（不再 skipped）
  2. directness_skip 向后兼容
  3. directness_tier 影响阈值桶选择
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from ink_writer.prose.directness_checker import (
    clear_cache,
    is_activated,
    run_directness_check,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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

_SLOW_BUILD_PROSE = textwrap.dedent(
    """
    夜色渐浓，街灯一盏接一盏亮了起来。青石板路被露水打湿，映着暖黄的光。
    他沿着河岸慢慢走，脚下是几百年的老石板，磨得发亮。
    河边有洗衣的妇人，有钓鱼的老人。他一个一个看过去，像在找什么人。
    风吹过来，带着河水的腥味和远处炊烟的味道。他停下脚步，靠着栏杆。
    桥下有小船经过，船夫撑着竹竿，嘴里哼着不成调的歌。
    他掏出烟袋，点了一锅烟，慢慢抽着。天完全黑了。
    """
).strip()

_EMOTIONAL_PROSE = textwrap.dedent(
    """
    她站在窗前，看着院子里的海棠。花已经谢了，满地花瓣，被雨水浸得发黑。
    他没有回来。三年了，他在信里说春天就回，可春天来过了，又走了。
    她把信折好放进抽屉里，抽屉里已经攒了十七封。每一封都只有四个字：一切安好。
    她看着他坐过的椅子，吹过的酒壶，翻过的书。它们都在原处，落了一层灰。
    她不想擦了。她也坐进了那把椅子，闭上眼睛，想听他的声音。只有风声。
    """
).strip()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFullSceneActivation:
    """AC 1-3: 全场景激活。"""

    @pytest.mark.parametrize("scene_mode", ["slow_build", "emotional", "daily", "transition", None])
    def test_all_scenes_activate(self, scene_mode):
        """所有 scene_mode 激活并打分，不再返回 skipped。"""
        report = run_directness_check(
            _CLEAN_PROSE,
            chapter_no=10,
            scene_mode=scene_mode,
        )
        assert not report.skipped, (
            f"scene_mode={scene_mode!r} 应该激活但返回 skipped: {report.reason}"
        )
        assert report.passed is True
        assert len(report.dimensions) == 5
        assert report.severity in {"green", "yellow"}

    @pytest.mark.parametrize("chapter_no", [1, 2, 3, 4, 10, 50, 100])
    def test_all_chapters_activate(self, chapter_no):
        """所有章节号激活，不限 [1,3]。"""
        report = run_directness_check(
            _CLEAN_PROSE,
            chapter_no=chapter_no,
            scene_mode=None,
        )
        assert not report.skipped
        assert report.passed is True

    def test_slow_build_fixture_activates(self):
        """slow_build 章节能正常评分。"""
        report = run_directness_check(
            _SLOW_BUILD_PROSE,
            chapter_no=42,
            scene_mode="slow_build",
        )
        assert not report.skipped, f"slow_build 应激活但 skipped: {report.reason}"
        assert report.passed is True

    def test_emotional_fixture_activates(self):
        """emotional 章节能正常评分。"""
        report = run_directness_check(
            _EMOTIONAL_PROSE,
            chapter_no=15,
            scene_mode="emotional",
        )
        assert not report.skipped, f"emotional 应激活但 skipped: {report.reason}"
        # emotional fixture 较文学化，可能 yellow，但不应 red
        assert report.severity in {"green", "yellow"}

    def test_no_scene_mode_default_activates(self):
        """默认章（无 scene_mode）也激活打分。"""
        report = run_directness_check(
            _CLEAN_PROSE,
            chapter_no=20,
            scene_mode=None,
        )
        assert not report.skipped
        assert report.passed is True


class TestDirectnessSkipBackwardCompat:
    """AC 5: directness_skip 向后兼容。"""

    def test_skip_true_returns_skipped(self):
        report = run_directness_check(
            _CLEAN_PROSE,
            chapter_no=1,
            scene_mode="golden_three",
            directness_skip=True,
        )
        assert report.skipped is True
        assert report.passed is True
        assert report.dimensions == ()

    def test_skip_true_even_golden_three_skipped(self):
        """即便是黄金三章，directness_skip=true 也跳过。"""
        report = run_directness_check(
            _CLEAN_PROSE,
            chapter_no=1,
            scene_mode="golden_three",
            directness_skip=True,
        )
        assert report.skipped is True

    def test_skip_false_always_activates(self):
        """directness_skip=False 始终激活。"""
        for scene in ("golden_three", "combat", "slow_build", "emotional", None):
            report = run_directness_check(
                _CLEAN_PROSE,
                chapter_no=1 if scene == "golden_three" else 50,
                scene_mode=scene,
                directness_skip=False,
            )
            assert not report.skipped


class TestDirectnessTier:
    """AC 6: directness_tier 桶选择。"""

    def test_tier_explosive_hit_falls_back_to_scenes_lookup(self):
        """tier=explosive_hit（默认）→ YAML 无 tiers.explosive_hit 时回退 default（场景桶逻辑正常运行）。

        注：US-008 将新增 tiers.explosive_hit 桶，届时本测试改为验证 tier 桶命中。
        """
        report = run_directness_check(
            _CLEAN_PROSE,
            chapter_no=5,
            scene_mode="combat",
            directness_tier="explosive_hit",
        )
        assert not report.skipped
        bucket = report.metrics_raw.get("bucket_used", "")
        # explosive_hit tier YAML 段未创建 → 回退 default
        assert "default" in bucket

    def test_tier_standard_falls_back(self):
        """tier=standard → YAML 无 tiers.standard 时回退 default。"""
        report = run_directness_check(
            _CLEAN_PROSE,
            chapter_no=5,
            scene_mode="combat",
            directness_tier="standard",
        )
        assert not report.skipped
        bucket = report.metrics_raw.get("bucket_used", "")
        # standard tier YAML 段未创建 → 回退 default
        assert "standard" in bucket or "other" in bucket or "default" in bucket

    def test_tier_none_behaves_same_as_old_lookup(self):
        """tier=None → 沿用原 scenes bucket 逻辑。"""
        report = run_directness_check(
            _CLEAN_PROSE,
            chapter_no=1,
            scene_mode="golden_three",
            directness_tier=None,
        )
        assert not report.skipped
        bucket = report.metrics_raw.get("bucket_used", "")
        assert "golden_three" in bucket
