"""Tests for US-007: golden-three applies_to hardening + consumer-side unification."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# 05_extract_rules post-processing
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "editor-wisdom"))
from importlib import import_module

extract_mod = import_module("05_extract_rules")
_apply_golden_three_tag = extract_mod._apply_golden_three_tag
GOLDEN_THREE_CATEGORIES_SCRIPT = extract_mod.GOLDEN_THREE_CATEGORIES


class TestApplyGoldenThreeTag:
    def test_opening_gets_golden_three(self):
        rules = [{"category": "opening", "applies_to": ["all_chapters"]}]
        _apply_golden_three_tag(rules)
        assert "golden_three" in rules[0]["applies_to"]

    def test_hook_gets_golden_three(self):
        rules = [{"category": "hook", "applies_to": ["all_chapters"]}]
        _apply_golden_three_tag(rules)
        assert "golden_three" in rules[0]["applies_to"]

    def test_golden_finger_gets_golden_three(self):
        rules = [{"category": "golden_finger", "applies_to": ["opening_only"]}]
        _apply_golden_three_tag(rules)
        assert "golden_three" in rules[0]["applies_to"]
        assert "opening_only" in rules[0]["applies_to"]

    def test_character_gets_golden_three(self):
        rules = [{"category": "character", "applies_to": ["all_chapters"]}]
        _apply_golden_three_tag(rules)
        assert "golden_three" in rules[0]["applies_to"]

    def test_non_golden_category_unchanged(self):
        rules = [{"category": "pacing", "applies_to": ["all_chapters"]}]
        _apply_golden_three_tag(rules)
        assert "golden_three" not in rules[0]["applies_to"]

    def test_already_has_golden_three_no_dup(self):
        rules = [{"category": "opening", "applies_to": ["golden_three"]}]
        _apply_golden_three_tag(rules)
        assert rules[0]["applies_to"].count("golden_three") == 1

    def test_all_four_golden_categories_match(self):
        assert GOLDEN_THREE_CATEGORIES_SCRIPT == frozenset(
            {"opening", "hook", "golden_finger", "character"}
        )


# ---------------------------------------------------------------------------
# writer_injection golden-three branch uses category filtering
# ---------------------------------------------------------------------------

from ink_writer.editor_wisdom.retriever import Rule


@dataclass
class MockRetriever:
    rules: list[Rule] = field(default_factory=list)

    def retrieve(self, query: str, k: int = 5, category: str | None = None) -> list[Rule]:
        if category:
            return [r for r in self.rules if r.category == category][:k]
        return self.rules[:k]


class TestWriterInjectionGoldenThree:
    def _build_rules(self):
        return [
            Rule(id="EW-0001", category="opening", rule="rule1", why="", severity="hard",
                 applies_to=["all_chapters"], source_files=["a.md"], score=0.9),
            Rule(id="EW-0002", category="pacing", rule="rule2", why="", severity="hard",
                 applies_to=["all_chapters"], source_files=["b.md"], score=0.8),
            Rule(id="EW-0003", category="hook", rule="rule3", why="", severity="soft",
                 applies_to=["all_chapters"], source_files=["c.md"], score=0.7),
        ]

    def test_chapter_1_includes_golden_category_rules(self):
        from ink_writer.editor_wisdom.writer_injection import build_writer_constraints
        from ink_writer.editor_wisdom.config import EditorWisdomConfig

        rules = self._build_rules()
        retriever = MockRetriever(rules=rules)
        config = EditorWisdomConfig(enabled=True)
        config.inject_into.writer = True
        config.retrieval_top_k = 5

        section = build_writer_constraints(
            "test outline", chapter_no=1, config=config, retriever=retriever
        )
        rule_ids = {r.id for r in section.rules}
        assert "EW-0001" in rule_ids  # opening category -> golden three
        assert "EW-0003" in rule_ids  # hook category -> golden three

    def test_chapter_1_filters_by_category_not_applies_to(self):
        """Rules with golden-three category are included even without applies_to='golden_three'."""
        from ink_writer.editor_wisdom.writer_injection import build_writer_constraints
        from ink_writer.editor_wisdom.config import EditorWisdomConfig

        rule = Rule(
            id="EW-0010", category="character", rule="test", why="",
            severity="hard", applies_to=["all_chapters"], source_files=["x.md"], score=0.9
        )
        retriever = MockRetriever(rules=[rule])
        config = EditorWisdomConfig(enabled=True)
        config.inject_into.writer = True
        config.retrieval_top_k = 5

        section = build_writer_constraints(
            "test outline", chapter_no=2, config=config, retriever=retriever
        )
        rule_ids = {r.id for r in section.rules}
        assert "EW-0010" in rule_ids

    def test_chapter_4_does_not_add_golden_rules(self):
        from ink_writer.editor_wisdom.writer_injection import build_writer_constraints
        from ink_writer.editor_wisdom.config import EditorWisdomConfig

        rules = self._build_rules()
        retriever = MockRetriever(rules=rules)
        config = EditorWisdomConfig(enabled=True)
        config.inject_into.writer = True
        config.retrieval_top_k = 1

        section = build_writer_constraints(
            "test outline", chapter_no=4, config=config, retriever=retriever
        )
        assert len(section.rules) == 1
        assert section.rules[0].id == "EW-0001"
