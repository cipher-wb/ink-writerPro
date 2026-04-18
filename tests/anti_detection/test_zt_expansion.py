#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""US-014: Tests for the expanded zero-tolerance rule set.

Covers the 6 new rule groups added on top of ZT_TIME_OPENING / ZT_MEANWHILE:
  - ZT_MEANWHILE    (new variants)
  - ZT_NOT_ONLY_BUT_ALSO
  - ZT_DESPITE_STILL
  - ZT_UNDOUBTEDLY
  - ZT_IN_SHORT
  - ZT_FIRST_SECOND
  - ZT_WORTH_MENTIONING

These tests use the real on-disk config so any drift between YAML and tests
will be caught. All tests are pure-Python (no LLM call).
"""

from __future__ import annotations

import pytest

from ink_writer.anti_detection.anti_detection_gate import check_zero_tolerance
from ink_writer.anti_detection.config import (
    AntiDetectionConfig,
    load_config,
)
from ink_writer.anti_detection.fix_prompt_builder import VIOLATION_FIX_TEMPLATES


@pytest.fixture(scope="module")
def real_config() -> AntiDetectionConfig:
    """Load the actual config/anti-detection.yaml from the repo."""
    return load_config()


class TestZTConfigLoading:
    """YAML sanity: all new rule ids are loaded from disk."""

    def test_all_new_rule_ids_loaded(self, real_config: AntiDetectionConfig):
        ids = {rule.id for rule in real_config.zero_tolerance}
        expected = {
            "ZT_TIME_OPENING",
            "ZT_MEANWHILE",
            "ZT_NOT_ONLY_BUT_ALSO",
            "ZT_DESPITE_STILL",
            "ZT_UNDOUBTEDLY",
            "ZT_IN_SHORT",
            "ZT_FIRST_SECOND",
            "ZT_WORTH_MENTIONING",
        }
        assert expected.issubset(ids), f"missing ids: {expected - ids}"

    def test_fix_templates_cover_new_rules(self):
        for rid in (
            "ZT_NOT_ONLY_BUT_ALSO",
            "ZT_DESPITE_STILL",
            "ZT_UNDOUBTEDLY",
            "ZT_IN_SHORT",
            "ZT_FIRST_SECOND",
            "ZT_WORTH_MENTIONING",
        ):
            assert rid in VIOLATION_FIX_TEMPLATES
            assert "零容忍" in VIOLATION_FIX_TEMPLATES[rid]

    def test_conjunction_density_max_loaded(self, real_config: AntiDetectionConfig):
        assert real_config.conjunction_density_max == pytest.approx(2.5)


class TestZTMeanwhileVariants:
    def test_original_meanwhile(self, real_config: AntiDetectionConfig):
        text = "他拔剑。\n\n与此同时，远在千里之外的宗门中。"
        assert check_zero_tolerance(text, real_config) == "ZT_MEANWHILE"

    def test_at_this_very_moment(self, real_config: AntiDetectionConfig):
        text = "他慢慢回头。\n\n就在此时此刻，一道黑影掠过屋檐。"
        assert check_zero_tolerance(text, real_config) == "ZT_MEANWHILE"

    def test_and_at_this_time(self, real_config: AntiDetectionConfig):
        text = "院中静得吓人。\n\n而在此时，钟声骤响。"
        assert check_zero_tolerance(text, real_config) == "ZT_MEANWHILE"

    def test_same_time(self, real_config: AntiDetectionConfig):
        text = "他握紧长剑。\n\n就在同一时间，远方传来马蹄声。"
        assert check_zero_tolerance(text, real_config) == "ZT_MEANWHILE"


class TestZTNotOnlyButAlso:
    def test_not_only_but_also(self, real_config: AntiDetectionConfig):
        text = "他不仅剑法超绝，而且内力深厚，令整个山门都不敢轻视。"
        assert check_zero_tolerance(text, real_config) == "ZT_NOT_ONLY_BUT_ALSO"

    def test_not_only_also(self, real_config: AntiDetectionConfig):
        text = "她不仅身手了得，还精通阵法，被师门寄予厚望。"
        assert check_zero_tolerance(text, real_config) == "ZT_NOT_ONLY_BUT_ALSO"

    def test_budan_erqie(self, real_config: AntiDetectionConfig):
        text = "这柄剑不但锋利无比，而且暗藏杀机，令人不敢轻易出鞘。"
        assert check_zero_tolerance(text, real_config) == "ZT_NOT_ONLY_BUT_ALSO"

    def test_budan_hai(self, real_config: AntiDetectionConfig):
        text = "老道士不但没生气，还笑着点了点头。"
        assert check_zero_tolerance(text, real_config) == "ZT_NOT_ONLY_BUT_ALSO"

    def test_standalone_buyi_does_not_trigger(self, real_config: AntiDetectionConfig):
        # '不仅' 单独出现但没后续 '而且/还' 不应触发
        text = "他拔剑出鞘，动作快得不可思议，让人目不暇接。"
        assert check_zero_tolerance(text, real_config) != "ZT_NOT_ONLY_BUT_ALSO"


class TestZTDespiteStill:
    def test_jinguan_ruci(self, real_config: AntiDetectionConfig):
        text = "他伤得很重，身形摇晃。尽管如此，他依然紧握着长剑。"
        assert check_zero_tolerance(text, real_config) == "ZT_DESPITE_STILL"

    def test_huasuiruci(self, real_config: AntiDetectionConfig):
        text = "他早已力竭。话虽如此，他仍然向前迈了一步。"
        assert check_zero_tolerance(text, real_config) == "ZT_DESPITE_STILL"

    def test_jinguan_but(self, real_config: AntiDetectionConfig):
        text = "尽管风雪弥漫，但他的眼神始终锁定对手。"
        assert check_zero_tolerance(text, real_config) == "ZT_DESPITE_STILL"

    def test_although_danshi(self, real_config: AntiDetectionConfig):
        text = "虽然身中剧毒，但是他的手仍稳如磐石。"
        assert check_zero_tolerance(text, real_config) == "ZT_DESPITE_STILL"


class TestZTUndoubtedly:
    def test_haowuyiwen(self, real_config: AntiDetectionConfig):
        text = "剑光一闪，尘土飞扬。毫无疑问，这是一记杀招。"
        assert check_zero_tolerance(text, real_config) == "ZT_UNDOUBTEDLY"

    def test_xianeryijian(self, real_config: AntiDetectionConfig):
        text = "山顶积雪漫漫。显而易见，此处已久无人至。"
        assert check_zero_tolerance(text, real_config) == "ZT_UNDOUBTEDLY"

    def test_buyaneryu(self, real_config: AntiDetectionConfig):
        text = "这一招的威力不言而喻，在场众人无不骇然。"
        assert check_zero_tolerance(text, real_config) == "ZT_UNDOUBTEDLY"

    def test_zhongsuozhouzhi(self, real_config: AntiDetectionConfig):
        text = "众所周知，剑宗从不纳外姓弟子。"
        assert check_zero_tolerance(text, real_config) == "ZT_UNDOUBTEDLY"

    def test_kexiangerzhi(self, real_config: AntiDetectionConfig):
        text = "他闭关十年，可想而知修为已今非昔比。"
        assert check_zero_tolerance(text, real_config) == "ZT_UNDOUBTEDLY"


class TestZTInShort:
    def test_zongeryanzhi(self, real_config: AntiDetectionConfig):
        text = "剑招如疾风，步法似残影。总而言之，这一战他胜得毫无悬念。"
        assert check_zero_tolerance(text, real_config) == "ZT_IN_SHORT"

    def test_zongshangsuoshu(self, real_config: AntiDetectionConfig):
        text = "综上所述，此局已无破解之法。"
        assert check_zero_tolerance(text, real_config) == "ZT_IN_SHORT"

    def test_zongdelaishuo(self, real_config: AntiDetectionConfig):
        text = "总的来说，这是一场精心布置的局。"
        assert check_zero_tolerance(text, real_config) == "ZT_IN_SHORT"

    def test_guigenjiedi(self, real_config: AntiDetectionConfig):
        text = "归根结底，他要的不过是一个答案。"
        assert check_zero_tolerance(text, real_config) == "ZT_IN_SHORT"


class TestZTFirstSecond:
    def test_first_then(self, real_config: AntiDetectionConfig):
        text = (
            "他定下了三个目标。首先是找到线索，其次是确认凶手，"
            "最后一步才是动手。"
        )
        assert check_zero_tolerance(text, real_config) == "ZT_FIRST_SECOND"

    def test_diyi_dier_disan(self, real_config: AntiDetectionConfig):
        text = "此中关键有三。第一是时机，第二是位置，第三是心境。"
        assert check_zero_tolerance(text, real_config) == "ZT_FIRST_SECOND"


class TestZTWorthMentioning:
    def test_zhideyitide(self, real_config: AntiDetectionConfig):
        text = "值得一提的是，他出手从不留半分余地。"
        assert check_zero_tolerance(text, real_config) == "ZT_WORTH_MENTIONING"

    def test_zhidezhuyide(self, real_config: AntiDetectionConfig):
        text = "值得注意的是，那柄剑的剑穗是红色的。"
        assert check_zero_tolerance(text, real_config) == "ZT_WORTH_MENTIONING"

    def test_budebutide(self, real_config: AntiDetectionConfig):
        text = "不得不提的是，这座城早已废弃多年。"
        assert check_zero_tolerance(text, real_config) == "ZT_WORTH_MENTIONING"

    def test_bukefourende(self, real_config: AntiDetectionConfig):
        text = "不可否认的是，这场战斗已然改变了格局。"
        assert check_zero_tolerance(text, real_config) == "ZT_WORTH_MENTIONING"


class TestCleanTextPasses:
    """A normal action/dialogue-driven passage must hit none of the new rules."""

    def test_no_false_positive_on_clean_prose(self, real_config: AntiDetectionConfig):
        text = (
            "剑光划破长空，映得半边天际血红一片。\n\n"
            "林渊握紧剑柄，指节泛白。他向前踏出一步，碎石在脚下崩裂。\n\n"
            "「你还要打？」他问，声音低哑。\n\n"
            "萧尘没有答话，只是抬起了剑。"
        )
        assert check_zero_tolerance(text, real_config) is None
