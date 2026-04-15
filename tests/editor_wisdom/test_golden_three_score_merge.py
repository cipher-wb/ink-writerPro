"""Tests for US-008: retrieve_golden_three_rules merges by score, not category order."""

from __future__ import annotations

from ink_writer.editor_wisdom.golden_three import (
    GOLDEN_THREE_CATEGORIES,
    retrieve_golden_three_rules,
)
from ink_writer.editor_wisdom.retriever import Rule


def _make_rule(id: str, category: str, score: float) -> Rule:
    return Rule(
        id=id,
        category=category,
        rule=f"rule-{id}",
        why=f"why-{id}",
        severity="hard",
        applies_to=["golden_three"],
        source_files=[],
        score=score,
    )


class ScoredRetriever:
    """Returns pre-scored rules filtered by category."""

    def __init__(self, rules: list[Rule]):
        self._rules = rules

    def retrieve(self, query: str, k: int = 5, category: str | None = None) -> list[Rule]:
        pool = self._rules
        if category is not None:
            pool = [r for r in pool if r.category == category]
        return sorted(pool, key=lambda r: -r.score)[:k]


class TestScoreMerge:
    def test_merged_order_by_score_not_category(self):
        rules = [
            _make_rule("R1", "character", 0.9),
            _make_rule("R2", "golden_finger", 0.2),
            _make_rule("R3", "hook", 0.5),
            _make_rule("R4", "opening", 0.7),
        ]
        retriever = ScoredRetriever(rules)
        result = retrieve_golden_three_rules("test", retriever, k=10)

        scores = [r.score for r in result]
        assert scores == sorted(scores, reverse=True)
        assert scores == [0.9, 0.7, 0.5, 0.2]

    def test_truncated_to_k(self):
        rules = [
            _make_rule("R1", "character", 0.9),
            _make_rule("R2", "golden_finger", 0.8),
            _make_rule("R3", "hook", 0.7),
            _make_rule("R4", "opening", 0.6),
            _make_rule("R5", "character", 0.5),
            _make_rule("R6", "hook", 0.4),
        ]
        retriever = ScoredRetriever(rules)
        result = retrieve_golden_three_rules("test", retriever, k=3)

        assert len(result) == 3
        assert [r.score for r in result] == [0.9, 0.8, 0.7]

    def test_mixed_scores_across_categories(self):
        rules = [
            _make_rule("R1", "opening", 0.1),
            _make_rule("R2", "opening", 0.95),
            _make_rule("R3", "hook", 0.5),
            _make_rule("R4", "character", 0.8),
            _make_rule("R5", "golden_finger", 0.3),
        ]
        retriever = ScoredRetriever(rules)
        result = retrieve_golden_three_rules("test", retriever, k=5)

        assert result[0].id == "R2"
        assert result[0].score == 0.95
        assert result[1].id == "R4"
        assert result[1].score == 0.8

    def test_empty_retriever_returns_empty(self):
        retriever = ScoredRetriever([])
        result = retrieve_golden_three_rules("test", retriever, k=5)
        assert result == []

    def test_k_larger_than_results(self):
        rules = [
            _make_rule("R1", "opening", 0.9),
            _make_rule("R2", "hook", 0.7),
        ]
        retriever = ScoredRetriever(rules)
        result = retrieve_golden_three_rules("test", retriever, k=20)
        assert len(result) == 2
        assert result[0].score >= result[1].score
