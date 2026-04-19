#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""US-013 (v18): Extended zero-tolerance tests with paired positive + negative samples.

PRD AC4 requirement
-------------------
> 测试 tests/anti_detection/test_zt_extended.py 每条 ZT 给 positive（应拦截）+ negative
> （误伤样本）共 20+ case

For each of the 8 zero-tolerance rules loaded from ``config/anti-detection.yaml``
this module ships at least one positive (text MUST trigger the rule) and at
least one negative (a near-miss that MUST NOT trigger the rule). The negatives
are written as concrete prose so any future rule tightening that broadens the
regex too aggressively will surface here as a regression.

Baseline calibration note (PRD AC3)
-----------------------------------
``conjunction_density_max = 2.5 / 千字`` was calibrated against the 114-book
qidian benchmark documented in ``memory/project_quality_upgrade.md`` (3,351+
chapters / 7.12M chars). Distribution facts that informed the threshold:

* p50 conjunction density across benchmark = ~1.3 / kchars
* p90 = ~2.4 / kchars
* AI-generated control set (前 60 章 GPT-4 baseline) p50 = ~3.8 / kchars

A threshold of 2.5 keeps human-prose chapters below the line while flagging
the AI baseline. ``test_threshold_within_human_baseline`` below pins this
intent so a future bump above 3.0 (which would silently let AI-style prose
through) trips the test.

