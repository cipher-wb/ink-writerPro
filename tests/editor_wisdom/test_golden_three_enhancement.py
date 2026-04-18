"""Tests for US-013: golden-three editor-wisdom enhancement."""

from __future__ import annotations

import os
import tempfile

from ink_writer.editor_wisdom.config import EditorWisdomConfig
from ink_writer.editor_wisdom.golden_three import (
    GOLDEN_THREE_CATEGORIES,
    GoldenThreeCheckResult,
    GoldenThreeReport,
    check_golden_three_chapter,
    generate_report,
    retrieve_golden_three_rules,
)
from ink_writer.editor_wisdom.retriever import Rule
from ink_writer.editor_wisdom.review_gate import run_review_gate


def _make_rule(id: str, category: str, severity: str = "hard") -> Rule:
    return Rule(
        id=id,
        category=category,
        rule=f"测试规则{id}",
        why=f"原因{id}",
        severity=severity,
        applies_to=["golden_three"] if category in GOLDEN_THREE_CATEGORIES else [],
        source_files=[],
    )


class FakeRetriever:
    """Returns rules filtered by category from a preset pool."""

    def __init__(self, rules: list[Rule]):
        self._rules = rules

    def retrieve(self, query: str, k: int = 5, category: str | None = None) -> list[Rule]:
        if category is not None:
            return [r for r in self._rules if r.category == category][:k]
        return self._rules[:k]


class TestRetrieveGoldenThreeRules:
    def test_filters_to_golden_categories(self):
        rules = [
            _make_rule("EW-0001", "opening"),
            _make_rule("EW-0002", "hook"),
            _make_rule("EW-0003", "pacing"),
            _make_rule("EW-0004", "golden_finger"),
            _make_rule("EW-0005", "character"),
            _make_rule("EW-0006", "taboo"),
        ]
        retriever = FakeRetriever(rules)
        result = retrieve_golden_three_rules("测试查询", retriever)

        result_categories = {r.category for r in result}
        assert result_categories <= GOLDEN_THREE_CATEGORIES
        assert "pacing" not in result_categories
        assert "taboo" not in result_categories

    def test_deduplicates_by_id(self):
        rules = [
            _make_rule("EW-0001", "opening"),
            _make_rule("EW-0001", "opening"),
        ]
        retriever = FakeRetriever(rules)
        result = retrieve_golden_three_rules("测试", retriever)
        assert len(result) == 1

    def test_empty_retriever(self):
        retriever = FakeRetriever([])
        result = retrieve_golden_three_rules("测试", retriever)
        assert result == []

    def test_returns_all_four_categories(self):
        rules = [
            _make_rule("EW-0001", "opening"),
            _make_rule("EW-0002", "hook"),
            _make_rule("EW-0003", "golden_finger"),
            _make_rule("EW-0004", "character"),
        ]
        retriever = FakeRetriever(rules)
        result = retrieve_golden_three_rules("测试", retriever)
        assert len(result) == 4
        result_categories = {r.category for r in result}
        assert result_categories == GOLDEN_THREE_CATEGORIES


