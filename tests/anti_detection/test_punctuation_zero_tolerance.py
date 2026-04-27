#!/usr/bin/env python3
"""US-001 (v26 prose anti-AI overhaul): Punctuation zero-tolerance rules.

Five new ZT rules added to config/anti-detection.yaml zero_tolerance:
  - ZT_EM_DASH         (regex)   — 双破折号 —— (U+2014 ×2 及变体)
  - ZT_AI_QUOTES       (regex)   — 智能引号 / 法式引号
  - ZT_HYPHEN_AS_DASH  (regex)   — 中文上下文 ASCII '-' 当破折号
  - ZT_DENSE_DUNHAO    (density) — 顿号 > 3 / 千字
  - ZT_ELLIPSIS_OVERUSE(density) — …… > 8 / 千字

PRD AC requires 5 fixture chapters (4 violation + 1 compliant) all hitting
expected branches. Density-class rules are exercised both via the headline
fixture and via isolated config builders so each rule's branch is covered.

Pure-Python — no LLM call.
"""

from __future__ import annotations

import pytest
from ink_writer.anti_detection.anti_detection_gate import (
    _rule_violated,
    check_zero_tolerance,
)
from ink_writer.anti_detection.config import (
    AntiDetectionConfig,
    ZeroToleranceRule,
    load_config,
)

# ---------------------------------------------------------------------------
# Real config — guards YAML/test drift.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cfg() -> AntiDetectionConfig:
    return load_config()


# ---------------------------------------------------------------------------
# Fixture chapters (4 violation + 1 compliant).
# ---------------------------------------------------------------------------


@pytest.fixture
def chapter_em_dash_violation() -> str:
    """4 paragraphs of plausible chapter prose containing one ——."""
    return (
        "林渊握紧剑柄，雪片落在他的肩上。\n\n"
        "他抬眼看了对方一眼——然后笑了一下。\n\n"
        "「你来了。」\n\n"
        "山门外的钟声从风里飘过来，一声又一声。"
    )


@pytest.fixture
def chapter_ai_quotes_violation() -> str:
    """Smart curly quotes (U+201C/U+201D) instead of 「」 or "" 直引。"""
    return (
        "林渊推开柴扉，雪光晃眼。\n\n"
        "他低声道：“你怎么也来了。”\n\n"
        "对面的人没有回答。\n\n"
        "云层很低，山脚的灯火远得像一颗星。"
    )


@pytest.fixture
def chapter_hyphen_violation() -> str:
    """ASCII '-' wedged between Chinese characters as a fake dash."""
    return (
        "林渊缓缓抽剑出鞘，剑光一闪。\n\n"
        "他笑了-然后向前一步。\n\n"
        "雪片碎裂在他的肩上。\n\n"
        "「这一剑，你接得住吗？」"
    )


@pytest.fixture
def chapter_density_violation() -> str:
    """Both 顿号 + …… overdensity in one short chapter.

    Length is intentionally short so density blows past both thresholds:
    顿号 count ≥ 3 / kchars and ……  count ≥ 8 / kchars.
    """
    return (
        "他打开包袱，里面塞着剑、铃、镜、符、香、绳、笔、纸、墨、印、令、册。\n\n"
        "「这……这……这……怎么办……还有……我不知道……」\n\n"
        "她静默良久……风吹雪……她终于……开口……"
    )


@pytest.fixture
def chapter_compliant() -> str:
    """Clean prose — no AI punctuation fingerprints."""
    return (
        "林渊握紧剑柄，雪片落在他的肩上。\n\n"
        "他抬眼看了对方一眼，笑了一下。\n\n"
        "「你来了。」\n\n"
        "山门外的钟声从风里飘过来，一声又一声。\n\n"
        "对面的人没有动。"
    )


# ---------------------------------------------------------------------------
# Rule inventory — keep YAML and tests in lockstep.
# ---------------------------------------------------------------------------


class TestPunctuationRulesLoaded:
    EXPECTED_PUNCT_RULES = {
        "ZT_EM_DASH",
        "ZT_AI_QUOTES",
        "ZT_HYPHEN_AS_DASH",
        "ZT_DENSE_DUNHAO",
        "ZT_ELLIPSIS_OVERUSE",
    }

    def test_all_five_punct_rules_loaded(self, cfg: AntiDetectionConfig):
        ids = {r.id for r in cfg.zero_tolerance}
        missing = self.EXPECTED_PUNCT_RULES - ids
        assert not missing, f"YAML missing punctuation ZT rules: {missing}"

    def test_density_rules_have_threshold_and_kind(self, cfg: AntiDetectionConfig):
        density_rules = {
            r.id: r for r in cfg.zero_tolerance if r.kind == "density"
        }
        assert "ZT_DENSE_DUNHAO" in density_rules
        assert "ZT_ELLIPSIS_OVERUSE" in density_rules
        assert density_rules["ZT_DENSE_DUNHAO"].density_threshold == 3.0
        assert density_rules["ZT_ELLIPSIS_OVERUSE"].density_threshold == 8.0

    def test_each_punct_rule_has_whitelist_field(self, cfg: AntiDetectionConfig):
        for rule_id in self.EXPECTED_PUNCT_RULES:
            rule = next(r for r in cfg.zero_tolerance if r.id == rule_id)
            # whitelist_patterns is required on every new punct rule (currently empty)
            assert isinstance(rule.whitelist_patterns, list)


# ---------------------------------------------------------------------------
# Violation fixtures hit expected branches.
# ---------------------------------------------------------------------------