Pure-Python — no LLM call.
"""

from __future__ import annotations

import pytest

from ink_writer.anti_detection.anti_detection_gate import check_zero_tolerance
from ink_writer.anti_detection.config import (
    AntiDetectionConfig,
    load_config,
)
from ink_writer.anti_detection.sentence_diversity import (
    analyze_diversity,
    conjunction_density,
)


@pytest.fixture(scope="module")
def cfg() -> AntiDetectionConfig:
    """Load the on-disk YAML so YAML/test drift is caught immediately."""
    return load_config()


# ---------------------------------------------------------------------------
# Rule inventory guard — keeps test set in lockstep with YAML.
# ---------------------------------------------------------------------------


class TestRuleInventory:
    EXPECTED_RULES = {
        "ZT_TIME_OPENING",
        "ZT_MEANWHILE",
        "ZT_NOT_ONLY_BUT_ALSO",
        "ZT_DESPITE_STILL",
        "ZT_UNDOUBTEDLY",
        "ZT_IN_SHORT",
        "ZT_FIRST_SECOND",
        "ZT_WORTH_MENTIONING",
    }

    def test_eight_rules_loaded(self, cfg: AntiDetectionConfig):
        ids = {r.id for r in cfg.zero_tolerance}
        missing = self.EXPECTED_RULES - ids
        assert not missing, f"YAML missing ZT rules: {missing}"
        assert len(ids) >= 8, f"PRD AC1 requires 8-10 ZT rules, got {len(ids)}"


# ---------------------------------------------------------------------------
# ZT_TIME_OPENING — opening line starts with a time marker.
# ---------------------------------------------------------------------------


class TestZTTimeOpening:
    def test_positive_first_day(self, cfg):
        text = "第三日，林渊背着剑走出山门。\n\n他没有回头。"
        assert check_zero_tolerance(text, cfg) == "ZT_TIME_OPENING"

    def test_positive_next_day(self, cfg):
        text = "次日，山中下起了雪。"
        assert check_zero_tolerance(text, cfg) == "ZT_TIME_OPENING"

    def test_negative_time_in_middle_not_at_start(self, cfg):
        # 时间词出现在第二句不在首行 → 不应误伤
        text = "林渊握紧剑柄，轻轻吸了一口气。\n\n第三日，他终于醒来。"
        # 首行不是时间起手 → ZT_TIME_OPENING 不命中（其他规则也不应命中）
        assert check_zero_tolerance(text, cfg) is None

    def test_negative_action_opening(self, cfg):
        text = "剑光一闪，碎石迸溅。\n\n林渊向前一步，雪花落在他的肩上。"
        assert check_zero_tolerance(text, cfg) is None


# ---------------------------------------------------------------------------
# ZT_MEANWHILE — omniscient cross-cut transition.
# ---------------------------------------------------------------------------


class TestZTMeanwhile:
    def test_positive_meanwhile(self, cfg):
        text = "他拔出长剑。\n\n与此同时，远在千里之外的宗门炸开了锅。"
        assert check_zero_tolerance(text, cfg) == "ZT_MEANWHILE"

    def test_positive_same_moment(self, cfg):
        text = "他屏息而行。\n\n就在同一时间，山门外鼓声大作。"
        assert check_zero_tolerance(text, cfg) == "ZT_MEANWHILE"

    def test_negative_simple_simultaneously(self, cfg):
        # 单独 '同时' 不带 '与此/就在此时' 等组合 → 不应触发
        text = "他抬手挡剑，同时反手一推将对方逼退三步。"
        assert check_zero_tolerance(text, cfg) is None


# ---------------------------------------------------------------------------
# ZT_NOT_ONLY_BUT_ALSO — bookish progressive connector.
# ---------------------------------------------------------------------------


class TestZTNotOnlyButAlso:
    def test_positive_not_only_and(self, cfg):
        text = "他不仅剑法超绝，而且内力浑厚，令满山弟子噤若寒蝉。"
        assert check_zero_tolerance(text, cfg) == "ZT_NOT_ONLY_BUT_ALSO"

    def test_positive_not_only_also(self, cfg):
        text = "她不仅出手极快，还精通阵法，被师门寄予厚望。"
        assert check_zero_tolerance(text, cfg) == "ZT_NOT_ONLY_BUT_ALSO"

    def test_negative_standalone_not_only(self, cfg):
        # '不仅' 单独出现，没有后续 '而且/还' → 不应误伤
        text = "他不仅仅是想赢这一战。他想要的是一个答案。"
        assert check_zero_tolerance(text, cfg) is None

    def test_negative_only_buqie(self, cfg):
        # '不切实际' 等含 '不' 字短语不应被误判
        text = "她抬眼看他，不切实际的念头一闪而过。"
        assert check_zero_tolerance(text, cfg) is None


# ---------------------------------------------------------------------------
# ZT_DESPITE_STILL — textbook concession transition.
# ---------------------------------------------------------------------------


class TestZTDespiteStill:
    def test_positive_jinguan_ruci(self, cfg):
        text = "他伤得很重，几乎站不稳。尽管如此，他依然不肯松开剑柄。"
        assert check_zero_tolerance(text, cfg) == "ZT_DESPITE_STILL"

    def test_positive_although_but(self, cfg):
        text = "虽然身中剧毒，但是他的手仍稳如磐石。"
        assert check_zero_tolerance(text, cfg) == "ZT_DESPITE_STILL"

    def test_negative_standalone_although(self, cfg):
        # '虽然' 但后无 '但是/可是' → 不应触发（短句省略式不是教科书转折）
        text = "虽然他没说话。他的眼神已经够冷。"
        assert check_zero_tolerance(text, cfg) is None

    def test_negative_other_concession_not_listed(self, cfg):
        # '即便如此' 不在规则列表 → 不应被误判
        text = "他知道前路凶险。即便如此，他也只是淡淡笑了一下。"
        assert check_zero_tolerance(text, cfg) is None


# ---------------------------------------------------------------------------
# ZT_UNDOUBTEDLY — omniscient judgment.
# ---------------------------------------------------------------------------


class TestZTUndoubtedly:
    def test_positive_haowuyiwen(self, cfg):
        text = "剑光一闪，尘土翻腾。毫无疑问，这是一记杀招。"
        assert check_zero_tolerance(text, cfg) == "ZT_UNDOUBTEDLY"

    def test_positive_xianeryijian(self, cfg):
        text = "山顶积雪连绵。显而易见，此处已久无人至。"
        assert check_zero_tolerance(text, cfg) == "ZT_UNDOUBTEDLY"

    def test_negative_pov_question(self, cfg):
        # POV 视角的反问句不应被误伤
        text = "他真的会赢吗？林渊握紧拳头，自己也不确定。"
        assert check_zero_tolerance(text, cfg) is None


# ---------------------------------------------------------------------------
# ZT_IN_SHORT — essay-style summary.
# ---------------------------------------------------------------------------


class TestZTInShort:
    def test_positive_in_short(self, cfg):
        text = "剑招如风，步法似影。总而言之，这一战他胜得毫无悬念。"
        assert check_zero_tolerance(text, cfg) == "ZT_IN_SHORT"

    def test_positive_to_sum_up(self, cfg):
        text = "综上所述，此局已无破解之法。"
        assert check_zero_tolerance(text, cfg) == "ZT_IN_SHORT"

    def test_negative_zong_alone(self, cfg):
        # '总' 单字不应触发任何规则
        text = "他总是在最难的时候笑得最从容。"
        assert check_zero_tolerance(text, cfg) is None

    def test_negative_pov_summary_in_dialogue(self, cfg):
        # 角色对话中说"总之"不应被规则误伤（不在列表里）
        text = "「总之，我不会再让她受伤。」林渊低声道。"
        assert check_zero_tolerance(text, cfg) is None


# ---------------------------------------------------------------------------
# ZT_FIRST_SECOND — enumerative list-item sentence.
# ---------------------------------------------------------------------------


class TestZTFirstSecond:
    def test_positive_first_second_last(self, cfg):
        text = (
            "他定下三件事。首先要找到线索，其次确认凶手，"
            "最后才是动手。"
        )
        assert check_zero_tolerance(text, cfg) == "ZT_FIRST_SECOND"

    def test_positive_diyi_dier_disan(self, cfg):
        text = "此中关键有三。第一是时机，第二是位置，第三是心境。"
        assert check_zero_tolerance(text, cfg) == "ZT_FIRST_SECOND"

    def test_negative_shouxian_alone(self, cfg):
        # '首先' 单独使用而无 '其次' 跟随 → 不应触发
        text = "首先要做的，是把剑找回来。"
        assert check_zero_tolerance(text, cfg) is None

    def test_negative_diyi_with_no_dier(self, cfg):
        # '第一' 单独出现而无 '第二/第三' → 不应触发
        text = "他第一次出手就斩落了对方的剑穗。"
        assert check_zero_tolerance(text, cfg) is None


# ---------------------------------------------------------------------------
# ZT_WORTH_MENTIONING — narrator-side reminder.
# ---------------------------------------------------------------------------


class TestZTWorthMentioning:
    def test_positive_zhideyitide(self, cfg):
        text = "值得一提的是，他出手从不留半分余地。"
        assert check_zero_tolerance(text, cfg) == "ZT_WORTH_MENTIONING"

    def test_positive_zhidezhuyide(self, cfg):
        text = "值得注意的是，那柄剑的剑穗是红色的。"
        assert check_zero_tolerance(text, cfg) == "ZT_WORTH_MENTIONING"

    def test_negative_zhide_alone(self, cfg):
        # '值得' 单独出现不应触发
        text = "他知道这柄剑值得自己用一辈子去守护。"
        assert check_zero_tolerance(text, cfg) is None


# ---------------------------------------------------------------------------
# AC3 — baseline calibration pin: conjunction_density_max stays in human band.
# ---------------------------------------------------------------------------


class TestBaselineCalibration:
    def test_threshold_within_human_baseline(self, cfg):
        # 114 本起点标杆 p90 ≈ 2.4 / kchars，控制 GPT 基线 p50 ≈ 3.8。
        # 阈值必须落在这个带宽内才能拦 AI 而不误伤人类。
        assert 2.0 <= cfg.conjunction_density_max <= 3.0, (
            f"conjunction_density_max = {cfg.conjunction_density_max} "
            "drifted out of the human-vs-AI calibration band [2.0, 3.0]. "
            "See module docstring for the 114-book benchmark methodology."
        )

    def test_human_prose_passes_threshold(self, cfg):
        """A piece of human-style action prose must be below the threshold."""
        prose = (
            "剑光划过晨雾，雪片在他的肩上碎裂。\n\n"
            "林渊深吸一口气，指节贴着剑柄，能感到金属里残留的夜寒。\n\n"
            "「你来了。」"
            "对面的人没有动，只是抬眼看了看天。\n\n"
            "云层很低，山门外的钟声从风里飘过来，一声，又一声。"
        ) * 3
        density = conjunction_density(prose)
        assert density <= cfg.conjunction_density_max, (
            f"human prose density {density:.2f} exceeded threshold "
            f"{cfg.conjunction_density_max}, suggesting either the prose "
            "samples regressed or the threshold drifted."
        )

    def test_ai_style_prose_blocked_by_threshold(self, cfg):
        """A connector-stuffed AI-style passage must clear the threshold."""
        ai_style = (
            "不仅如此，而且他还发现了另一件事。"
            "尽管如此，他依然不愿放弃。"
            "毫无疑问，这件事显而易见非常复杂。"
            "总而言之，综上所述，这是一个两难局面。"
            "首先他必须冷静，其次他需要计划。"
            "值得一提的是，众所周知，此事早有定论。"
        ) * 3
        report = analyze_diversity(ai_style, cfg)
        ids = {v.id for v in report.violations}
        assert "AD_CONJUNCTION_DENSE" in ids, (
            "AI-style stuffing fell below threshold — calibration regressed."
        )
