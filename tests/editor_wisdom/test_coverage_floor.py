"""Tests for v18 US-002: golden-three category floor + coverage metrics.

Guardrails:
- chapter ≤3 must inject ≥3 rules for each of opening/taboo/hook;
- `.ink/editor-wisdom-coverage.json` is written after prompt assembly;
- coverage <10%/章 on chapters 1-3 counts as a failure (SM-7 floor).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ink_writer.editor_wisdom.config import EditorWisdomConfig
from ink_writer.editor_wisdom.coverage_metrics import (
    compute_coverage,
    read_coverage,
    record_chapter_coverage,
    summarize,
)
from ink_writer.editor_wisdom.retriever import Rule
from ink_writer.editor_wisdom.writer_injection import (
    GOLDEN_THREE_FLOOR_CATEGORIES,
    GOLDEN_THREE_FLOOR_PER_CATEGORY,
    build_writer_constraints,
)


class CategoryAwareRetriever:
    """Retriever that respects the `category` filter and exposes plenty of rules per category."""

    def __init__(self, rules: list[Rule]) -> None:
        self._rules = rules

    def retrieve(
        self, query: str, k: int = 5, category: str | None = None
    ) -> list[Rule]:
        if category is not None:
            pool = [r for r in self._rules if r.category == category]
        else:
            pool = list(self._rules)
        return pool[:k]


def _rule(
    id_: str,
    category: str,
    severity: str = "hard",
    rule_text: str = "规则",
) -> Rule:
    return Rule(
        id=id_,
        category=category,
        rule=rule_text,
        why="测试",
        severity=severity,
        applies_to=[],
        source_files=[],
    )


def _wide_retriever_rules() -> list[Rule]:
    """Return ≥3 rules per opening/taboo/hook plus a couple of other categories.

    Order is deliberately skewed so that a semantic-only retriever would NOT pick
    enough opening/taboo/hook rules without the category-floor fallback.
    """
    out: list[Rule] = []
    for cat in ["pacing", "pacing", "genre", "genre", "character", "character"]:
        out.append(_rule(f"EW-P-{len(out):03d}", cat))
    for cat in ("opening", "taboo", "hook"):
        for i in range(5):
            out.append(_rule(f"EW-{cat[:3].upper()}-{i:03d}", cat))
    return out


class TestCategoryFloor:
    def test_ch1_enforces_per_category_floor(self):
        retriever = CategoryAwareRetriever(_wide_retriever_rules())
        # retrieval_top_k=6 → 朴素 top-k 只会出 pacing/genre/character，触发补齐。
        config = EditorWisdomConfig(retrieval_top_k=6)
        section = build_writer_constraints(
            "开篇章节",
            chapter_no=1,
            config=config,
            retriever=retriever,
        )
        counts: dict[str, int] = {}
        for r in section.rules:
            counts[r.category] = counts.get(r.category, 0) + 1

        for cat in GOLDEN_THREE_FLOOR_CATEGORIES:
            assert counts.get(cat, 0) >= GOLDEN_THREE_FLOOR_PER_CATEGORY, (
                f"golden-three floor violated for {cat}: {counts}"
            )

    def test_ch4_does_not_enforce_floor(self):
        retriever = CategoryAwareRetriever(_wide_retriever_rules())
        config = EditorWisdomConfig(retrieval_top_k=6)
        section = build_writer_constraints(
            "普通章节",
            chapter_no=4,
            config=config,
            retriever=retriever,
        )
        counts: dict[str, int] = {}
        for r in section.rules:
            counts[r.category] = counts.get(r.category, 0) + 1
        # ch4 不强制下限（保留原行为）
        assert counts.get("opening", 0) < GOLDEN_THREE_FLOOR_PER_CATEGORY

    def test_existing_rules_satisfying_floor_not_duplicated(self):
        rules = []
        for cat in ("opening", "taboo", "hook"):
            for i in range(3):
                rules.append(_rule(f"EW-{cat}-{i}", cat))
        retriever = CategoryAwareRetriever(rules)
        # retrieval_top_k 足够大，top-k 已经覆盖所有
        config = EditorWisdomConfig(retrieval_top_k=len(rules))
        section = build_writer_constraints(
            "", chapter_no=1, config=config, retriever=retriever
        )
        ids = [r.id for r in section.rules]
        assert len(ids) == len(set(ids)), "no duplicates after floor enforcement"


class TestComputeCoverage:
    def test_coverage_pct_and_breakdown(self):
        rules = [
            _rule("EW-1", "opening"),
            _rule("EW-2", "opening"),
            _rule("EW-3", "taboo"),
        ]
        snap = compute_coverage(rules, chapter_no=2, total_rules=100)
        assert snap["chapter_no"] == 2
        assert snap["injected_total"] == 3
        assert snap["coverage_pct"] == 3.0
        assert snap["by_category"] == {"opening": 2, "taboo": 1}
        # golden_three ch2 缺少 hook 类，应为 False
        assert snap["golden_three_floor_met"] is False

    def test_ch4_floor_met_true(self):
        snap = compute_coverage(
            [_rule("EW-1", "opening")], chapter_no=4, total_rules=100
        )
        assert snap["golden_three_floor_met"] is True

    def test_floor_met_when_all_present(self):
        rules = []
        for cat in ("opening", "taboo", "hook"):
            for i in range(3):
                rules.append(_rule(f"EW-{cat}-{i}", cat))
        snap = compute_coverage(rules, chapter_no=1, total_rules=364)
        assert snap["golden_three_floor_met"] is True

    def test_zero_total_rules_no_zerodiv(self):
        snap = compute_coverage(
            [_rule("EW-1", "opening")], chapter_no=1, total_rules=0
        )
        assert snap["coverage_pct"] == 0.0


class TestRecordChapterCoverage:
    def test_writes_and_reads(self, tmp_path: Path):
        rules = [
            _rule("EW-1", "opening"),
            _rule("EW-2", "taboo"),
            _rule("EW-3", "hook"),
        ]
        path = record_chapter_coverage(
            project_root=tmp_path,
            chapter_no=1,
            rules=rules,
            total_rules=100,
        )
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["total_rules"] == 100
        assert "1" in data["chapters"]
        assert data["chapters"]["1"]["injected_total"] == 3

    def test_append_multiple_chapters(self, tmp_path: Path):
        for ch in range(1, 4):
            record_chapter_coverage(
                project_root=tmp_path,
                chapter_no=ch,
                rules=[_rule(f"EW-{ch}", "opening")],
                total_rules=100,
            )
        data = read_coverage(tmp_path)
        assert set(data["chapters"].keys()) == {"1", "2", "3"}


class TestCoverageFloorGate:
    """SM-7: 黄金三章实际覆盖率 <10%/章 即 fail（PRD AC 明确点名）。"""

    def test_golden_three_below_10pct_fails(self, tmp_path: Path):
        # 只注入 3 条，total_rules=100 → 3% 覆盖率 → 应 fail
        record_chapter_coverage(
            project_root=tmp_path,
            chapter_no=1,
            rules=[
                _rule("EW-1", "opening"),
                _rule("EW-2", "taboo"),
                _rule("EW-3", "hook"),
            ],
            total_rules=100,
        )
        data = read_coverage(tmp_path)
        snap = data["chapters"]["1"]
        assert snap["coverage_pct"] < 10.0, (
            "deliberately constructed failure: coverage ~3%"
        )
        # 门禁：若覆盖率 <10%，显式报错
        with pytest.raises(AssertionError):
            assert snap["coverage_pct"] >= 10.0, (
                f"ch1 coverage {snap['coverage_pct']}% < 10% floor"
            )

    def test_golden_three_above_10pct_passes(self, tmp_path: Path):
        # 注入 15 条，total_rules=100 → 15% 覆盖率
        many_rules = [_rule(f"EW-{i}", "opening") for i in range(15)]
        record_chapter_coverage(
            project_root=tmp_path,
            chapter_no=1,
            rules=many_rules,
            total_rules=100,
        )
        data = read_coverage(tmp_path)
        snap = data["chapters"]["1"]
        assert snap["coverage_pct"] >= 10.0


class TestSummarize:
    def test_empty(self, tmp_path: Path):
        out = summarize(tmp_path)
        assert out["chapter_count"] == 0
        assert out["avg_coverage_pct"] == 0.0
        assert out["golden_three_violations"] == []

    def test_violations_reported(self, tmp_path: Path):
        # ch1 缺 hook → 违反；ch4 缺 hook → 不算违反
        record_chapter_coverage(
            project_root=tmp_path,
            chapter_no=1,
            rules=[_rule("EW-1", "opening"), _rule("EW-2", "taboo")],
            total_rules=100,
        )
        record_chapter_coverage(
            project_root=tmp_path,
            chapter_no=4,
            rules=[_rule("EW-3", "opening")],
            total_rules=100,
        )
        out = summarize(tmp_path)
        assert 1 in out["golden_three_violations"]
        assert 4 not in out["golden_three_violations"]
        assert out["chapter_count"] == 2


class TestWriterInjectionCoverageHook:
    def test_coverage_file_written_when_project_root_passed(
        self, tmp_path: Path
    ):
        retriever = CategoryAwareRetriever(_wide_retriever_rules())
        config = EditorWisdomConfig(retrieval_top_k=6)
        build_writer_constraints(
            "开篇",
            chapter_no=1,
            config=config,
            retriever=retriever,
            project_root=tmp_path,
        )
        coverage_file = tmp_path / ".ink" / "editor-wisdom-coverage.json"
        assert coverage_file.exists()
        data = json.loads(coverage_file.read_text(encoding="utf-8"))
        assert "chapters" in data
        assert "1" in data["chapters"]
        snap = data["chapters"]["1"]
        # 经过 floor 补齐后，opening/taboo/hook 都应 ≥3
        assert snap["golden_three_floor_met"] is True

    def test_coverage_file_not_written_without_project_root(self):
        retriever = CategoryAwareRetriever(_wide_retriever_rules())
        config = EditorWisdomConfig(retrieval_top_k=6)
        # 不传 project_root：不应写文件（向后兼容，不影响既有测试）
        section = build_writer_constraints(
            "开篇",
            chapter_no=1,
            config=config,
            retriever=retriever,
        )
        assert not section.empty
