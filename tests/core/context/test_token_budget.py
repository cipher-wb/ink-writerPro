#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""US-006 tests: token budget re-ranking + recent_full_texts protection.

Covers acceptance criteria from prd-chapter-context-injection:
- recent_full_texts is promoted to a top-level protected section (budget=None, never trimmed).
- Soft cap breach warns and trims minor sections only.
- Hard cap breach degrades in order: global → scene → recent_summaries → recent_full_texts.
- recent_full_texts stays intact as long as other degradation targets exist.
- Per-build token_breakdown + soft/hard caps exposed in meta; logs include estimates.
- soft_cap / hard_cap / trim orders are configurable via DataModulesConfig.
"""
from __future__ import annotations

import logging

import pytest

from ink_writer.core.infra.config import DataModulesConfig
from ink_writer.core.context.context_manager import ContextManager


@pytest.fixture
def manager(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return ContextManager(cfg)


def _make_full_texts(word_count_per_chapter: int = 2500):
    """Build a synthetic recent_full_texts payload matching _load_recent_full_texts schema."""
    return [
        {
            "chapter": ch,
            "text": "正" * word_count_per_chapter,
            "word_count": word_count_per_chapter,
            "missing": False,
        }
        for ch in (1, 2, 3)
    ]


def _pack_with_full_texts(chapter: int = 4, word_count: int = 2500):
    return {
        "meta": {"chapter": chapter},
        "core": {
            "chapter_outline": "本章大纲：A 去找 B",
            "protagonist_snapshot": {"name": "萧炎"},
            "recent_full_texts": _make_full_texts(word_count),
            "recent_summaries": [
                {"chapter": ch, "summary": f"ch{ch} 摘要"}
                for ch in range(1, 8)
            ],
            "recent_meta": [],
            "volume_summaries": [],
            "key_chapter_summaries": [],
        },
        "scene": {"location_context": {}, "appearing_characters": []},
        "global": {"worldview_skeleton": "九州世界"},
    }


class TestRecentFullTextsProtected:
    def test_full_texts_rendered_as_top_level_section_with_no_budget(self, manager):
        pack = _pack_with_full_texts(chapter=4, word_count=2500)
        assembled = manager.assemble_context(pack, max_chars=8000)

        sections = assembled["sections"]
        assert "recent_full_texts" in sections
        full_sec = sections["recent_full_texts"]
        # Protected sections report budget=None and protected=True
        assert full_sec["budget"] is None
        assert full_sec["protected"] is True
        # content preserves the list & raw text survives without truncation marker
        assert isinstance(full_sec["content"], list)
        assert len(full_sec["content"]) == 3
        assert "…[TRUNCATED]" not in full_sec["text"]
        assert "…[BUDGET_TRIMMED]" not in full_sec["text"]

    def test_core_section_no_longer_contains_full_texts(self, manager):
        """After US-006, the assembled `core` section is rendered WITHOUT recent_full_texts
        to avoid double-counting and to protect full texts from core's weight budget."""
        pack = _pack_with_full_texts(chapter=4, word_count=2500)
        assembled = manager.assemble_context(pack, max_chars=8000)

        core_sec = assembled["sections"]["core"]
        # Full texts lifted out → core.content no longer exposes the key
        assert "recent_full_texts" not in core_sec["content"]
        # Raw pack is not mutated
        assert "recent_full_texts" in pack["core"]

    def test_full_texts_listed_in_protected_sections_meta(self, manager):
        pack = _pack_with_full_texts()
        assembled = manager.assemble_context(pack, max_chars=8000)
        assert "recent_full_texts" in assembled["meta"]["protected_sections"]


class TestTokenBreakdown:
    def test_token_breakdown_exposes_per_section_estimates(self, manager):
        pack = _pack_with_full_texts(chapter=4, word_count=2500)
        assembled = manager.assemble_context(pack, max_chars=8000)

        breakdown = assembled["meta"]["token_breakdown"]
        # Every assembled section should get an estimate
        assert set(breakdown.keys()) == set(assembled["sections"].keys())
        for tokens in breakdown.values():
            assert isinstance(tokens, int)
            assert tokens >= 0
        # recent_full_texts with 3×2500 chars ≈ 7500 / 1.5 = 5000 tokens (lower bound)
        assert breakdown["recent_full_texts"] >= 4000

    def test_meta_exposes_soft_and_hard_caps(self, manager):
        pack = _pack_with_full_texts()
        assembled = manager.assemble_context(pack, max_chars=8000)
        meta = assembled["meta"]
        assert meta["soft_token_limit"] == manager.config.context_soft_token_limit
        assert meta["hard_token_limit"] == manager.config.context_hard_token_limit
        assert isinstance(meta["estimated_tokens"], int)

    def test_three_chapter_full_texts_fit_within_default_soft_cap(self, manager):
        """3×2500 字 ~ 12k tokens 应当远低于 soft cap (默认 60k) → 不触发任何降级。"""
        pack = _pack_with_full_texts(chapter=4, word_count=2500)
        assembled = manager.assemble_context(pack, max_chars=8000)
        assert assembled["meta"]["trim_stages_applied"] == []
        assert assembled["meta"].get("budget_trimmed") is False
        assert "budget_trim_warning" not in assembled["sections"]


