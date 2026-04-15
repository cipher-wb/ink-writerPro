"""Tests for writer-agent editor-wisdom constraint injection."""

from __future__ import annotations

import pytest

from ink_writer.editor_wisdom.config import EditorWisdomConfig, InjectInto
from ink_writer.editor_wisdom.retriever import Rule
from ink_writer.editor_wisdom.writer_injection import (
    WriterConstraintsSection,
    build_writer_constraints,
)


class FakeRetriever:
    """Retriever that returns predefined rules."""

    def __init__(self, rules: list[Rule]) -> None:
        self._rules = rules

    def retrieve(
        self, query: str, k: int = 5, category: str | None = None
    ) -> list[Rule]:
        results = self._rules
        if category is not None:
            results = [r for r in results if r.category == category]
        return results[:k]


def _make_rule(
    id: str = "EW-0001",
    category: str = "opening",
    rule: str = "测试规则",
    severity: str = "hard",
    applies_to: list[str] | None = None,
) -> Rule:
    return Rule(
        id=id,
        category=category,
        rule=rule,
        why="测试原因",
        severity=severity,
        applies_to=applies_to or [],
        source_files=[],
    )


class TestWriterConstraintsSection:
    def test_empty_section(self):
        section = WriterConstraintsSection()
        assert section.empty
        assert section.to_markdown() == ""

    def test_hard_rules_in_markdown(self):
        rules = [_make_rule(severity="hard", rule="开篇必须有钩子")]
        section = WriterConstraintsSection(rules=rules)
        md = section.to_markdown()
        assert "硬约束" in md
        assert "开篇必须有钩子" in md
        assert "EW-0001" in md

    def test_soft_rules_in_markdown(self):
        rules = [_make_rule(severity="soft", rule="建议多用对话")]
        section = WriterConstraintsSection(rules=rules)
        md = section.to_markdown()
        assert "软约束" in md
        assert "建议多用对话" in md

    def test_info_rules_omitted(self):
        rules = [_make_rule(severity="info", rule="参考信息")]
        section = WriterConstraintsSection(rules=rules)
        assert section.empty is False
        md = section.to_markdown()
        assert md == ""

    def test_hard_before_soft(self):
        rules = [
            _make_rule(id="EW-0002", severity="soft", rule="软规则"),
            _make_rule(id="EW-0001", severity="hard", rule="硬规则"),
        ]
        section = WriterConstraintsSection(rules=rules)
        md = section.to_markdown()
        hard_pos = md.index("硬规则")
        soft_pos = md.index("软规则")
        assert hard_pos < soft_pos

    def test_mixed_severities(self):
        rules = [
            _make_rule(id="EW-0001", severity="hard", rule="硬规则A"),
            _make_rule(id="EW-0002", severity="soft", rule="软规则B"),
            _make_rule(id="EW-0003", severity="info", rule="信息C"),
        ]
        section = WriterConstraintsSection(rules=rules)
        md = section.to_markdown()
        assert "硬规则A" in md
        assert "软规则B" in md
        assert "信息C" not in md


class TestBuildWriterConstraints:
    def test_disabled_config(self):
        config = EditorWisdomConfig(enabled=False)
        retriever = FakeRetriever([_make_rule()])
        result = build_writer_constraints(
            "测试大纲", config=config, retriever=retriever
        )
        assert result.empty

    def test_writer_inject_disabled(self):
        config = EditorWisdomConfig(inject_into=InjectInto(writer=False))
        retriever = FakeRetriever([_make_rule()])
        result = build_writer_constraints(
            "测试大纲", config=config, retriever=retriever
        )
        assert result.empty

    def test_basic_retrieval(self):
        rules = [
            _make_rule(id="EW-0001", severity="hard", rule="必须有开场钩子"),
            _make_rule(id="EW-0002", severity="soft", rule="建议用对话推进"),
        ]
        config = EditorWisdomConfig()
        retriever = FakeRetriever(rules)
        result = build_writer_constraints(
            "主角第一次进入学院", chapter_no=5, config=config, retriever=retriever
        )
        assert not result.empty
        assert len(result.rules) == 2

    def test_info_only_returns_empty(self):
        rules = [_make_rule(severity="info")]
        config = EditorWisdomConfig()
        retriever = FakeRetriever(rules)
        result = build_writer_constraints(
            "测试大纲", config=config, retriever=retriever
        )
        assert result.empty

    def test_golden_three_injects_extra_rules(self):
        base_rule = _make_rule(id="EW-0001", severity="hard", rule="基础规则")
        golden_rule = _make_rule(
            id="EW-0099",
            severity="hard",
            rule="黄金三章专用规则",
            applies_to=["golden_three"],
        )
        retriever = FakeRetriever([base_rule, golden_rule])
        config = EditorWisdomConfig(retrieval_top_k=10)
        result = build_writer_constraints(
            "第一章开篇", chapter_no=1, config=config, retriever=retriever
        )
        rule_ids = {r.id for r in result.rules}
        assert "EW-0099" in rule_ids

    def test_golden_three_not_for_ch4(self):
        normal_rule = _make_rule(id="EW-0001", severity="hard", rule="普通规则")

        class SelectiveRetriever:
            def retrieve(self, query: str, k: int = 5, category: str | None = None):
                return [normal_rule]

        config = EditorWisdomConfig()
        result = build_writer_constraints(
            "第四章", chapter_no=4, config=config, retriever=SelectiveRetriever()
        )
        rule_ids = {r.id for r in result.rules}
        assert "EW-0099" not in rule_ids

    def test_dedup_golden_three_rules(self):
        rule = _make_rule(
            id="EW-0001",
            severity="hard",
            rule="同时是普通和黄金三章规则",
            applies_to=["golden_three"],
        )
        retriever = FakeRetriever([rule])
        config = EditorWisdomConfig(retrieval_top_k=10)
        result = build_writer_constraints(
            "第一章", chapter_no=1, config=config, retriever=retriever
        )
        assert len([r for r in result.rules if r.id == "EW-0001"]) == 1

    def test_empty_retrieval(self):
        retriever = FakeRetriever([])
        config = EditorWisdomConfig()
        result = build_writer_constraints(
            "测试大纲", config=config, retriever=retriever
        )
        assert result.empty

    def test_retriever_failure_raises_when_enabled(self, monkeypatch):
        config = EditorWisdomConfig(enabled=True)

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated index missing")

        from ink_writer.editor_wisdom import writer_injection as _wi

        monkeypatch.setattr(_wi, "Retriever", _boom)
        with pytest.raises(Exception):
            build_writer_constraints("测试大纲", config=config, retriever=None)

    def test_markdown_contains_hard_rule_text(self):
        """Integration test: assert prompt contains at least one hard-severity rule text."""
        rules = [
            _make_rule(id="EW-0010", severity="hard", rule="开篇三秒必须抓住读者"),
            _make_rule(id="EW-0011", severity="soft", rule="配角需有个性化语言"),
        ]
        config = EditorWisdomConfig()
        retriever = FakeRetriever(rules)
        result = build_writer_constraints(
            "主角初入江湖的开篇章节",
            chapter_no=1,
            config=config,
            retriever=retriever,
        )
        md = result.to_markdown()
        assert "开篇三秒必须抓住读者" in md
        hard_section_found = "硬约束" in md
        assert hard_section_found

    def test_chapter_no_preserved(self):
        rules = [_make_rule(severity="hard")]
        config = EditorWisdomConfig()
        retriever = FakeRetriever(rules)
        result = build_writer_constraints(
            "测试", chapter_no=42, config=config, retriever=retriever
        )
        assert result.chapter_no == 42