class TestCheckGoldenThreeChapter:
    def test_chapter_1_uses_golden_threshold(self):
        config = EditorWisdomConfig(
            hard_gate_threshold=0.75,
            golden_three_threshold=0.85,
        )
        checker_result = {"score": 0.80, "violations": [], "summary": "中等"}
        result = check_golden_three_chapter("文本", 1, checker_result, config)

        assert result.threshold == 0.85
        assert not result.passed  # 0.80 < 0.85

    def test_chapter_3_uses_golden_threshold(self):
        config = EditorWisdomConfig(golden_three_threshold=0.85)
        checker_result = {"score": 0.90, "violations": [], "summary": "良好"}
        result = check_golden_three_chapter("文本", 3, checker_result, config)

        assert result.threshold == 0.85
        assert result.passed  # 0.90 >= 0.85

    def test_chapter_4_uses_hard_threshold(self):
        config = EditorWisdomConfig(
            hard_gate_threshold=0.75,
            golden_three_threshold=0.85,
        )
        checker_result = {"score": 0.80, "violations": [], "summary": "可以"}
        result = check_golden_three_chapter("文本", 4, checker_result, config)

        assert result.threshold == 0.75
        assert result.passed  # 0.80 >= 0.75

    def test_same_score_passes_normal_fails_golden(self):
        """Core AC: same text passes with is_golden_three=false but fails with is_golden_three=true."""
        config = EditorWisdomConfig(
            hard_gate_threshold=0.75,
            golden_three_threshold=0.85,
        )
        checker_result = {
            "score": 0.80,
            "violations": [
                {"rule_id": "EW-0001", "quote": "问题段落", "severity": "soft", "fix_suggestion": "修复"},
            ],
            "summary": "一般质量",
        }

        normal_result = check_golden_three_chapter("文本", 10, checker_result, config)
        assert normal_result.passed  # 0.80 >= 0.75

        golden_result = check_golden_three_chapter("文本", 1, checker_result, config)
        assert not golden_result.passed  # 0.80 < 0.85

    def test_violations_carried_through(self):
        violations = [
            {"rule_id": "EW-0001", "quote": "引用", "severity": "hard", "fix_suggestion": "修"},
        ]
        checker_result = {"score": 0.5, "violations": violations, "summary": "差"}
        result = check_golden_three_chapter("文本", 1, checker_result)
        assert len(result.violations) == 1
        assert result.violations[0]["rule_id"] == "EW-0001"


class TestGoldenThreeReport:
    def test_report_markdown_structure(self):
        results = [
            GoldenThreeCheckResult(chapter_no=1, score=0.90, threshold=0.85, passed=True, summary="好"),
            GoldenThreeCheckResult(chapter_no=2, score=0.70, threshold=0.85, passed=False,
                                    violations=[{"rule_id": "EW-0001", "quote": "问题", "severity": "hard", "fix_suggestion": "修"}],
                                    summary="差"),
            GoldenThreeCheckResult(chapter_no=3, score=0.88, threshold=0.85, passed=True, summary="良"),
        ]
        report = GoldenThreeReport(chapters=results)

        assert not report.all_passed
        md = report.to_markdown()
        assert "黄金三章编辑智慧审查报告" in md
        assert "PASS" in md
        assert "FAIL" in md
        assert "EW-0001" in md
        assert "第1章" in md
        assert "第2章" in md
        assert "第3章" in md

    def test_all_passed_report(self):
        results = [
            GoldenThreeCheckResult(chapter_no=1, score=0.90, threshold=0.85, passed=True),
            GoldenThreeCheckResult(chapter_no=2, score=0.95, threshold=0.85, passed=True),
        ]
        report = GoldenThreeReport(chapters=results)
        assert report.all_passed
        md = report.to_markdown()
        assert "全部通过" in md

    def test_empty_report(self):
        report = GoldenThreeReport()
        assert report.all_passed
        md = report.to_markdown()
        assert "黄金三章" in md