class TestSoftCapDegradation:
    def test_soft_cap_breach_warns_and_trims_minor_sections(self, manager, caplog):
        pack = _pack_with_full_texts(chapter=4, word_count=2500)
        # Pad minor sections so they become meaningful chars
        pack["alerts"] = {"disambiguation_warnings": ["abc" * 400]}
        pack["preferences"] = {"k": "p" * 1500}
        pack["memory"] = {"m": "m" * 1500}
        pack["story_skeleton"] = "s" * 1500
        pack["global"]["extra"] = "g" * 1500

        manager.config.context_soft_token_limit = 500
        manager.config.context_hard_token_limit = 200000  # never breach hard here

        with caplog.at_level(logging.WARNING, logger="ink_writer.core.context.context_manager"):
            assembled = manager.assemble_context(pack, max_chars=8000)

        applied = assembled["meta"]["trim_stages_applied"]
        # At least one soft-stage trim should be applied
        assert any(stage.startswith("soft:") for stage in applied), applied
        # recent_full_texts MUST remain untouched
        full_sec = assembled["sections"]["recent_full_texts"]
        assert full_sec.get("budget_trimmed") is not True
        assert "…[BUDGET_TRIMMED]" not in full_sec["text"]
        # Warning log emitted
        assert any("soft token limit" in rec.message for rec in caplog.records)

    def test_soft_cap_does_not_touch_protected_even_if_listed(self, manager):
        pack = _pack_with_full_texts(chapter=4, word_count=2500)
        manager.config.context_soft_token_limit = 100
        manager.config.context_hard_token_limit = 200000
        # Misconfigure: force recent_full_texts into soft order — should still be skipped
        manager.config.context_soft_cap_trim_order = (
            "recent_full_texts",
            "alerts",
            "preferences",
        )

        assembled = manager.assemble_context(pack, max_chars=8000)
        full_sec = assembled["sections"]["recent_full_texts"]
        assert full_sec.get("budget_trimmed") is not True
        # No stage entry like "soft:recent_full_texts" should appear
        assert not any(
            stage == "soft:recent_full_texts"
            for stage in assembled["meta"]["trim_stages_applied"]
        )


class TestHardCapDegradation:
    def test_hard_cap_breach_degrades_in_configured_order(self, manager, caplog):
        pack = _pack_with_full_texts(chapter=4, word_count=2500)
        pack["scene"] = {"data": "x" * 3000}
        pack["global"] = {"data": "y" * 3000}

        # Force hard-cap breach
        manager.config.context_soft_token_limit = 50
        manager.config.context_hard_token_limit = 100

        with caplog.at_level(logging.WARNING, logger="ink_writer.core.context.context_manager"):
            assembled = manager.assemble_context(pack, max_chars=8000)

        applied = assembled["meta"]["trim_stages_applied"]
        # Hard stages should include global / scene before recent_full_texts
        hard_stages = [s for s in applied if s.startswith("hard:")]
        assert hard_stages, applied
        # The first hard stage must be "global" or "scene" (never recent_full_texts first)
        assert hard_stages[0] in ("hard:global", "hard:scene")
        # Warning log emitted for hard breach
        assert any("hard token limit" in rec.message for rec in caplog.records)

    def test_recent_full_texts_protected_across_both_caps(self, manager):
        """Even if both caps are violated and degradation runs to exhaustion,
        recent_full_texts must never be truncated because it is `protected`."""
        pack = _pack_with_full_texts(chapter=4, word_count=2500)

        manager.config.context_soft_token_limit = 1
        manager.config.context_hard_token_limit = 1

        assembled = manager.assemble_context(pack, max_chars=8000)
        full_sec = assembled["sections"]["recent_full_texts"]
        assert full_sec["budget"] is None
        assert full_sec.get("budget_trimmed") is not True
        assert "…[BUDGET_TRIMMED]" not in full_sec["text"]
        # The content must still be the full list of 3 chapters, each with full text
        assert len(full_sec["content"]) == 3
        assert all(
            "…[BUDGET_TRIMMED]" not in entry["text"]
            for entry in full_sec["content"]
        )

    def test_hard_cap_recent_summaries_stage_shrinks_core(self, manager):
        pack = _pack_with_full_texts(chapter=4, word_count=200)
        # Inflate recent_summaries so that removing them makes a meaningful difference
        pack["core"]["recent_summaries"] = [
            {"chapter": ch, "summary": "摘要" * 400}
            for ch in range(1, 8)
        ]

        manager.config.context_soft_token_limit = 50
        manager.config.context_hard_token_limit = 100
        # Run only the recent_summaries stage of hard tier
        manager.config.context_soft_cap_trim_order = ()
        manager.config.context_hard_cap_trim_order = ("recent_summaries",)

        assembled = manager.assemble_context(pack, max_chars=8000)
        applied = assembled["meta"]["trim_stages_applied"]
        assert "hard:recent_summaries" in applied
        core_sec = assembled["sections"]["core"]
        # Shrunk core text must no longer include the padded summary bodies
        assert "摘要" * 400 not in core_sec["text"]


class TestConfigurableCaps:
    def test_soft_and_hard_limits_respect_config_overrides(self, manager):
        pack = _pack_with_full_texts(chapter=4, word_count=2500)
        manager.config.context_soft_token_limit = 1234
        manager.config.context_hard_token_limit = 9999

        assembled = manager.assemble_context(pack, max_chars=8000)
        assert assembled["meta"]["soft_token_limit"] == 1234
        assert assembled["meta"]["hard_token_limit"] == 9999

    def test_misconfigured_soft_greater_than_hard_uses_hard(self, manager):
        """When soft > hard (misconfig), effective soft cap degrades to hard cap
        so that protection still triggers."""
        pack = _pack_with_full_texts(chapter=4, word_count=2500)
        manager.config.context_soft_token_limit = 100000
        manager.config.context_hard_token_limit = 100

        assembled = manager.assemble_context(pack, max_chars=8000)
        # With soft=100k but hard=100, any real payload breaches hard; trim must occur
        applied = assembled["meta"]["trim_stages_applied"]
        assert applied  # some trim applied
        # recent_full_texts stays protected
        full_sec = assembled["sections"]["recent_full_texts"]
        assert full_sec.get("budget_trimmed") is not True
