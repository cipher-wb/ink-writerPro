"""Tests for ink-writer/scripts/step2b_metrics.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ink-writer" / "scripts"))

from step2b_metrics import (
    calc_avg_sentence_length,
    calc_dialogue_ratio,
    evaluate,
    find_long_sentences,
    find_summary_phrases,
)

# ---------------------------------------------------------------------------
# Test 1: 句长均值计算
# ---------------------------------------------------------------------------

class TestAvgSentenceLength:
    def test_normal_sentences(self):
        text = "这是一个测试句子，包含了一些内容。这是第二个句子，也有一些字。第三个句子比较短。"
        avg = calc_avg_sentence_length(text)
        assert avg > 0
        # 3 sentences, check reasonable range
        assert 5 < avg < 30

    def test_empty_text(self):
        assert calc_avg_sentence_length("") == 0.0

    def test_mixed_punctuation(self):
        text = "他来了吗？没有！那就等着。"
        avg = calc_avg_sentence_length(text)
        assert avg > 0

    def test_long_sentences_avg(self):
        # Two sentences averaging >20 chars each
        text = "萧尘站在山崖边缘，感受着从深渊中涌上来的寒风，心中想起了师父说过的那些话。林渊在远处看着他，眼中闪过一丝担忧，但什么也没有说。"
        avg = calc_avg_sentence_length(text)
        assert avg > 20


# ---------------------------------------------------------------------------
# Test 2: 对话占比计算
# ---------------------------------------------------------------------------

class TestDialogueRatio:
    def test_no_dialogue(self):
        text = "他走在路上，天色已晚。远处传来了钟声。"
        ratio = calc_dialogue_ratio(text)
        assert ratio == 0.0

    def test_has_dialogue(self):
        text = "他说：「你好啊，我叫萧尘。」她点了点头。"
        ratio = calc_dialogue_ratio(text)
        assert ratio > 0.0

    def test_high_dialogue(self):
        text = "「你来了。」「嗯，我来了。」「那就开始吧。」「好。」"
        ratio = calc_dialogue_ratio(text)
        assert ratio > 0.5

    def test_empty_text(self):
        assert calc_dialogue_ratio("") == 0.0


# ---------------------------------------------------------------------------
# Test 3: 综合评估 — 全量模式（未达标）
# ---------------------------------------------------------------------------

class TestEvaluateFull:
    def test_short_sentences_trigger_full_mode(self):
        """短句均值 + 无对话 → 全量模式"""
        text = "他来了。她走了。天黑了。雨停了。风来了。"
        result = evaluate(text)
        assert result["targeted_mode"] is False
        assert result["mode"] == "full"

    def test_no_dialogue_trigger_full_mode(self):
        """句长达标但无对话 → 全量模式"""
        text = (
            "萧尘站在山崖边缘，感受着从深渊中涌上来的寒风，心中想起了师父的话。"
            "林渊在远处看着他，眼中闪过一丝担忧，但什么也没有说出来。"
            "远处的山峰在夕阳下染上了一层金红色的光芒，美得令人窒息。"
        )
        result = evaluate(text)
        assert result["dialogue_ratio"] < 0.10
        assert result["targeted_mode"] is False
        assert result["mode"] == "full"


# ---------------------------------------------------------------------------
# Test 4: 综合评估 — 定向检查模式（达标）
# ---------------------------------------------------------------------------

class TestEvaluateTargeted:
    def test_both_metrics_met_trigger_targeted(self):
        """句长达标 + 对话达标 → 定向检查模式"""
        text = (
            "萧尘走进了大殿，四周的烛火摇曳不定，投下忽明忽暗的影子，空气中弥漫着淡淡的檀香。"
            "「你就是新来的弟子？」长老坐在上首，目光如炬地打量着他，手指轻轻敲着扶手。"
            "「是的，晚辈萧尘，奉师命前来拜见长老大人。」萧尘抱拳行礼，语气恭敬但不卑不亢。"
            "长老微微颔首，从袖中取出一块玉牌递了过来，上面刻着复杂的符文，在烛光下泛着微光。"
            "「拿着这个去藏经阁，那里有你需要的一切功法秘籍，切记不可贪多。」"
            "萧尘双手接过玉牌，感受到其中蕴含的灵力波动，心中一凛，暗道这位长老修为深不可测。"
        )
        result = evaluate(text)
        assert result["avg_sentence_length"] > 20
        assert result["dialogue_ratio"] > 0.10
        assert result["targeted_mode"] is True
        assert result["mode"] == "targeted"


# ---------------------------------------------------------------------------
# Test 5: 超长句检测
# ---------------------------------------------------------------------------

class TestLongSentences:
    def test_detect_long_sentence(self):
        long = "他" * 60  # 60 chars, > 55
        text = f"{long}。短句。"
        result = find_long_sentences(text)
        assert len(result) >= 1
        assert result[0]["length"] > 55

    def test_dialogue_excluded(self):
        """对话内的超长句不计入"""
        text = "「" + "他" * 60 + "」。短句。"
        result = find_long_sentences(text)
        assert len(result) == 0

    def test_normal_length_ok(self):
        text = "这是一个正常长度的句子，不超过五十五个字。"
        result = find_long_sentences(text)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Test 6: 总结式旁白检测
# ---------------------------------------------------------------------------

class TestSummaryPhrases:
    def test_detect_summary_phrases(self):
        text = "由此可见，他的实力远超常人。换句话说，没有人是他的对手。"
        result = find_summary_phrases(text)
        assert len(result) == 2
        phrases = [r["phrase"] for r in result]
        assert "由此可见" in phrases
        assert "换句话说" in phrases

    def test_no_summary_phrases(self):
        text = "他拔出剑，向前踏出一步。剑光一闪，敌人应声倒地。"
        result = find_summary_phrases(text)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Test 7: evaluate 输出结构完整性
# ---------------------------------------------------------------------------

class TestEvaluateStructure:
    def test_output_has_all_fields(self):
        text = "测试文本。「对话」。"
        result = evaluate(text)
        expected_keys = {
            "avg_sentence_length", "dialogue_ratio", "dialogue_ratio_pct",
            "targeted_mode", "mode", "long_sentences_count", "long_sentences",
            "summary_phrases_count", "summary_phrases",
        }
        assert expected_keys.issubset(set(result.keys()))
