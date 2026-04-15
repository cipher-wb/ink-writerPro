#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for anti-detection sentence diversity hard gate."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ink_writer.anti_detection.config import (
    AntiDetectionConfig,
    ZeroToleranceRule,
    load_config,
)
from ink_writer.anti_detection.fix_prompt_builder import (
    VIOLATION_FIX_TEMPLATES,
    build_fix_prompt,
    normalize_checker_output,
)
from ink_writer.anti_detection.sentence_diversity import (
    DiversityReport,
    DiversityViolation,
    analyze_diversity,
)
from ink_writer.anti_detection.anti_detection_gate import (
    AntiDetectionAttempt,
    AntiDetectionResult,
    check_zero_tolerance,
    run_anti_detection_gate,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    (tmp_path / "chapters").mkdir()
    (tmp_path / "logs").mkdir()
    return tmp_path


@pytest.fixture()
def default_config() -> AntiDetectionConfig:
    return AntiDetectionConfig(
        enabled=True,
        score_threshold=70.0,
        golden_three_threshold=80.0,
        max_retries=1,
        zero_tolerance=[
            ZeroToleranceRule(
                id="ZT_TIME_OPENING",
                description="章节以时间标记开头",
                patterns=[
                    r"^第[一二三四五六七八九十\d]+[天日]",
                    r"^[次翌]日",
                    r"^[一二三四五六七八九十\d]+天[后前]",
                ],
            ),
            ZeroToleranceRule(
                id="ZT_MEANWHILE",
                description="使用与此同时转场",
                patterns=[r"与此同时"],
            ),
        ],
    )


SAMPLE_CHECKER_PASS = {
    "checker": "anti-detection",
    "chapter": 10,
    "overall_score": 85,
    "dimensions": {},
    "severity_counts": {"critical": 0, "high": 0, "medium": 1, "low": 0},
    "fix_priority": [],
}

SAMPLE_CHECKER_FAIL = {
    "checker": "anti-detection",
    "chapter": 10,
    "overall_score": 45,
    "dimensions": {},
    "severity_counts": {"critical": 0, "high": 3, "medium": 2, "low": 0},
    "fix_priority": [
        {"location": "第3段", "type": "句长平坦区", "fix": "插入碎句"},
        {"location": "第60-85行", "type": "对话同质", "fix": "差异化对话长度"},
    ],
}

SAMPLE_CHECKER_BORDERLINE = {
    "checker": "anti-detection",
    "chapter": 10,
    "overall_score": 65,
    "dimensions": {},
    "severity_counts": {"critical": 0, "high": 1, "medium": 2, "low": 0},
    "fix_priority": [
        {"location": "全章", "type": "AD_SENTENCE_FRAGMENTATION", "fix": "合并短句"},
    ],
}

# A deliberately AI-tasting text: uniform sentence length, no dialogue, no emotion marks
AI_TASTE_FIXTURE = (
    "他走进了房间。他看到了桌子。他拿起了杯子。他喝了一口水。"
    "他觉得很渴。他又喝了一口。他放下了杯子。他走到了窗前。"
    "他看着外面的风景。天空很蓝。白云在飘动。他觉得很平静。"
    "因为他很累。所以他想休息。于是他躺在了沙发上。因此他闭上了眼睛。"
    "他想起了昨天的事情。昨天他去了市场。他买了很多东西。他觉得很满足。"
    "他慢慢地睡着了。他做了一个梦。梦里有很多人。他们在笑着说话。"
    "他醒来的时候。已经是下午了。他站起来伸了个懒腰。他走到厨房去。"
    "他打开了冰箱。里面有很多食物。他拿出了一个苹果。他咬了一口。"
)

# A human-like text with varied sentences, dialogue, emotion marks, fragments
HUMAN_LIKE_FIXTURE = (
    "剑光划破长空，映得半边天际血红一片。\n\n"
    "「你疯了！」林渊猛地后退两步，右手死死攥住剑柄，指节泛白——"
    "他从未见过任何人敢以肉身硬接天罚雷劫。\n\n"
    "萧尘没有回答。\n\n"
    "风卷起地上的碎石，细碎的沙砾打在脸上生疼。远处的山峰在雷光中"
    "忽明忽暗，像是随时会崩塌的巨兽。空气中弥漫着焦灼的气味，混合着"
    "某种说不清道不明的甜腻——那是灵力过载时独有的味道。\n\n"
    "「为什么……」林渊的声音在发抖，「你明明知道，渡劫失败的代价是什么！」\n\n"
    "沉默。\n\n"
    "漫长的、令人窒息的沉默。\n\n"
    "然后萧尘笑了。不是苦笑，不是自嘲，而是一种纯粹的、不带任何杂质的笑。"
    "就好像他此刻正站在春天的原野上，而不是雷劫之下。\n\n"
    "「因为……」他轻声说，声音几乎被雷鸣吞没，「有些事，不做会后悔一辈子啊。」\n\n"
    "第七道天雷落下。\n\n"
    "大地震颤。林渊被气浪掀飞出去，重重撞在一块巨石上，嘴角溢出血丝。"
    "他拼命睁大眼睛，透过弥漫的灰尘和灵力风暴，试图看清那个身影——\n\n"
    "看不见了。\n\n"
    "什么都看不见了。\n\n"
    "「萧尘！」他嘶吼着，喉咙像是被砂纸打磨过，声音嘶哑得不像自己。"
    "泪水和着灰尘糊了满脸，他也顾不得擦。他只是拼了命地往前爬，"
    "膝盖磨破了，手指扣进泥土里，指甲翻起来也浑然不觉。\n\n"
    "他必须找到他。\n\n"
    "哪怕是尸体，也要找到。"
)


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestConfig:
    def test_default_config(self):
        cfg = AntiDetectionConfig()
        assert cfg.enabled is True
        assert cfg.score_threshold == 70.0
        assert cfg.max_retries == 1
        assert cfg.zero_tolerance == []

    def test_load_config_from_yaml(self, tmp_path: Path):
        yaml_content = """
enabled: true
score_threshold: 75.0
golden_three_threshold: 85.0
max_retries: 2
sentence_cv_min: 0.40
zero_tolerance:
  - id: ZT_TEST
    description: test rule
    patterns:
      - "^test"
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")
        cfg = load_config(yaml_file)
        assert cfg.score_threshold == 75.0
        assert cfg.golden_three_threshold == 85.0
        assert cfg.max_retries == 2
        assert cfg.sentence_cv_min == 0.40
        assert len(cfg.zero_tolerance) == 1
        assert cfg.zero_tolerance[0].id == "ZT_TEST"

    def test_load_config_missing_file(self, tmp_path: Path):
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.enabled is True
        assert cfg.score_threshold == 70.0

    def test_load_config_empty_yaml(self, tmp_path: Path):
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("", encoding="utf-8")
        cfg = load_config(yaml_file)
        assert cfg.enabled is True

    def test_zero_tolerance_rule_dataclass(self):
        rule = ZeroToleranceRule(id="ZT_X", description="desc", patterns=["^x"])
        assert rule.id == "ZT_X"
        assert len(rule.patterns) == 1


# ---------------------------------------------------------------------------
# Fix prompt builder tests
# ---------------------------------------------------------------------------


class TestFixPromptBuilder:
    def test_build_fix_prompt_empty(self):
        assert build_fix_prompt([]) == ""

    def test_build_fix_prompt_with_violations(self):
        violations = [
            {"id": "AD_SENTENCE_CV", "severity": "high", "description": "句长过均匀"},
            {"id": "AD_DIALOGUE_LOW", "severity": "high", "description": "对话不足"},
        ]
        result = build_fix_prompt(violations)
        assert "句式多样性修复指令" in result
        assert "AD_SENTENCE_CV" in result
        assert "AD_DIALOGUE_LOW" in result
        assert "不得改变剧情事实" in result

    def test_build_fix_prompt_unknown_id(self):
        violations = [{"id": "UNKNOWN_RULE", "severity": "low", "description": "desc"}]
        result = build_fix_prompt(violations)
        assert "desc" in result

    def test_templates_cover_all_known_ids(self):
        known_ids = [
            "AD_SENTENCE_CV", "AD_SENTENCE_FRAGMENTATION",
            "AD_SHORT_SENTENCE_EXCESS", "AD_LONG_SENTENCE_DEFICIT",
            "AD_PARAGRAPH_REGULAR", "AD_PARAGRAPH_CV",
            "AD_DIALOGUE_LOW", "AD_EXCLAMATION_LOW", "AD_ELLIPSIS_LOW",
            "AD_EMOTION_PUNCT_LOW", "AD_CAUSAL_DENSE",
            "ZT_TIME_OPENING", "ZT_MEANWHILE",
        ]
        for vid in known_ids:
            assert vid in VIOLATION_FIX_TEMPLATES

    def test_normalize_checker_output_standard_format(self):
        result = normalize_checker_output(SAMPLE_CHECKER_FAIL)
        assert result["score"] == 45
        assert len(result["violations"]) == 2
        assert result["fix_prompt"] != ""

    def test_normalize_checker_output_already_normalized(self):
        raw = {"score": 80.0, "violations": [{"id": "x"}], "fix_prompt": "fix me"}
        result = normalize_checker_output(raw)
        assert result["score"] == 80.0
        assert result["fix_prompt"] == "fix me"

    def test_normalize_checker_output_empty(self):
        result = normalize_checker_output({})
        assert result["score"] == 0.0
        assert result["violations"] == []
        assert result["fix_prompt"] == ""


# ---------------------------------------------------------------------------
# Sentence diversity analysis tests
# ---------------------------------------------------------------------------


class TestSentenceDiversity:
    def test_empty_text(self):
        cfg = AntiDetectionConfig()
        report = analyze_diversity("", cfg)
        assert report.violations == []

    def test_short_text(self):
        cfg = AntiDetectionConfig()
        report = analyze_diversity("太短了。", cfg)
        assert report.violations == []

    def test_ai_taste_text_triggers_violations(self):
        cfg = AntiDetectionConfig()
        report = analyze_diversity(AI_TASTE_FIXTURE, cfg)
        violation_ids = {v.id for v in report.violations}
        assert "AD_SENTENCE_FRAGMENTATION" in violation_ids or "AD_SHORT_SENTENCE_EXCESS" in violation_ids
        assert report.sentence_mean < 18.0

    def test_human_like_text_fewer_violations(self):
        cfg = AntiDetectionConfig()
        report = analyze_diversity(HUMAN_LIKE_FIXTURE, cfg)
        high_violations = [v for v in report.violations if v.severity == "high"]
        ai_report = analyze_diversity(AI_TASTE_FIXTURE, cfg)
        ai_high = [v for v in ai_report.violations if v.severity == "high"]
        assert len(high_violations) <= len(ai_high)

    def test_sentence_cv_detection(self):
        uniform = "。".join(["这是一个标准句子啊"] * 30) + "。"
        cfg = AntiDetectionConfig(sentence_cv_min=0.35)
        report = analyze_diversity(uniform, cfg)
        violation_ids = {v.id for v in report.violations}
        assert "AD_SENTENCE_CV" in violation_ids

    def test_dialogue_ratio_detection(self):
        no_dialogue = "。".join(["他走向远方的山峰不回头看一眼身后"] * 20) + "。"
        cfg = AntiDetectionConfig(dialogue_ratio_min=0.10)
        report = analyze_diversity(no_dialogue, cfg)
        violation_ids = {v.id for v in report.violations}
        assert "AD_DIALOGUE_LOW" in violation_ids

    def test_emotion_punctuation_detection(self):
        flat_text = "。".join(["他平静地走过长廊然后坐下来慢慢喝茶"] * 20) + "。"
        cfg = AntiDetectionConfig(exclamation_density_min=1.5, total_emotion_punctuation_min=5.0)
        report = analyze_diversity(flat_text, cfg)
        violation_ids = {v.id for v in report.violations}
        assert "AD_EXCLAMATION_LOW" in violation_ids or "AD_EMOTION_PUNCT_LOW" in violation_ids

    def test_causal_density_detection(self):
        causal = "因为他很累。所以他想休息。于是他躺下了。因此他闭上眼。" * 15
        cfg = AntiDetectionConfig(causal_density_max=1.0)
        report = analyze_diversity(causal, cfg)
        violation_ids = {v.id for v in report.violations}
        assert "AD_CAUSAL_DENSE" in violation_ids

    def test_paragraph_regularity_detection(self):
        regular = "\n\n".join([
            "这是第一段。它有两句话。再加一句话。"
        ] * 15)
        cfg = AntiDetectionConfig(single_sentence_paragraph_ratio_min=0.20)
        report = analyze_diversity(regular, cfg)
        assert report.single_sentence_para_ratio < 0.20

    def test_metrics_populated(self):
        cfg = AntiDetectionConfig()
        report = analyze_diversity(HUMAN_LIKE_FIXTURE, cfg)
        assert report.sentence_cv > 0
        assert report.sentence_mean > 0
        assert isinstance(report.dialogue_ratio, float)
        assert isinstance(report.total_punctuation_density, float)


# ---------------------------------------------------------------------------
# Zero tolerance tests
# ---------------------------------------------------------------------------


class TestZeroTolerance:
    def test_time_opening_detected(self, default_config: AntiDetectionConfig):
        text = "第三天，他终于到达了目的地。"
        assert check_zero_tolerance(text, default_config) == "ZT_TIME_OPENING"

    def test_time_opening_ci_day(self, default_config: AntiDetectionConfig):
        text = "次日清晨，他收到了一封信。"
        assert check_zero_tolerance(text, default_config) == "ZT_TIME_OPENING"

    def test_time_opening_days_later(self, default_config: AntiDetectionConfig):
        text = "三天后，消息传来。"
        assert check_zero_tolerance(text, default_config) == "ZT_TIME_OPENING"

    def test_meanwhile_detected(self, default_config: AntiDetectionConfig):
        text = "萧尘握紧了剑。\n\n与此同时，在千里之外的宗门中。"
        assert check_zero_tolerance(text, default_config) == "ZT_MEANWHILE"

    def test_clean_text_passes(self, default_config: AntiDetectionConfig):
        text = "剑光划过天际，血色弥漫了整个战场。"
        assert check_zero_tolerance(text, default_config) is None

    def test_empty_text(self, default_config: AntiDetectionConfig):
        assert check_zero_tolerance("", default_config) is None

    def test_no_rules(self):
        cfg = AntiDetectionConfig(zero_tolerance=[])
        text = "第三天，他到了。"
        assert check_zero_tolerance(text, cfg) is None

    def test_time_in_middle_not_triggered(self, default_config: AntiDetectionConfig):
        text = "剑光如虹。第三天的阳光洒下。"
        result = check_zero_tolerance(text, default_config)
        assert result != "ZT_TIME_OPENING"

    def test_leading_whitespace_handled(self, default_config: AntiDetectionConfig):
        text = "  \n  第三天清晨，他出发了。"
        assert check_zero_tolerance(text, default_config) == "ZT_TIME_OPENING"


# ---------------------------------------------------------------------------
# Gate integration tests
# ---------------------------------------------------------------------------


class TestAntiDetectionGate:
    def test_disabled_gate_passes(self, tmp_project: Path):
        config = AntiDetectionConfig(enabled=False)
        result = run_anti_detection_gate(
            "any text", 1, str(tmp_project),
            checker_fn=lambda t, c: {},
            polish_fn=lambda t, p, c: t,
            config=config,
        )
        assert result.passed is True
        assert result.final_score == 100.0

    def test_passing_score_no_retry(self, tmp_project: Path, default_config: AntiDetectionConfig):
        checker = MagicMock(return_value=SAMPLE_CHECKER_PASS)
        polish = MagicMock(return_value="polished")
        result = run_anti_detection_gate(
            "clean text", 10, str(tmp_project),
            checker_fn=checker,
            polish_fn=polish,
            config=default_config,
        )
        assert result.passed is True
        assert result.final_score == 85
        assert len(result.attempts) == 1
        polish.assert_not_called()

    def test_failing_score_triggers_block(self, tmp_project: Path, default_config: AntiDetectionConfig):
        checker = MagicMock(return_value=SAMPLE_CHECKER_FAIL)
        polish = MagicMock(return_value="still bad")
        result = run_anti_detection_gate(
            "bad text", 10, str(tmp_project),
            checker_fn=checker,
            polish_fn=polish,
            config=default_config,
        )
        assert result.passed is False
        assert result.blocked_path is not None
        assert os.path.exists(result.blocked_path)
        assert "anti_detection_blocked.md" in result.blocked_path

    def test_borderline_polished_then_passes(self, tmp_project: Path, default_config: AntiDetectionConfig):
        default_config.max_retries = 2
        call_count = [0]

        def checker_fn(text, chapter):
            call_count[0] += 1
            if call_count[0] == 1:
                return SAMPLE_CHECKER_BORDERLINE
            return SAMPLE_CHECKER_PASS

        polish = MagicMock(return_value="improved text")
        result = run_anti_detection_gate(
            "borderline text", 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish,
            config=default_config,
        )
        assert result.passed is True
        assert len(result.attempts) == 2
        polish.assert_called_once()

    def test_golden_three_higher_threshold(self, tmp_project: Path, default_config: AntiDetectionConfig):
        checker_result = dict(SAMPLE_CHECKER_PASS)
        checker_result["overall_score"] = 75  # passes 70 but not 80
        checker = MagicMock(return_value=checker_result)
        polish = MagicMock(return_value="polished")

        result = run_anti_detection_gate(
            "chapter 2 text", 2, str(tmp_project),
            checker_fn=checker,
            polish_fn=polish,
            config=default_config,
        )
        assert result.passed is False
        assert result.threshold == 80.0

    def test_zero_tolerance_immediate_block(self, tmp_project: Path, default_config: AntiDetectionConfig):
        checker = MagicMock(return_value=SAMPLE_CHECKER_PASS)
        polish = MagicMock(return_value="polished")
        result = run_anti_detection_gate(
            "第三天，他出发了。然后又走了很远。", 10, str(tmp_project),
            checker_fn=checker,
            polish_fn=polish,
            config=default_config,
        )
        assert result.passed is False
        assert result.zero_tolerance_hit == "ZT_TIME_OPENING"
        assert result.blocked_path is not None
        checker.assert_not_called()
        polish.assert_not_called()

    def test_zero_tolerance_blocked_md_content(self, tmp_project: Path, default_config: AntiDetectionConfig):
        result = run_anti_detection_gate(
            "次日清晨，阳光如常。", 5, str(tmp_project),
            checker_fn=lambda t, c: SAMPLE_CHECKER_PASS,
            polish_fn=lambda t, p, c: t,
            config=default_config,
        )
        assert result.blocked_path is not None
        content = Path(result.blocked_path).read_text(encoding="utf-8")
        assert "零容忍" in content
        assert "ZT_TIME_OPENING" in content

    def test_meanwhile_zero_tolerance(self, tmp_project: Path, default_config: AntiDetectionConfig):
        text = "萧尘拔剑。\n\n与此同时，远在千里之外。"
        result = run_anti_detection_gate(
            text, 10, str(tmp_project),
            checker_fn=lambda t, c: SAMPLE_CHECKER_PASS,
            polish_fn=lambda t, p, c: t,
            config=default_config,
        )
        assert result.passed is False
        assert result.zero_tolerance_hit == "ZT_MEANWHILE"

    def test_attempt_dataclass(self):
        attempt = AntiDetectionAttempt(
            attempt=1, score=65.0, violations=[], fix_prompt="fix", passed=False,
        )
        assert attempt.attempt == 1
        assert attempt.passed is False

    def test_result_dataclass(self):
        result = AntiDetectionResult(
            chapter_no=1, passed=True, final_score=85.0, threshold=70.0,
        )
        assert result.chapter_no == 1
        assert result.zero_tolerance_hit is None

    def test_log_file_created(self, tmp_project: Path, default_config: AntiDetectionConfig):
        run_anti_detection_gate(
            "clean text no time markers", 7, str(tmp_project),
            checker_fn=lambda t, c: SAMPLE_CHECKER_PASS,
            polish_fn=lambda t, p, c: t,
            config=default_config,
        )
        log_path = tmp_project / "logs" / "anti-detection" / "chapter_7.log"
        assert log_path.exists()


# ---------------------------------------------------------------------------
# Integration test: deliberately AI-tasting fixture chapter
# ---------------------------------------------------------------------------


class TestAITasteIntegration:
    def test_ai_taste_fixture_triggers_diversity_violations(self):
        cfg = AntiDetectionConfig()
        report = analyze_diversity(AI_TASTE_FIXTURE, cfg)
        violation_ids = {v.id for v in report.violations}
        assert len(report.violations) >= 3
        high_sev = [v for v in report.violations if v.severity == "high"]
        assert len(high_sev) >= 2

    def test_human_fixture_has_better_metrics(self):
        cfg = AntiDetectionConfig()
        ai_report = analyze_diversity(AI_TASTE_FIXTURE, cfg)
        human_report = analyze_diversity(HUMAN_LIKE_FIXTURE, cfg)
        assert human_report.sentence_cv > ai_report.sentence_cv
        assert human_report.dialogue_ratio > ai_report.dialogue_ratio

    def test_full_gate_with_ai_fixture(self, tmp_project: Path, default_config: AntiDetectionConfig):
        """Simulate full gate: checker returns low score for AI text, polish called, still fails → block."""
        call_count = [0]

        def checker_fn(text, chapter):
            call_count[0] += 1
            return SAMPLE_CHECKER_FAIL

        polish_calls = []

        def polish_fn(text, fix_prompt, chapter):
            polish_calls.append(fix_prompt)
            return text

        result = run_anti_detection_gate(
            AI_TASTE_FIXTURE, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )
        assert result.passed is False
        assert result.blocked_path is not None
        assert call_count[0] == 1  # max_retries=1 means one check only

    def test_full_gate_with_human_fixture_passes(self, tmp_project: Path, default_config: AntiDetectionConfig):
        """Human-like text with passing checker score goes through cleanly."""
        result = run_anti_detection_gate(
            HUMAN_LIKE_FIXTURE, 10, str(tmp_project),
            checker_fn=lambda t, c: SAMPLE_CHECKER_PASS,
            polish_fn=lambda t, p, c: t,
            config=default_config,
        )
        assert result.passed is True
        assert result.zero_tolerance_hit is None
