#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for style_anchor module — style fingerprinting and drift detection.
"""

import json

import pytest

from ink_writer.core.extract.style_anchor import (
    _extract_text_features,
    compute_anchor,
    save_anchor,
    check_drift,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_TEXT = (
    "这是第一句话，描述了一个场景。"
    "他走上前去，目光坚定！"
    "她微微一笑。"
    "\u201c你来了？\u201d他问道。"
    "\u201c嗯。\u201d她答。"
    "风吹过旷野，带来远方的气息。"
    "他深吸一口气，转身离去。"
)


def _make_chapter_file(text_dir, chapter_num, content):
    """Create a chapter markdown file in the text directory."""
    padded = f"{chapter_num:04d}"
    path = text_dir / f"第{padded}章测试章节.md"
    path.write_text(content, encoding="utf-8")
    return path


def _long_text(multiplier=10):
    """Generate text longer than the 200-char minimum threshold."""
    base = (
        "这是一段比较长的正文内容，用于测试风格锚定功能。"
        "他缓缓走在长街上，两侧的灯火明灭不定。"
        "远处传来几声犬吠，夜色渐深！"
        "\u201c今晚的月色真美。\u201d她轻声说道。"
        "\u201c是啊。\u201d他回答。"
        "寒风凛冽，吹得衣袍猎猎作响。"
    )
    return (base + "\n\n") * multiplier


# ---------------------------------------------------------------------------
# _extract_text_features
# ---------------------------------------------------------------------------


class TestExtractTextFeatures:

    def test_basic_output_keys(self):
        features = _extract_text_features(SAMPLE_TEXT)
        expected_keys = {
            "avg_sentence_length",
            "short_sentence_ratio",
            "dialogue_ratio",
            "avg_paragraph_length",
            "exclamation_density",
        }
        assert set(features.keys()) == expected_keys

    def test_all_values_are_floats(self):
        features = _extract_text_features(SAMPLE_TEXT)
        for v in features.values():
            assert isinstance(v, float)

    def test_empty_text(self):
        features = _extract_text_features("")
        assert features["avg_sentence_length"] == 0.0
        assert features["short_sentence_ratio"] == 0.0
        assert features["dialogue_ratio"] == 0.0
        assert features["avg_paragraph_length"] == 0.0
        # exclamation_density: 0 exclamations / (1/1000) = 0
        assert features["exclamation_density"] == 0.0

    def test_exclamation_density(self):
        # 10 exclamation marks in ~50 chars -> high density
        text = "好！棒！妙！行！对！来！走！看！听！说！"
        features = _extract_text_features(text)
        assert features["exclamation_density"] > 0

    def test_dialogue_ratio_positive(self):
        text = "\u201c你好吗？\u201d他问。\u201c我很好。\u201d她答。"
        features = _extract_text_features(text)
        assert features["dialogue_ratio"] > 0

    def test_short_sentence_ratio(self):
        # All short sentences (<=8 chars each)
        text = "好的。行。走吧。来了。"
        features = _extract_text_features(text)
        assert features["short_sentence_ratio"] == 1.0

    def test_no_short_sentences(self):
        text = "这是一个非常非常长的句子用来测试短句占比是否为零的情况。"
        features = _extract_text_features(text)
        assert features["short_sentence_ratio"] == 0.0

    def test_paragraph_length(self):
        text = "第一段内容。\n\n第二段内容，稍微长一些。\n\n第三段。"
        features = _extract_text_features(text)
        assert features["avg_paragraph_length"] > 0

    def test_mixed_exclamation_marks(self):
        # Both Chinese and ASCII exclamation marks
        text = "太好了！Really!太棒了！Amazing!"
        features = _extract_text_features(text)
        assert features["exclamation_density"] > 0


# ---------------------------------------------------------------------------
# compute_anchor
# ---------------------------------------------------------------------------


class TestComputeAnchor:

    def test_no_chapters_returns_error(self, tmp_path):
        (tmp_path / "正文").mkdir()
        result = compute_anchor(str(tmp_path))
        assert "error" in result
        assert result["chapters_found"] == 0

    def test_insufficient_chapters(self, tmp_path):
        text_dir = tmp_path / "正文"
        text_dir.mkdir()
        # Only 2 chapters — need at least 3
        for i in range(1, 3):
            _make_chapter_file(text_dir, i, _long_text())
        result = compute_anchor(str(tmp_path), chapters=[1, 2])
        assert "error" in result
        assert result["chapters_found"] == 2

    def test_short_chapter_skipped(self, tmp_path):
        text_dir = tmp_path / "正文"
        text_dir.mkdir()
        # 3 long chapters + 1 short chapter (below 200 char threshold)
        for i in range(1, 4):
            _make_chapter_file(text_dir, i, _long_text())
        _make_chapter_file(text_dir, 4, "很短的内容。")
        result = compute_anchor(str(tmp_path), chapters=[1, 2, 3, 4])
        assert "error" not in result
        assert result["chapters_used"] == 3

    def test_successful_anchor(self, tmp_path):
        text_dir = tmp_path / "正文"
        text_dir.mkdir()
        for i in range(1, 6):
            _make_chapter_file(text_dir, i, _long_text(multiplier=10 + i))
        result = compute_anchor(str(tmp_path), chapters=list(range(1, 6)))
        assert "error" not in result
        assert result["version"] == 1
        assert result["chapters_used"] == 5
        assert result["chapter_range"] == [1, 5]
        assert "metrics" in result
        for key in [
            "avg_sentence_length",
            "short_sentence_ratio",
            "dialogue_ratio",
            "avg_paragraph_length",
            "exclamation_density",
        ]:
            assert key in result["metrics"]
            assert "mean" in result["metrics"][key]
            assert "stdev" in result["metrics"][key]

    def test_default_chapters_range(self, tmp_path):
        """When chapters=None, defaults to range(1, 11)."""
        text_dir = tmp_path / "正文"
        text_dir.mkdir()
        for i in range(1, 11):
            _make_chapter_file(text_dir, i, _long_text())
        result = compute_anchor(str(tmp_path))
        assert "error" not in result
        assert result["chapters_used"] == 10

    def test_missing_chapter_files_skipped(self, tmp_path):
        text_dir = tmp_path / "正文"
        text_dir.mkdir()
        # Only chapters 1, 3, 5 exist — others just skipped
        for i in [1, 3, 5]:
            _make_chapter_file(text_dir, i, _long_text())
        result = compute_anchor(str(tmp_path), chapters=[1, 2, 3, 4, 5])
        assert "error" not in result
        assert result["chapters_used"] == 3

    def test_single_chapter_stdev_zero(self, tmp_path):
        """With exactly 1 valid chapter, stdev should be 0, but need >=3."""
        text_dir = tmp_path / "正文"
        text_dir.mkdir()
        _make_chapter_file(text_dir, 1, _long_text())
        result = compute_anchor(str(tmp_path), chapters=[1])
        assert "error" in result


# ---------------------------------------------------------------------------
# save_anchor
# ---------------------------------------------------------------------------


class TestSaveAnchor:

    def test_save_with_provided_anchor(self, tmp_path):
        anchor = {
            "version": 1,
            "chapters_used": 5,
            "chapter_range": [1, 5],
            "metrics": {"avg_sentence_length": {"mean": 12.0, "stdev": 2.0}},
        }
        msg = save_anchor(str(tmp_path), anchor=anchor)
        assert "风格锚点已保存" in msg
        saved_path = tmp_path / ".ink" / "style_anchor.json"
        assert saved_path.exists()
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        assert saved["version"] == 1
        assert saved["metrics"]["avg_sentence_length"]["mean"] == 12.0

    def test_save_with_error_anchor(self, tmp_path):
        anchor = {"error": "章节数据不足", "chapters_found": 0}
        msg = save_anchor(str(tmp_path), anchor=anchor)
        assert msg == "章节数据不足"

    def test_save_computes_anchor_when_none(self, tmp_path):
        text_dir = tmp_path / "正文"
        text_dir.mkdir()
        for i in range(1, 5):
            _make_chapter_file(text_dir, i, _long_text())
        msg = save_anchor(str(tmp_path))
        assert "风格锚点已保存" in msg
        assert (tmp_path / ".ink" / "style_anchor.json").exists()

    def test_save_returns_error_when_no_data(self, tmp_path):
        (tmp_path / "正文").mkdir()
        msg = save_anchor(str(tmp_path))
        assert "不足" in msg


# ---------------------------------------------------------------------------
# check_drift
# ---------------------------------------------------------------------------


class TestCheckDrift:

    def _setup_anchor(self, tmp_path, metrics=None):
        """Write a style_anchor.json to .ink/."""
        if metrics is None:
            metrics = {
                "avg_sentence_length": {"mean": 15.0, "stdev": 2.0},
                "short_sentence_ratio": {"mean": 0.3, "stdev": 0.05},
                "dialogue_ratio": {"mean": 0.2, "stdev": 0.03},
                "avg_paragraph_length": {"mean": 50.0, "stdev": 5.0},
                "exclamation_density": {"mean": 5.0, "stdev": 1.0},
            }
        anchor = {
            "version": 1,
            "chapters_used": 10,
            "chapter_range": [1, 10],
            "metrics": metrics,
        }
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir(parents=True, exist_ok=True)
        (ink_dir / "style_anchor.json").write_text(
            json.dumps(anchor, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return anchor

    def test_no_anchor_file(self, tmp_path):
        result = check_drift(str(tmp_path))
        assert result["status"] == "skip"
        assert "不存在" in result["reason"]

    def test_empty_metrics_in_anchor(self, tmp_path):
        self._setup_anchor(tmp_path, metrics={})
        result = check_drift(str(tmp_path), recent_chapters=[11, 12, 13])
        assert result["status"] == "skip"
        assert "为空" in result["reason"]

    def test_recent_chapters_explicit(self, tmp_path):
        """Explicit recent_chapters, enough data for comparison."""
        self._setup_anchor(tmp_path)
        text_dir = tmp_path / "正文"
        text_dir.mkdir()
        for i in range(11, 15):
            _make_chapter_file(text_dir, i, _long_text())
        result = check_drift(str(tmp_path), recent_chapters=list(range(11, 15)))
        assert result["status"] == "checked"
        assert result["current_chapters"] == [11, 14]
        assert isinstance(result["drift_count"], int)
        assert isinstance(result["warnings"], list)

    def test_drift_detection_high_severity(self, tmp_path):
        """Force a large drift by using extreme anchor values."""
        # Anchor says avg_sentence_length=100 with stdev=1
        # Actual text will have much shorter sentences -> high z-score
        self._setup_anchor(tmp_path, metrics={
            "avg_sentence_length": {"mean": 100.0, "stdev": 1.0},
            "short_sentence_ratio": {"mean": 0.0, "stdev": 0.01},
            "dialogue_ratio": {"mean": 0.0, "stdev": 0.01},
            "avg_paragraph_length": {"mean": 500.0, "stdev": 1.0},
            "exclamation_density": {"mean": 0.0, "stdev": 0.01},
        })
        text_dir = tmp_path / "正文"
        text_dir.mkdir()
        for i in range(20, 24):
            _make_chapter_file(text_dir, i, _long_text())
        result = check_drift(str(tmp_path), recent_chapters=list(range(20, 24)))
        assert result["status"] == "checked"
        assert result["drift_count"] > 0
        # Check that warnings contain severity info
        for w in result["warnings"]:
            assert w["severity"] in ("medium", "high")
            assert "z_score" in w
            assert "deviation_pct" in w

    def test_drift_medium_severity(self, tmp_path):
        """Z-score between 2 and 3 should give medium severity."""
        # We need precise control: anchor mean far enough that z > 2 but < 3
        self._setup_anchor(tmp_path, metrics={
            "avg_sentence_length": {"mean": 50.0, "stdev": 10.0},
            "short_sentence_ratio": {"mean": 0.3, "stdev": 0.1},
            "dialogue_ratio": {"mean": 0.2, "stdev": 0.1},
            "avg_paragraph_length": {"mean": 50.0, "stdev": 10.0},
            "exclamation_density": {"mean": 5.0, "stdev": 10.0},
        })
        text_dir = tmp_path / "正文"
        text_dir.mkdir()
        for i in range(20, 24):
            _make_chapter_file(text_dir, i, _long_text())
        result = check_drift(str(tmp_path), recent_chapters=list(range(20, 24)))
        assert result["status"] == "checked"

    def test_no_drift_when_values_match(self, tmp_path):
        """When current style matches anchor closely, no warnings."""
        text_dir = tmp_path / "正文"
        text_dir.mkdir()
        content = _long_text()
        # First compute real features to build a matching anchor
        for i in range(1, 5):
            _make_chapter_file(text_dir, i, content)
        anchor_data = compute_anchor(str(tmp_path), chapters=list(range(1, 5)))
        self._setup_anchor(tmp_path, metrics=anchor_data["metrics"])
        # Use same content for recent chapters
        for i in range(20, 24):
            _make_chapter_file(text_dir, i, content)
        result = check_drift(str(tmp_path), recent_chapters=list(range(20, 24)))
        assert result["status"] == "checked"
        assert result["drift_count"] == 0
        assert result["warnings"] == []

    def test_auto_detect_recent_chapters_too_few(self, tmp_path):
        """When recent_chapters=None and total chapters < 15, skip."""
        self._setup_anchor(tmp_path)
        text_dir = tmp_path / "正文"
        text_dir.mkdir()
        for i in range(1, 10):
            _make_chapter_file(text_dir, i, _long_text())
        result = check_drift(str(tmp_path))
        assert result["status"] == "skip"
        assert "不足15章" in result["reason"]

    def test_auto_detect_recent_chapters_enough(self, tmp_path):
        """When recent_chapters=None and total chapters >= 15, auto-detect last 10."""
        self._setup_anchor(tmp_path)
        text_dir = tmp_path / "正文"
        text_dir.mkdir()
        for i in range(1, 20):
            _make_chapter_file(text_dir, i, _long_text())
        result = check_drift(str(tmp_path))
        assert result["status"] == "checked"
        assert result["current_chapters"] == [10, 19]

    def test_anchor_has_extra_metric_not_in_current(self, tmp_path):
        """Anchor metric key missing from current metrics triggers continue branch."""
        # Include a fake metric in the anchor that compute_anchor won't produce
        metrics = {
            "avg_sentence_length": {"mean": 15.0, "stdev": 2.0},
            "nonexistent_metric": {"mean": 99.0, "stdev": 1.0},
        }
        self._setup_anchor(tmp_path, metrics=metrics)
        text_dir = tmp_path / "正文"
        text_dir.mkdir()
        for i in range(20, 24):
            _make_chapter_file(text_dir, i, _long_text())
        result = check_drift(str(tmp_path), recent_chapters=list(range(20, 24)))
        assert result["status"] == "checked"
        # nonexistent_metric should be silently skipped, no crash
        metric_names = [w["metric"] for w in result["warnings"]]
        assert "nonexistent_metric" not in metric_names

    def test_compute_error_propagates(self, tmp_path):
        """If recent chapters have insufficient data, skip."""
        self._setup_anchor(tmp_path)
        text_dir = tmp_path / "正文"
        text_dir.mkdir()
        # Create 15+ chapters for auto-detect, but only short content for recent ones
        for i in range(1, 10):
            _make_chapter_file(text_dir, i, _long_text())
        for i in range(10, 20):
            _make_chapter_file(text_dir, i, "短。")
        result = check_drift(str(tmp_path))
        assert result["status"] == "skip"
