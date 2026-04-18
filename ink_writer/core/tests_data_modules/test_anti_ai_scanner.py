#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for anti_ai_scanner module — 7-layer AI writing detection.
"""

import json
import tempfile
from pathlib import Path

import pytest

from anti_ai_scanner import AntiAIScanner, HIGH_RISK_WORDS, LAYER_MAX_SCORES


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

# Clean literary text — minimal AI patterns
CLEAN_TEXT = (
    "老陈蹲在巷口，手里攥着半根烟。\n\n"
    "巷子深处传来铁锅翻炒的声响，油烟味从窗缝里挤出来。"
    "他吸了一口，烟灰落在裤腿上，他也不拍。\n\n"
    "\u201c回来吃饭。\u201d屋里的女人喊了一声。\n\n"
    "他没应。过了半晌，把烟头摁灭在墙根，站起来，膝盖咔嚓响了一下。"
    "门口的猫抬头看了他一眼，又把脑袋埋回爪子底下。\n\n"
    "天擦黑了。路灯嗡地亮起来，照出一小圈昏黄的光。"
    "他往屋里走，脚步声闷闷的。"
)

# AI-flavored text with many detectable patterns
AI_TEXT = (
    "综合来看，这段经历对他而言意义深远。"
    "首先，他展现出了非常坚定的意志。"
    "其次，他仿佛看到了新的希望。"
    "最后，命运的齿轮开始转动。\n\n"
    "他皱起眉头，目光深邃，嘴角勾起一抹苦笑。"
    "空气仿佛凝固了，气氛变得微妙起来。"
    "毫无疑问，一切才刚刚开始。\n\n"
    "他非常愤怒，十分高兴地说："
    "\u201c我觉得我们应该因为这件事所以做出改变。\u201d\n\n"
    "她很很很很高兴，极其极其紧张，异常异常兴奋。"
    "值得注意的是，这折射出了深层的蕴含着希望的彰显。\n\n"
    "与此同时，他看到了远方的曙光，闻到了泥土的芬芳，"
    "感受到了风的温柔，听到了鸟鸣，感觉到了大地的脉动。\n\n"
    "不仅如此，而且他甚至简直更是无法自拔。"
)


@pytest.fixture
def clean_scanner():
    return AntiAIScanner(CLEAN_TEXT, filename="clean.txt")


@pytest.fixture
def ai_scanner():
    return AntiAIScanner(AI_TEXT, filename="ai.txt")


# ---------------------------------------------------------------------------
# 1. Basic instantiation
# ---------------------------------------------------------------------------

class TestInit:
    def test_basic_attributes(self, clean_scanner):
        assert clean_scanner.filename == "clean.txt"
        assert clean_scanner.total_chars > 0
        assert isinstance(clean_scanner.lines, list)
        assert clean_scanner.high_risk_segments == []

    def test_empty_text(self):
        s = AntiAIScanner("", filename="empty.txt")
        assert s.total_chars == 0
        assert s.lines == []

    def test_short_text(self):
        s = AntiAIScanner("短")
        assert s.total_chars == 1

    def test_custom_wordlist(self, tmp_path):
        wordlist = tmp_path / "custom.json"
        wordlist.write_text(
            json.dumps({"总结词": ["自定义总结"], "自定义类别": ["测试词A"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        s = AntiAIScanner("自定义总结出现了，测试词A也出现了。", custom_wordlist=str(wordlist))
        # merged into existing category
        assert "自定义总结" in s._high_risk_words["总结词"]
        # new category added
        assert "自定义类别" in s._high_risk_words
        result = s.scan_layer1_high_risk_words()
        # should detect the custom words
        matched = [d["word"] for d in result["details"]]
        assert "自定义总结" in matched
        assert "测试词A" in matched

    def test_invalid_custom_wordlist(self, capsys):
        """Bad path should not crash, just warn on stderr."""
        s = AntiAIScanner("hello", custom_wordlist="/nonexistent/path.json")
        assert s._high_risk_words  # still has defaults


# ---------------------------------------------------------------------------
# 2. L1 — high risk words
# ---------------------------------------------------------------------------

class TestLayer1:
    def test_detects_high_risk_words(self, ai_scanner):
        result = ai_scanner.scan_layer1_high_risk_words()
        assert result["score"] > 0
        assert result["max"] == LAYER_MAX_SCORES["L1_high_risk_words"]
        categories_found = {d["category"] for d in result["details"]}
        # AI_TEXT contains words from several categories
        assert "总结词" in categories_found
        assert "动作套话" in categories_found
        assert "机械收尾" in categories_found

    def test_clean_text_low_score(self, clean_scanner):
        result = clean_scanner.scan_layer1_high_risk_words()
        # Clean text should have very few or zero hits
        assert result["score"] <= 4

    def test_score_capped_at_max(self):
        """Even with massive hits, score should not exceed max."""
        # Repeat high-risk words many times
        text = "。".join(["综合总之毫无疑问毋庸置疑"] * 50)
        s = AntiAIScanner(text)
        result = s.scan_layer1_high_risk_words()
        assert result["score"] <= result["max"]


# ---------------------------------------------------------------------------
# 3. L2 — sentence pattern
# ---------------------------------------------------------------------------

class TestLayer2:
    def test_detects_three_part_pattern(self):
        text = "首先他站起来。其次他走了几步。最后他坐下了。"
        s = AntiAIScanner(text)
        result = s.scan_layer2_sentence_pattern()
        types = [d["type"] for d in result["details"]]
        assert "三段式" in types

    def test_detects_isomorphic_sentences(self):
        text = "他拿起了剑，挥向前方。他拿起了盾，挡住攻击。他拿起了弓，射向远处。"
        s = AntiAIScanner(text)
        result = s.scan_layer2_sentence_pattern()
        types = [d["type"] for d in result["details"]]
        assert "同构句" in types or "无符号排比" in types

    def test_detects_list_narrative(self):
        text = "正文开始。\n· 第一条内容\n· 第二条内容\n· 第三条内容\n· 第四条内容"
        s = AntiAIScanner(text)
        result = s.scan_layer2_sentence_pattern()
        types = [d["type"] for d in result["details"]]
        assert "清单化叙事" in types

    def test_detects_progressive_overuse(self):
        text = "他不仅勇敢，而且聪明，甚至简直是天才，更是无人能及，况且他还很谦虚。"
        s = AntiAIScanner(text)
        result = s.scan_layer2_sentence_pattern()
        types = [d["type"] for d in result["details"]]
        assert "递进词过度" in types

    def test_clean_text_low_score(self, clean_scanner):
        result = clean_scanner.scan_layer2_sentence_pattern()
        assert result["score"] <= 5


# ---------------------------------------------------------------------------
# 4. L3 — adjective density
# ---------------------------------------------------------------------------

class TestLayer3:
    def test_detects_degree_adverbs(self):
        text = "他非常高兴，十分激动，极其兴奋，异常紧张，格外感动。" * 5
        s = AntiAIScanner(text)
        result = s.scan_layer3_adjective_density()
        types = [d["type"] for d in result["details"]]
        assert "程度副词过多" in types

    def test_detects_double_adjective(self):
        text = "温暖的柔和的阳光洒了下来。冰冷的刺骨的寒风吹过脸庞。"
        s = AntiAIScanner(text)
        result = s.scan_layer3_adjective_density()
        types = [d["type"] for d in result["details"]]
        assert "双形容词修饰" in types

    def test_detects_sensory_pile(self):
        text = "他看到了远山，听到了鸟鸣，闻到了花香，感受到了风。"
        s = AntiAIScanner(text)
        result = s.scan_layer3_adjective_density()
        types = [d["type"] for d in result["details"]]
        assert "感官堆砌" in types

    def test_clean_text_low_score(self, clean_scanner):
        result = clean_scanner.scan_layer3_adjective_density()
        assert result["score"] <= 4


# ---------------------------------------------------------------------------
# 5. L4 — idiom density
# ---------------------------------------------------------------------------

class TestLayer4:
    def test_detects_four_char_stacking(self):
        text = "风和日丽，鸟语花香，万里无云，碧波荡漾，心旷神怡。"
        s = AntiAIScanner(text)
        result = s.scan_layer4_idiom_density()
        assert result["score"] > 0

    def test_low_idiom_clean(self, clean_scanner):
        result = clean_scanner.scan_layer4_idiom_density()
        assert result["score"] <= result["max"]


# ---------------------------------------------------------------------------
# 6. L5 — dialogue quality
# ---------------------------------------------------------------------------

class TestLayer5:
    def test_detects_hollow_dialogue(self):
        text = (
            "张三说\u201c嗯\u201d\n"
            "李四说\u201c哦\u201d\n"
            "王五说\u201c好的\u201d\n"
            "赵六说\u201c是的\u201d\n"
        )
        s = AntiAIScanner(text)
        result = s.scan_layer5_dialogue_quality()
        types = [d["type"] for d in result["details"]]
        assert "空洞对话" in types

    def test_detects_manual_dialogue(self):
        long_speech = "这件事情的来龙去脉是这样的，" * 20
        text = f"他说\u201c{long_speech}\u201d"
        s = AntiAIScanner(text)
        result = s.scan_layer5_dialogue_quality()
        types = [d["type"] for d in result["details"]]
        assert "说明书式对话" in types

    def test_detects_subtext_missing(self):
        # More than 60% of dialogues contain direct intent words
        dialogues = []
        for i in range(10):
            dialogues.append(f"张三说\u201c我觉得第{i}件事很重要\u201d")
        text = "\n".join(dialogues)
        s = AntiAIScanner(text)
        result = s.scan_layer5_dialogue_quality()
        types = [d["type"] for d in result["details"]]
        assert "潜台词缺失" in types

    def test_clean_text_low_score(self, clean_scanner):
        result = clean_scanner.scan_layer5_dialogue_quality()
        assert result["score"] <= 10


# ---------------------------------------------------------------------------
# 7. L6 — paragraph structure
# ---------------------------------------------------------------------------

class TestLayer6:
    def test_detects_long_paragraph(self):
        # Single paragraph > 300 chars
        text = "他走了一步又一步，" * 80
        s = AntiAIScanner(text)
        result = s.scan_layer6_paragraph_structure()
        types = [d["type"] for d in result["details"]]
        assert "过长段落" in types or "段落偏长" in types

    def test_detects_short_paragraphs(self):
        # Many very short paragraphs
        text = "\n\n".join(["短。"] * 20)
        s = AntiAIScanner(text)
        result = s.scan_layer6_paragraph_structure()
        types = [d["type"] for d in result["details"]]
        assert "段落偏短" in types or "单句成段过多" in types

    def test_empty_text_zero_score(self):
        s = AntiAIScanner("")
        result = s.scan_layer6_paragraph_structure()
        assert result["score"] == 0

    def test_clean_text_reasonable(self, clean_scanner):
        result = clean_scanner.scan_layer6_paragraph_structure()
        assert result["score"] <= result["max"]


# ---------------------------------------------------------------------------
# 8. L7 — punctuation rhythm
# ---------------------------------------------------------------------------

class TestLayer7:
    def test_detects_consecutive_ellipsis(self):
        text = "他说完了……………… 然后沉默了。"
        s = AntiAIScanner(text)
        result = s.scan_layer7_punctuation_rhythm()
        types = [d["type"] for d in result["details"]]
        assert "连续省略号" in types

    def test_detects_consecutive_exclamation(self):
        text = "不可能！！！这怎么会！！！太过分了！！！"
        s = AntiAIScanner(text)
        result = s.scan_layer7_punctuation_rhythm()
        types = [d["type"] for d in result["details"]]
        assert "连续感叹号" in types

    def test_detects_long_comma_sentence(self):
        text = "他走了很远，穿过了田野，翻过了山丘，跨过了河流，趟过了泥地，来到了村口。"
        s = AntiAIScanner(text)
        result = s.scan_layer7_punctuation_rhythm()
        types = [d["type"] for d in result["details"]]
        assert "逗号过多长句" in types

    def test_clean_text_low_score(self, clean_scanner):
        result = clean_scanner.scan_layer7_punctuation_rhythm()
        assert result["score"] <= 3


# ---------------------------------------------------------------------------
# 9. scan_all integration
# ---------------------------------------------------------------------------

class TestScanAll:
    def test_result_structure(self, clean_scanner):
        result = clean_scanner.scan_all()
        assert "risk_score" in result
        assert "risk_level" in result
        assert "layer_scores" in result
        assert "high_risk_segments" in result
        assert "summary" in result
        assert "total_chars" in result
        assert result["file"] == "clean.txt"
        assert len(result["layer_scores"]) == 7

    def test_risk_level_low(self, clean_scanner):
        result = clean_scanner.scan_all()
        # Clean text should be low or at most medium
        assert result["risk_level"] in ("low", "medium")
        assert result["risk_score"] < 60

    def test_risk_level_high(self, ai_scanner):
        result = ai_scanner.scan_all()
        # AI text should have a meaningful score
        assert result["risk_score"] > 20

    def test_risk_score_bounded(self, ai_scanner):
        result = ai_scanner.scan_all()
        assert 0 <= result["risk_score"] <= 100

    def test_risk_level_thresholds(self):
        """Verify the three risk level buckets."""
        # Craft a text with known behavior: empty text -> 0 score
        s = AntiAIScanner("")
        result = s.scan_all()
        assert result["risk_score"] == 0
        assert result["risk_level"] == "low"

    def test_summary_contains_info(self, ai_scanner):
        result = ai_scanner.scan_all()
        assert isinstance(result["summary"], str)
        # AI text should have problems listed in summary
        assert "主要问题" in result["summary"] or "未发现" in result["summary"]


# ---------------------------------------------------------------------------
# 10. format_report
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_returns_nonempty_string(self, clean_scanner):
        result = clean_scanner.scan_all()
        report = clean_scanner.format_report(result)
        assert isinstance(report, str)
        assert len(report) > 100

    def test_contains_key_sections(self, ai_scanner):
        result = ai_scanner.scan_all()
        report = ai_scanner.format_report(result)
        assert "Anti-AI" in report
        assert "各层得分" in report
        assert "风险评分" in report
        assert result["file"] in report

    def test_report_shows_segments(self, ai_scanner):
        result = ai_scanner.scan_all()
        report = ai_scanner.format_report(result)
        if result["high_risk_segments"]:
            assert "高风险段落" in report


# ---------------------------------------------------------------------------
# 11. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_whitespace_only(self):
        s = AntiAIScanner("   \n\n   \n")
        result = s.scan_all()
        assert result["risk_score"] == 0

    def test_single_character(self):
        s = AntiAIScanner("哦")
        result = s.scan_all()
        assert 0 <= result["risk_score"] <= 100

    def test_no_dialogue_text(self):
        text = "山间的雾气渐渐散去。远处传来几声犬吠。"
        s = AntiAIScanner(text)
        result = s.scan_layer5_dialogue_quality()
        assert result["score"] == 0

    def test_all_layers_have_max(self, clean_scanner):
        result = clean_scanner.scan_all()
        for key, layer in result["layer_scores"].items():
            assert "score" in layer
            assert "max" in layer
            assert layer["score"] <= layer["max"]
            assert layer["max"] == LAYER_MAX_SCORES[key]
