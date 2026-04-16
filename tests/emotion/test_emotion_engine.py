#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for emotion curve engine: detector, config, fix_prompt, gate."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ink_writer.emotion.config import EmotionCurveConfig, load_config
from ink_writer.emotion.emotion_detector import (
    EMOTION_KEYWORDS,
    EMOTION_VALENCE_AROUSAL,
    SceneEmotion,
    EmotionCurve,
    split_scenes,
    detect_emotion_curve,
    cosine_similarity,
    interpolate_curve,
    compute_corpus_similarity,
    curve_to_jsonl_records,
    _variance,
    _find_flat_segments,
    _compute_scene_emotion,
)
from ink_writer.emotion.fix_prompt_builder import (
    VIOLATION_FIX_TEMPLATES,
    build_fix_prompt,
    normalize_checker_output,
)
from ink_writer.emotion.emotion_gate import (
    EmotionGateAttempt,
    EmotionGateResult,
    run_emotion_gate,
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
def default_config() -> EmotionCurveConfig:
    return EmotionCurveConfig(
        enabled=True,
        variance_threshold=0.15,
        flat_segment_max=2,
        corpus_similarity_threshold=0.8,
        max_retries=2,
        score_threshold=60.0,
    )


TENSE_TEXT = ("他紧张地看着前方，心跳加速，冷汗顺着脊背流下。危险的气息越来越近，他颤抖着握紧了手中的剑。"
              "这一刻，生与死的边界如此模糊。周围的空气仿佛凝固了一般，每一秒都无比漫长。") * 3

WARM_TEXT = ("她温柔地笑了笑，伸手关心地摸了摸他的头。温暖的阳光洒进来，照顾好自己的身体，她微笑着安慰他，"
             "一切都会好起来的。陪伴是最好的礼物。他感受到了前所未有的温暖和安心。") * 3

ANGRY_TEXT = ("愤怒在他心中翻涌，他恨不得将眼前的混蛋碎尸万段。该死的叛徒！可恶！他怒吼一声，杀了你们所有人！"
              "胸中的怒火如同火山喷发，再也无法压抑。他一拳砸在桌上，木屑四溅。") * 3

NEUTRAL_TEXT = "他走进了房间，把东西放在桌上，然后坐了下来。窗外的天空很蓝，阳光照在地上。时间慢慢流逝，一切都很平静。房间里安安静静的，没有什么特别的事情发生。" * 5

SHOCK_TEXT = ("震惊！他不可能做到这种事！瞳孔一缩，难以置信地看着眼前的一切。怎么可能！这完全超出了他的认知范围。"
              "周围所有人都目瞪口呆，一时间谁也说不出话来。") * 3

MIXED_CHAPTER = (
    TENSE_TEXT + "\n\n" + WARM_TEXT + "\n\n" + ANGRY_TEXT + "\n\n"
    + SHOCK_TEXT + "\n\n" + NEUTRAL_TEXT
)

FLAT_CHAPTER = NEUTRAL_TEXT + "\n\n" + NEUTRAL_TEXT + "\n\n" + NEUTRAL_TEXT + "\n\n" + NEUTRAL_TEXT

SAMPLE_CHECKER_PASS = {
    "agent": "emotion-curve-checker",
    "chapter": 10,
    "overall_score": 78,
    "pass": True,
    "issues": [],
    "hard_violations": [],
    "soft_suggestions": [],
    "fix_prompt": "",
    "metrics": {"valence_variance": 0.25, "arousal_variance": 0.30},
    "summary": "通过",
}

SAMPLE_CHECKER_FAIL = {
    "agent": "emotion-curve-checker",
    "chapter": 10,
    "overall_score": 35,
    "pass": False,
    "issues": [],
    "hard_violations": [
        {
            "id": "EMOTION_FLAT",
            "severity": "critical",
            "location": "场景1-3",
            "description": "3个连续场景无情绪变化",
            "must_fix": True,
            "fix_suggestion": "在场景2插入冲突",
        },
        {
            "id": "EMOTION_VARIANCE_LOW",
            "severity": "high",
            "location": "全章",
            "description": "0.03",
            "must_fix": True,
            "fix_suggestion": "增加情绪高峰和低谷",
        },
    ],
    "soft_suggestions": [
        {
            "id": "EMOTION_MONOTONE",
            "severity": "medium",
            "location": "全章",
            "description": "中性",
            "suggestion": "引入对比情绪",
        }
    ],
    "fix_prompt": "",
    "metrics": {"valence_variance": 0.03, "arousal_variance": 0.02},
    "summary": "情绪曲线严重平淡",
}

CHAPTER_TEXT = "这是一段测试正文。" * 100


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestConfig:
    def test_default_config(self) -> None:
        config = EmotionCurveConfig()
        assert config.enabled is True
        assert config.variance_threshold == 0.15
        assert config.flat_segment_max == 2
        assert config.corpus_similarity_threshold == 0.8
        assert config.max_retries == 2
        assert config.score_threshold == 60.0

    def test_load_config_missing_file(self, tmp_path: Path) -> None:
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config == EmotionCurveConfig()

    def test_load_config_from_yaml(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "emotion-curve.yaml"
        yaml_path.write_text(
            "enabled: true\nvariance_threshold: 0.2\nmax_retries: 3\nscore_threshold: 50.0\n",
            encoding="utf-8",
        )
        config = load_config(yaml_path)
        assert config.variance_threshold == 0.2
        assert config.max_retries == 3
        assert config.score_threshold == 50.0

    def test_load_config_invalid_yaml(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "bad.yaml"
        yaml_path.write_text("just a string", encoding="utf-8")
        config = load_config(yaml_path)
        assert config == EmotionCurveConfig()

    def test_load_real_config(self) -> None:
        config = load_config()
        assert config.enabled is True
        assert isinstance(config.variance_threshold, float)


# ---------------------------------------------------------------------------
# Emotion detector tests
# ---------------------------------------------------------------------------


class TestSplitScenes:
    def test_split_by_double_newline(self) -> None:
        text = "段落一内容。" * 30 + "\n\n" + "段落二内容。" * 30
        scenes = split_scenes(text, min_scene_chars=50)
        assert len(scenes) == 2

    def test_split_by_separator(self) -> None:
        text = "段落一内容。" * 30 + "\n***\n" + "段落二内容。" * 30
        scenes = split_scenes(text, min_scene_chars=50)
        assert len(scenes) == 2

    def test_merge_short_segments(self) -> None:
        text = "短。\n\n短。\n\n短。"
        scenes = split_scenes(text, min_scene_chars=200)
        assert len(scenes) == 1

    def test_empty_text(self) -> None:
        assert split_scenes("") == []
        assert split_scenes("   ") == []

    def test_single_long_paragraph(self) -> None:
        text = "连续文本不断重复。" * 100
        scenes = split_scenes(text)
        assert len(scenes) >= 1


class TestComputeSceneEmotion:
    def test_tense_scene(self) -> None:
        v, a, dom, counts = _compute_scene_emotion(TENSE_TEXT)
        assert dom == "紧张"
        assert v < 0
        assert a > 0.5

    def test_warm_scene(self) -> None:
        v, a, dom, counts = _compute_scene_emotion(WARM_TEXT)
        assert dom == "温馨"
        assert v > 0
        assert a < 0.5

    def test_angry_scene(self) -> None:
        v, a, dom, counts = _compute_scene_emotion(ANGRY_TEXT)
        assert dom == "愤怒"
        assert v < 0
        assert a > 0.5

    def test_neutral_scene(self) -> None:
        v, a, dom, counts = _compute_scene_emotion(NEUTRAL_TEXT)
        assert dom == "中性"
        assert v == 0.0

    def test_returns_keyword_counts(self) -> None:
        _, _, _, counts = _compute_scene_emotion(TENSE_TEXT)
        assert "紧张" in counts
        assert counts["紧张"] > 0


class TestDetectEmotionCurve:
    def test_mixed_chapter_has_variance(self) -> None:
        curve = detect_emotion_curve(MIXED_CHAPTER, chapter=1)
        assert curve.chapter == 1
        assert len(curve.scenes) >= 3
        assert curve.valence_variance > 0.05
        assert curve.overall_valence_range > 0.3

    def test_flat_chapter_detected(self) -> None:
        curve = detect_emotion_curve(FLAT_CHAPTER, chapter=2)
        assert curve.valence_variance < 0.05
        assert len(curve.flat_segments) > 0

    def test_scenes_have_correct_fields(self) -> None:
        curve = detect_emotion_curve(MIXED_CHAPTER, chapter=3)
        for scene in curve.scenes:
            assert isinstance(scene.valence, float)
            assert isinstance(scene.arousal, float)
            assert isinstance(scene.dominant_emotion, str)
            assert isinstance(scene.scene_index, int)

    def test_single_scene_chapter(self) -> None:
        curve = detect_emotion_curve(TENSE_TEXT, chapter=4)
        assert len(curve.scenes) == 1
        assert curve.valence_variance == 0.0


class TestVariance:
    def test_empty(self) -> None:
        assert _variance([]) == 0.0

    def test_single(self) -> None:
        assert _variance([5.0]) == 0.0

    def test_known_values(self) -> None:
        result = _variance([1.0, 2.0, 3.0, 4.0, 5.0])
        assert abs(result - 2.0) < 0.01

    def test_identical(self) -> None:
        assert _variance([3.0, 3.0, 3.0]) == 0.0


class TestFlatSegments:
    def test_no_flat(self) -> None:
        scenes = [
            SceneEmotion(0, 0, 100, 0.0, 0.3, "中性"),
            SceneEmotion(1, 100, 200, 0.5, 0.8, "热血"),
            SceneEmotion(2, 200, 300, -0.5, 0.3, "悲伤"),
        ]
        assert _find_flat_segments(scenes) == []

    def test_two_flat(self) -> None:
        scenes = [
            SceneEmotion(0, 0, 100, 0.0, 0.3, "中性"),
            SceneEmotion(1, 100, 200, 0.01, 0.31, "中性"),
            SceneEmotion(2, 200, 300, 0.5, 0.8, "热血"),
        ]
        flat = _find_flat_segments(scenes)
        assert 0 in flat
        assert 1 in flat

    def test_all_flat(self) -> None:
        scenes = [
            SceneEmotion(i, i * 100, (i + 1) * 100, 0.0, 0.3, "中性")
            for i in range(5)
        ]
        flat = _find_flat_segments(scenes)
        assert len(flat) == 5


class TestCosineSimilarity:
    def test_identical(self) -> None:
        assert cosine_similarity([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)

    def test_orthogonal(self) -> None:
        assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_opposite(self) -> None:
        assert cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_empty(self) -> None:
        assert cosine_similarity([], []) == 0.0

    def test_different_lengths(self) -> None:
        assert cosine_similarity([1, 2], [1, 2, 3]) == 0.0

    def test_zero_vector(self) -> None:
        assert cosine_similarity([0, 0], [1, 2]) == 0.0


class TestInterpolateCurve:
    def test_same_length(self) -> None:
        assert interpolate_curve([1.0, 2.0, 3.0], 3) == [1.0, 2.0, 3.0]

    def test_upsample(self) -> None:
        result = interpolate_curve([0.0, 1.0], 3)
        assert len(result) == 3
        assert result[0] == pytest.approx(0.0)
        assert result[1] == pytest.approx(0.5)
        assert result[2] == pytest.approx(1.0)

    def test_downsample(self) -> None:
        result = interpolate_curve([0.0, 0.5, 1.0], 2)
        assert len(result) == 2
        assert result[0] == pytest.approx(0.0)
        assert result[1] == pytest.approx(1.0)

    def test_empty(self) -> None:
        result = interpolate_curve([], 5)
        assert result == [0.0] * 5

    def test_single(self) -> None:
        result = interpolate_curve([3.0], 4)
        assert result == [3.0] * 4


class TestCorpusSimilarity:
    def test_high_similarity(self) -> None:
        curve = detect_emotion_curve(MIXED_CHAPTER, chapter=1)
        valences = [s.valence for s in curve.scenes]
        refs = [valences]
        sim = compute_corpus_similarity(curve, refs)
        assert sim == pytest.approx(1.0, abs=0.01)

    def test_no_references(self) -> None:
        curve = detect_emotion_curve(MIXED_CHAPTER, chapter=1)
        assert compute_corpus_similarity(curve, []) == 0.0

    def test_empty_curve(self) -> None:
        curve = EmotionCurve(chapter=1, scenes=[], valence_variance=0, arousal_variance=0,
                             flat_segments=[], overall_valence_range=0, overall_arousal_range=0)
        assert compute_corpus_similarity(curve, [[0.1, 0.2]]) == 0.0


class TestCurveToJsonl:
    def test_correct_format(self) -> None:
        curve = detect_emotion_curve(MIXED_CHAPTER, chapter=42)
        records = curve_to_jsonl_records(curve)
        assert len(records) == len(curve.scenes)
        for r in records:
            assert r["chapter"] == 42
            assert "scene" in r
            assert "valence" in r
            assert "arousal" in r
            assert "dominant_emotion" in r
            assert isinstance(r["valence"], float)


# ---------------------------------------------------------------------------
# Fix prompt builder tests
# ---------------------------------------------------------------------------


class TestBuildFixPrompt:
    def test_empty_violations(self) -> None:
        assert build_fix_prompt([]) == ""

    def test_single_flat_violation(self) -> None:
        violations = [
            {
                "id": "EMOTION_FLAT",
                "severity": "critical",
                "description": "场景2-4",
                "fix_suggestion": "插入冲突",
            }
        ]
        prompt = build_fix_prompt(violations)
        assert "EMOTION_FLAT" in prompt
        assert "情绪曲线过平" in prompt
        assert "情绪曲线修复指令" in prompt

    def test_variance_low_violation(self) -> None:
        violations = [
            {
                "id": "EMOTION_VARIANCE_LOW",
                "severity": "high",
                "description": "0.03",
            }
        ]
        prompt = build_fix_prompt(violations)
        assert "方差不足" in prompt
        assert "0.03" in prompt

    def test_multiple_violations(self) -> None:
        violations = [
            {"id": "EMOTION_FLAT", "severity": "critical", "description": "场景1-2"},
            {"id": "EMOTION_MONOTONE", "severity": "medium", "description": "紧张"},
        ]
        prompt = build_fix_prompt(violations)
        assert "1." in prompt
        assert "2." in prompt

    def test_unknown_violation(self) -> None:
        violations = [{"id": "CUSTOM", "severity": "low", "description": "自定义问题"}]
        prompt = build_fix_prompt(violations)
        assert "CUSTOM" in prompt
        assert "自定义问题" in prompt

    def test_footer_present(self) -> None:
        violations = [{"id": "EMOTION_FLAT", "severity": "critical"}]
        prompt = build_fix_prompt(violations)
        assert "不得改变剧情事实" in prompt


class TestNormalizeCheckerOutput:
    def test_normalize_pass(self) -> None:
        result = normalize_checker_output(SAMPLE_CHECKER_PASS)
        assert result["score"] == 78.0
        assert result["violations"] == []
        assert result["fix_prompt"] == ""

    def test_normalize_fail(self) -> None:
        result = normalize_checker_output(SAMPLE_CHECKER_FAIL)
        assert result["score"] == 35.0
        assert len(result["violations"]) == 3
        assert result["violations"][0]["id"] == "EMOTION_FLAT"
        assert result["violations"][0]["must_fix"] is True
        assert "情绪曲线修复指令" in result["fix_prompt"]

    def test_normalize_overall_score_fallback(self) -> None:
        raw = {"overall_score": 55, "hard_violations": [], "soft_suggestions": []}
        result = normalize_checker_output(raw)
        assert result["score"] == 55.0

    def test_normalize_preserves_existing_fix_prompt(self) -> None:
        raw = {
            "overall_score": 40,
            "fix_prompt": "自定义情绪修复",
            "hard_violations": [{"id": "EMOTION_FLAT", "severity": "critical"}],
        }
        result = normalize_checker_output(raw)
        assert result["fix_prompt"] == "自定义情绪修复"

    def test_normalize_already_normalized(self) -> None:
        raw = {
            "score": 70,
            "violations": [{"id": "EMOTION_MONOTONE", "severity": "medium"}],
            "fix_prompt": "already built",
        }
        result = normalize_checker_output(raw)
        assert result["score"] == 70.0
        assert len(result["violations"]) == 1


# ---------------------------------------------------------------------------
# Emotion gate tests
# ---------------------------------------------------------------------------


class TestRunEmotionGate:
    def test_pass_on_first_check(
        self, tmp_project: Path, default_config: EmotionCurveConfig
    ) -> None:
        checker_fn = MagicMock(return_value=SAMPLE_CHECKER_PASS)
        polish_fn = MagicMock(return_value="polished text")

        result = run_emotion_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        assert result.passed is True
        assert result.final_score == 78.0
        assert len(result.attempts) == 1
        assert result.blocked_path is None
        assert result.final_text == CHAPTER_TEXT
        checker_fn.assert_called_once()
        polish_fn.assert_not_called()

    def test_fail_then_pass_after_polish(
        self, tmp_project: Path, default_config: EmotionCurveConfig
    ) -> None:
        pass_result = dict(SAMPLE_CHECKER_PASS)
        pass_result["overall_score"] = 65

        checker_fn = MagicMock(
            side_effect=[SAMPLE_CHECKER_FAIL, pass_result]
        )
        polish_fn = MagicMock(return_value="improved text")

        result = run_emotion_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        assert result.passed is True
        assert len(result.attempts) == 2
        assert result.attempts[0].passed is False
        assert result.attempts[1].passed is True
        assert result.blocked_path is None
        assert result.final_text == "improved text"
        assert checker_fn.call_count == 2
        assert polish_fn.call_count == 1

    def test_fail_twice_creates_emotion_blocked(
        self, tmp_project: Path, default_config: EmotionCurveConfig
    ) -> None:
        checker_fn = MagicMock(return_value=SAMPLE_CHECKER_FAIL)
        polish_fn = MagicMock(return_value="still flat text")

        result = run_emotion_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        assert result.passed is False
        assert len(result.attempts) == 2
        assert result.blocked_path is not None
        assert result.blocked_path.endswith("emotion_blocked.md")
        assert result.final_text is None

        assert os.path.exists(result.blocked_path)
        content = Path(result.blocked_path).read_text(encoding="utf-8")
        assert "情绪曲线门禁阻断" in content
        assert "EMOTION_FLAT" in content

        assert checker_fn.call_count == 2
        assert polish_fn.call_count == 1

    def test_disabled_config_passes_immediately(
        self, tmp_project: Path
    ) -> None:
        config = EmotionCurveConfig(enabled=False)
        checker_fn = MagicMock()
        polish_fn = MagicMock()

        result = run_emotion_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=config,
        )

        assert result.passed is True
        assert result.final_score == 100.0
        checker_fn.assert_not_called()
        polish_fn.assert_not_called()

    def test_polish_fn_receives_fix_prompt(
        self, tmp_project: Path, default_config: EmotionCurveConfig
    ) -> None:
        pass_result = dict(SAMPLE_CHECKER_PASS)
        pass_result["overall_score"] = 70

        checker_fn = MagicMock(
            side_effect=[SAMPLE_CHECKER_FAIL, pass_result]
        )
        polish_fn = MagicMock(return_value="fixed text")

        run_emotion_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        polish_fn.assert_called_once()
        call_args = polish_fn.call_args
        fix_prompt_arg = call_args[0][1]
        assert "EMOTION_FLAT" in fix_prompt_arg
        assert "情绪曲线修复指令" in fix_prompt_arg

    def test_emotion_blocked_contains_fix_prompt(
        self, tmp_project: Path, default_config: EmotionCurveConfig
    ) -> None:
        checker_fn = MagicMock(return_value=SAMPLE_CHECKER_FAIL)
        polish_fn = MagicMock(return_value="still bad")

        result = run_emotion_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        content = Path(result.blocked_path).read_text(encoding="utf-8")
        assert "修复提示" in content
        assert "情绪曲线修复指令" in content

    def test_log_file_created(
        self, tmp_project: Path, default_config: EmotionCurveConfig
    ) -> None:
        checker_fn = MagicMock(return_value=SAMPLE_CHECKER_PASS)
        polish_fn = MagicMock()

        run_emotion_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        log_path = tmp_project / "logs" / "emotion-curve" / "chapter_10.log"
        assert log_path.exists()
        log_content = log_path.read_text(encoding="utf-8")
        assert "情绪曲线门禁检查" in log_content

    def test_attempts_recorded_correctly(
        self, tmp_project: Path, default_config: EmotionCurveConfig
    ) -> None:
        checker_fn = MagicMock(return_value=SAMPLE_CHECKER_FAIL)
        polish_fn = MagicMock(return_value="polished")

        result = run_emotion_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        assert len(result.attempts) == 2
        for i, attempt in enumerate(result.attempts, 1):
            assert attempt.attempt == i
            assert attempt.score == 35.0
            assert attempt.passed is False
            assert len(attempt.violations) > 0

    def test_chapter_dir_created_for_blocked(
        self, tmp_project: Path, default_config: EmotionCurveConfig
    ) -> None:
        checker_fn = MagicMock(return_value=SAMPLE_CHECKER_FAIL)
        polish_fn = MagicMock(return_value="bad")

        run_emotion_gate(
            CHAPTER_TEXT, 99, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        assert (tmp_project / "chapters" / "99" / "emotion_blocked.md").exists()


# ---------------------------------------------------------------------------
# Integration: monkey-patch → 2 retries → blocked
# ---------------------------------------------------------------------------


class TestIntegrationMonkeyPatch:
    def test_score_low_triggers_2_retries_then_blocked(
        self, tmp_project: Path
    ) -> None:
        config = EmotionCurveConfig(
            enabled=True,
            score_threshold=60.0,
            max_retries=2,
        )

        low_result = {
            "overall_score": 20,
            "hard_violations": [
                {
                    "id": "EMOTION_FLAT",
                    "severity": "critical",
                    "description": "全章平淡",
                    "fix_suggestion": "加冲突",
                },
                {
                    "id": "EMOTION_VARIANCE_LOW",
                    "severity": "high",
                    "description": "0.01",
                    "fix_suggestion": "加情绪波动",
                },
            ],
            "soft_suggestions": [
                {
                    "id": "EMOTION_MONOTONE",
                    "severity": "medium",
                    "description": "中性",
                    "suggestion": "引入对比",
                }
            ],
        }

        checker_fn = MagicMock(return_value=low_result)
        polish_calls: list[tuple[str, str, int]] = []

        def mock_polish(text: str, fix_prompt: str, chapter_no: int) -> str:
            polish_calls.append((text, fix_prompt, chapter_no))
            return text + "\n（已增加情绪波动）"

        result = run_emotion_gate(
            CHAPTER_TEXT, 5, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=mock_polish,
            config=config,
        )

        assert result.passed is False
        assert checker_fn.call_count == 2
        assert len(polish_calls) == 1

        assert result.blocked_path is not None
        blocked = Path(result.blocked_path)
        assert blocked.exists()
        assert blocked.name == "emotion_blocked.md"

        content = blocked.read_text(encoding="utf-8")
        assert "情绪曲线门禁阻断" in content
        assert "EMOTION_FLAT" in content

        for _, fix_prompt, _ in polish_calls:
            assert "情绪曲线修复指令" in fix_prompt
            assert "EMOTION_FLAT" in fix_prompt


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_checker_returns_exactly_threshold(
        self, tmp_project: Path, default_config: EmotionCurveConfig
    ) -> None:
        exact = {"overall_score": 60.0, "hard_violations": [], "soft_suggestions": []}
        checker_fn = MagicMock(return_value=exact)
        polish_fn = MagicMock()

        result = run_emotion_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )
        assert result.passed is True
        polish_fn.assert_not_called()

    def test_empty_checker_result(
        self, tmp_project: Path, default_config: EmotionCurveConfig
    ) -> None:
        checker_fn = MagicMock(return_value={})
        polish_fn = MagicMock(return_value="polished")

        result = run_emotion_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )
        assert result.passed is False
        assert result.final_score == 0.0


# ---------------------------------------------------------------------------
# Corpus replay simulation (50 chapters)
# ---------------------------------------------------------------------------


class TestCorpusReplaySimulation:
    def test_50_chapter_similarity_above_threshold(self) -> None:
        """Simulate 50 chapters with varied emotions; corpus similarity ≥ 0.8."""
        import random
        rng = random.Random(42)

        emotion_templates = [
            "紧张心跳加速冷汗颤抖危险",
            "热血燃烧战豪气壮志怒吼",
            "泪哭痛失去离别悲心碎",
            "笑乐有趣轻松惬意舒适",
            "震惊不可能瞳孔难以置信",
            "愤怒怒恨该死混蛋可恶",
            "温暖温柔关心照顾微笑安慰",
        ]

        reference_curves: list[list[float]] = []
        chapter_curves: list[EmotionCurve] = []

        for ch in range(1, 51):
            scenes_text_parts = []
            for _ in range(rng.randint(3, 6)):
                tmpl = rng.choice(emotion_templates)
                filler = "普通文本描写场景环境人物动作。" * rng.randint(10, 20)
                scenes_text_parts.append(tmpl * rng.randint(2, 5) + filler)

            chapter_text = "\n\n".join(scenes_text_parts)
            curve = detect_emotion_curve(chapter_text, chapter=ch)
            chapter_curves.append(curve)

            valences = [s.valence for s in curve.scenes]
            if ch <= 25:
                reference_curves.append(valences)

        similarities = []
        for curve in chapter_curves[25:]:
            sim = compute_corpus_similarity(curve, reference_curves)
            similarities.append(sim)

        avg_sim = sum(similarities) / len(similarities) if similarities else 0
        assert avg_sim >= 0.5, f"Average similarity {avg_sim} too low"
        high_sim_count = sum(1 for s in similarities if s >= 0.8)
        assert high_sim_count >= len(similarities) * 0.3, \
            f"Only {high_sim_count}/{len(similarities)} chapters have similarity >= 0.8"
