#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""US-014: Tests for conjunction_density() and AD_CONJUNCTION_DENSE violation.

The conjunction_density helper counts how many book-ish connectives
(不仅/而且/尽管如此/毫无疑问/总而言之/...) appear per 1000 chars and the
anti-detection gate raises AD_CONJUNCTION_DENSE when density exceeds
``conjunction_density_max`` (default 2.5).

All tests are pure-Python (no LLM call).
"""

from __future__ import annotations

import pytest

from ink_writer.anti_detection.config import AntiDetectionConfig
from ink_writer.anti_detection.fix_prompt_builder import VIOLATION_FIX_TEMPLATES
from ink_writer.anti_detection.sentence_diversity import (
    analyze_diversity,
    conjunction_density,
)


# ---------------------------------------------------------------------------
# conjunction_density() unit tests
# ---------------------------------------------------------------------------


class TestConjunctionDensityFunction:
    def test_empty_returns_zero(self):
        assert conjunction_density("") == 0.0

    def test_short_text_returns_zero(self):
        # < 100 chars — the helper returns 0.0 to avoid noisy signals
        assert conjunction_density("不仅如此而且还有。") == 0.0

    def test_clean_long_text_low_density(self):
        clean = (
            "剑光一闪，血溅三尺。"
            "林渊后退半步，掌心已经被汗水打湿。"
            "他抬起头，看向对面的身影——那人一身黑衣，"
            "面覆青铜鬼面，手中长剑滴着血。"
            "风从山谷间灌上来，吹得他衣袂翻飞。"
            "他听见自己的心跳，一下，一下，像战鼓。"
        ) * 3
        density = conjunction_density(clean)
        assert density < 2.5

    def test_heavy_conjunction_text_high_density(self):
        heavy = (
            "不仅如此，而且他还发现另一件事。"
            "尽管如此，他依然不愿放弃。"
            "毫无疑问，这件事显而易见非常复杂。"
            "总而言之，综上所述，这是一个两难局面。"
            "首先他必须冷静，其次他需要计划。"
            "值得一提的是，众所周知，此事早有定论。"
        ) * 3
        density = conjunction_density(heavy)
        assert density > 5.0

    def test_density_monotonic_in_conjunction_count(self):
        base = "他走进屋子看了一眼然后慢慢坐下来闭上了眼睛。" * 10
        heavy = base + "不仅如此，而且毫无疑问，尽管如此，总而言之，综上所述。" * 5
        assert conjunction_density(heavy) > conjunction_density(base)

    def test_returns_float(self):
        text = "他抬起了剑，风声如啸。" * 20 + "不仅如此，毫无疑问。"
        density = conjunction_density(text)
        assert isinstance(density, float)


# ---------------------------------------------------------------------------
# analyze_diversity integration with AD_CONJUNCTION_DENSE
# ---------------------------------------------------------------------------


class TestConjunctionDensityViolation:
    def test_clean_text_no_violation(self):
        cfg = AntiDetectionConfig(conjunction_density_max=2.5)
        text = (
            "剑光划过天际。\n\n"
            "林渊向前一步，碎石在脚下崩裂。他低声问：「你还要打？」"
            "萧尘没有答话，只是抬起了剑。风卷起衣袂。"
            "他听见自己的心跳声，一下，又一下。"
        ) * 4
        report = analyze_diversity(text, cfg)
        ids = {v.id for v in report.violations}
        assert "AD_CONJUNCTION_DENSE" not in ids
        assert report.conjunction_density <= 2.5

    def test_heavy_conjunction_triggers_violation(self):
        cfg = AntiDetectionConfig(conjunction_density_max=2.5)
        heavy = (
            "不仅如此，而且他还发现另一件事。"
            "尽管如此，他依然不愿放弃。"
            "毫无疑问，这件事显而易见非常复杂。"
            "总而言之，综上所述，这是一个两难局面。"
            "首先他必须冷静，其次他需要计划。"
            "值得一提的是，众所周知，此事早有定论。"
        ) * 3
        report = analyze_diversity(heavy, cfg)
        ids = {v.id for v in report.violations}
        assert "AD_CONJUNCTION_DENSE" in ids
        assert report.conjunction_density > 2.5

    def test_threshold_respected(self):
        # Raise threshold sky-high — even heavy text should not violate
        cfg = AntiDetectionConfig(conjunction_density_max=999.0)
        heavy = (
            "不仅如此，而且他还发现另一件事。"
            "尽管如此，他依然不愿放弃。"
            "毫无疑问，这件事显而易见非常复杂。"
            "总而言之，综上所述，这是一个两难局面。"
        ) * 5
        report = analyze_diversity(heavy, cfg)
        ids = {v.id for v in report.violations}
        assert "AD_CONJUNCTION_DENSE" not in ids

    def test_violation_severity_and_description(self):
        cfg = AntiDetectionConfig(conjunction_density_max=2.5)
        heavy = (
            "不仅如此，而且毫无疑问。尽管如此，总而言之，综上所述。"
            "首先，其次，最后。值得一提的是，众所周知。"
        ) * 5
        report = analyze_diversity(heavy, cfg)
        conj = [v for v in report.violations if v.id == "AD_CONJUNCTION_DENSE"]
        assert len(conj) == 1
        assert conj[0].severity == "medium"
        assert "连接词密度" in conj[0].description
        assert conj[0].fix_suggestion

    def test_conjunction_density_recorded_in_report(self):
        cfg = AntiDetectionConfig(conjunction_density_max=2.5)
        text = "他走进屋子看了看然后坐下来休息一会儿。" * 20
        report = analyze_diversity(text, cfg)
        assert isinstance(report.conjunction_density, float)
        assert report.conjunction_density >= 0.0


class TestConjunctionDenseFixTemplate:
    def test_fix_template_registered(self):
        assert "AD_CONJUNCTION_DENSE" in VIOLATION_FIX_TEMPLATES
        tmpl = VIOLATION_FIX_TEMPLATES["AD_CONJUNCTION_DENSE"]
        assert "连接词" in tmpl

    def test_default_config_threshold(self):
        cfg = AntiDetectionConfig()
        assert cfg.conjunction_density_max == pytest.approx(2.5)