class TestGenerateReport:
    def test_creates_report_file(self):
        results = [
            GoldenThreeCheckResult(chapter_no=1, score=0.90, threshold=0.85, passed=True, summary="好"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_report(results, tmpdir)
            assert os.path.exists(path)
            assert path.endswith("golden-three-editor-wisdom.md")
            with open(path, encoding="utf-8") as f:
                content = f.read()
            assert "第1章" in content
            assert "0.90" in content

    def test_creates_reports_directory(self):
        results = [
            GoldenThreeCheckResult(chapter_no=1, score=0.85, threshold=0.85, passed=True),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_report(results, tmpdir)
            assert os.path.isdir(os.path.join(tmpdir, "reports"))
            assert os.path.exists(path)


class TestGoldenThreePolishLoop:
    """Integration test: same text passes normal gate but triggers polish loop in golden-three mode."""

    def test_passes_normal_triggers_polish_golden(self):
        """Same low-quality chapter text passes with is_golden_three=false
        but triggers polish loop when is_golden_three=true.

        US-015: switched to dual-threshold API; we force hard=0.85 to preserve
        the pre-US-015 scenario (strict golden-three blocks score=0.80).
        """
        config = EditorWisdomConfig(
            hard_gate_threshold=0.75,
            golden_three_hard_threshold=0.85,
        )

        def score_80_checker(text: str, chapter_no: int) -> dict:
            return {
                "agent": "editor-wisdom-checker",
                "chapter": chapter_no,
                "score": 0.80,
                "violations": [
                    {"rule_id": "EW-0001", "quote": "低质量段落", "severity": "soft", "fix_suggestion": "重写"},
                ],
                "summary": "一般质量",
            }

        polish_calls: list[int] = []

        def tracking_polish(text: str, violations: list[dict], chapter_no: int) -> str:
            polish_calls.append(chapter_no)
            return text + "\n（已润色）"

        with tempfile.TemporaryDirectory() as tmpdir:
            normal_result = run_review_gate(
                chapter_text="低质量测试章节正文，存在一些问题需要修复。",
                chapter_no=10,
                project_root=tmpdir,
                checker_fn=score_80_checker,
                polish_fn=tracking_polish,
                config=config,
            )
            assert normal_result.passed
            assert len(polish_calls) == 0

        polish_calls.clear()

        with tempfile.TemporaryDirectory() as tmpdir:
            golden_result = run_review_gate(
                chapter_text="低质量测试章节正文，存在一些问题需要修复。",
                chapter_no=1,
                project_root=tmpdir,
                checker_fn=score_80_checker,
                polish_fn=tracking_polish,
                config=config,
            )
            assert not golden_result.passed
            assert golden_result.threshold == 0.85
            assert len(polish_calls) == 2  # 3 attempts = 2 polish calls
            assert golden_result.final_text is None

    def test_golden_passes_with_high_score(self):
        """Golden-three chapter passes when score exceeds golden_three_hard_threshold."""
        config = EditorWisdomConfig(golden_three_hard_threshold=0.85)

        def high_score_checker(text: str, chapter_no: int) -> dict:
            return {
                "agent": "editor-wisdom-checker",
                "chapter": chapter_no,
                "score": 0.90,
                "violations": [],
                "summary": "优秀",
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="高质量章节。",
                chapter_no=2,
                project_root=tmpdir,
                checker_fn=high_score_checker,
                polish_fn=lambda t, v, c: t,
                config=config,
            )
            assert result.passed
            assert result.threshold == 0.85

    def test_blocked_md_for_golden_three(self):
        """Golden-three chapter that never passes gets blocked.md."""
        config = EditorWisdomConfig(golden_three_hard_threshold=0.85)

        def always_low_checker(text: str, chapter_no: int) -> dict:
            return {
                "agent": "editor-wisdom-checker",
                "chapter": chapter_no,
                "score": 0.60,
                "violations": [
                    {"rule_id": "EW-0001", "quote": "开头太弱", "severity": "hard", "fix_suggestion": "增强触发"},
                    {"rule_id": "EW-0002", "quote": "缺少钩子", "severity": "hard", "fix_suggestion": "添加钩子"},
                ],
                "summary": "严重不达标",
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="弱开头章节。",
                chapter_no=1,
                project_root=tmpdir,
                checker_fn=always_low_checker,
                polish_fn=lambda t, v, c: t,
                config=config,
            )
            assert not result.passed
            assert result.blocked_path is not None
            assert os.path.exists(result.blocked_path)
            with open(result.blocked_path, encoding="utf-8") as f:
                content = f.read()
            assert "EW-0001" in content
            assert "0.85" in content