class TestEmDashViolation:
    def test_em_dash_caught(self, cfg, chapter_em_dash_violation):
        assert (
            check_zero_tolerance(chapter_em_dash_violation, cfg) == "ZT_EM_DASH"
        )

    def test_em_dash_variant_u2015(self, cfg):
        text = "他点头――然后离开。"
        assert check_zero_tolerance(text, cfg) == "ZT_EM_DASH"

    def test_single_em_dash_does_not_trigger(self, cfg):
        # 单个 — 不是 AI 指纹（虽然不推荐，但不阻断；本规则只针对 ——）
        text = "他抬手—雪片落下。"
        # 单 — 不命中 ZT_EM_DASH
        assert check_zero_tolerance(text, cfg) != "ZT_EM_DASH"


class TestAIQuotesViolation:
    def test_smart_quotes_caught(self, cfg, chapter_ai_quotes_violation):
        assert (
            check_zero_tolerance(chapter_ai_quotes_violation, cfg)
            == "ZT_AI_QUOTES"
        )

    def test_french_guillemets_caught(self, cfg):
        text = "他低声道：«你怎么也来了。»"
        assert check_zero_tolerance(text, cfg) == "ZT_AI_QUOTES"

    def test_chinese_brackets_pass(self, cfg):
        # 「」是爆款标准引号，不应误伤
        text = "他低声道：「你怎么也来了。」"
        assert check_zero_tolerance(text, cfg) is None


class TestHyphenAsDashViolation:
    def test_hyphen_caught(self, cfg, chapter_hyphen_violation):
        assert (
            check_zero_tolerance(chapter_hyphen_violation, cfg)
            == "ZT_HYPHEN_AS_DASH"
        )

    def test_hyphen_outside_chinese_context_passes(self, cfg):
        # ASCII context — code-style or western punctuation, not the AI fingerprint
        text = "He said hello-world to her. 然后她笑了。"
        # 'hello-world' is between ASCII letters → 不命中 ZT_HYPHEN_AS_DASH
        assert check_zero_tolerance(text, cfg) != "ZT_HYPHEN_AS_DASH"


class TestDensityViolations:
    """Density rules are tested against the combined fixture; isolation per rule
    is achieved by running with a config containing only that rule."""

    def _isolated_cfg(self, rule_id: str, cfg: AntiDetectionConfig) -> AntiDetectionConfig:
        rule = next(r for r in cfg.zero_tolerance if r.id == rule_id)
        return AntiDetectionConfig(zero_tolerance=[rule])

    def test_dunhao_overdensity_caught(
        self, cfg, chapter_density_violation
    ):
        iso = self._isolated_cfg("ZT_DENSE_DUNHAO", cfg)
        assert (
            check_zero_tolerance(chapter_density_violation, iso)
            == "ZT_DENSE_DUNHAO"
        )

    def test_ellipsis_overuse_caught(
        self, cfg, chapter_density_violation
    ):
        iso = self._isolated_cfg("ZT_ELLIPSIS_OVERUSE", cfg)
        assert (
            check_zero_tolerance(chapter_density_violation, iso)
            == "ZT_ELLIPSIS_OVERUSE"
        )

    def test_below_threshold_dunhao_passes(self, cfg):
        # 5 顿号 in ~5000 chars → 1 / 千字 << 3 → 不阻断
        rule = next(r for r in cfg.zero_tolerance if r.id == "ZT_DENSE_DUNHAO")
        # 构造 1000 字内有 1 个顿号
        prose = "他握紧剑柄。" * 100 + "山、水。"
        iso = AntiDetectionConfig(zero_tolerance=[rule])
        assert check_zero_tolerance(prose, iso) is None

    def test_density_handles_empty_text(self, cfg):
        rule = next(r for r in cfg.zero_tolerance if r.id == "ZT_DENSE_DUNHAO")
        iso = AntiDetectionConfig(zero_tolerance=[rule])
        assert check_zero_tolerance("", iso) is None


# ---------------------------------------------------------------------------
# Compliant fixture passes cleanly.
# ---------------------------------------------------------------------------


class TestCompliantChapter:
    def test_compliant_returns_none(self, cfg, chapter_compliant):
        assert check_zero_tolerance(chapter_compliant, cfg) is None


# ---------------------------------------------------------------------------
# Lower-level _rule_violated helper unit tests.
# ---------------------------------------------------------------------------


class TestRuleViolatedHelper:
    def test_whitelist_field_inert_but_loaded(self, cfg):
        """whitelist_patterns is reserved for future US; currently always empty
        and ignored by _rule_violated. Lock the contract so the field stays
        present even if someone refactors the loader."""
        for r in cfg.zero_tolerance:
            assert isinstance(r.whitelist_patterns, list)

    def test_regex_rule_default_kind(self):
        rule = ZeroToleranceRule(
            id="ZT_TEST_REGEX",
            description="test",
            patterns=["foo"],
        )
        assert _rule_violated(rule, "this is foo bar", "this is foo bar")
        assert not _rule_violated(rule, "no match", "no match")

    def test_unknown_kind_falls_back_to_regex(self):
        # Defensive: unrecognized kind should not raise; treat as regex.
        rule = ZeroToleranceRule(
            id="ZT_TEST_UNKNOWN",
            description="test",
            patterns=["foo"],
            kind="bogus",
        )
        # bogus != density → falls into regex branch
        assert _rule_violated(rule, "foo", "foo")
