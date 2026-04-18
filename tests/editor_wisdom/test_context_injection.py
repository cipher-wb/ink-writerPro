"""Integration tests for editor-wisdom context injection."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ink_writer.editor_wisdom.config import EditorWisdomConfig, InjectInto
from ink_writer.editor_wisdom.context_injection import (
    EditorWisdomSection,
    build_editor_wisdom_section,
)
from ink_writer.editor_wisdom.retriever import Rule


class FakeRetriever:
    """A fake retriever that returns pre-configured rules."""

    def __init__(self, rules_by_category: dict[str, list[Rule]] | None = None) -> None:
        self._rules_by_category = rules_by_category or {}
        self._all_rules: list[Rule] = []
        for rule_list in self._rules_by_category.values():
            for r in rule_list:
                if r not in self._all_rules:
                    self._all_rules.append(r)

    def retrieve(
        self,
        query: str,
        k: int = 5,
        category: str | None = None,
    ) -> list[Rule]:
        if category is not None:
            pool = self._rules_by_category.get(category, [])
        else:
            pool = self._all_rules
        return pool[:k]


def _make_rule(
    id: str = "EW-0001",
    category: str = "opening",
    rule: str = "开篇必须3秒内抓住读者",
    severity: str = "hard",
) -> Rule:
    return Rule(
        id=id,
        category=category,
        rule=rule,
        why="编辑经验",
        severity=severity,
        applies_to=[category],
        source_files=["test.md"],
    )


# --- EditorWisdomSection tests ---


def test_empty_section_produces_no_markdown():
    section = EditorWisdomSection()
    assert section.empty is True
    assert section.to_markdown() == ""


def test_section_with_rules_produces_markdown():
    rules = [
        _make_rule(id="EW-0001", severity="hard"),
        _make_rule(id="EW-0002", severity="soft", rule="避免套路开头"),
        _make_rule(id="EW-0003", severity="info", rule="参考成功案例"),
    ]
    section = EditorWisdomSection(rules=rules, query_used="开篇")
    md = section.to_markdown()
    assert "编辑建议" in md
    assert "硬约束" in md
    assert "软约束" in md
    assert "参考信息" in md
    assert "EW-0001" in md
    assert "EW-0002" in md
    assert "EW-0003" in md


def test_section_groups_by_severity():
    rules = [
        _make_rule(id="EW-0001", severity="hard"),
        _make_rule(id="EW-0002", severity="soft", rule="建议句式"),
    ]
    section = EditorWisdomSection(rules=rules)
    md = section.to_markdown()
    hard_pos = md.index("硬约束")
    soft_pos = md.index("软约束")
    assert hard_pos < soft_pos


# --- build_editor_wisdom_section tests ---


def test_disabled_config_returns_empty():
    config = EditorWisdomConfig(enabled=False)
    section = build_editor_wisdom_section(
        chapter_outline="主角觉醒",
        config=config,
        retriever=FakeRetriever(),
    )
    assert section.empty is True


def test_context_inject_disabled_returns_empty():
    config = EditorWisdomConfig(
        enabled=True,
        inject_into=InjectInto(context=False, writer=True, polish=True),
    )
    section = build_editor_wisdom_section(
        chapter_outline="主角觉醒",
        config=config,
        retriever=FakeRetriever(),
    )
    assert section.empty is True


def test_empty_retrieval_returns_empty():
    config = EditorWisdomConfig(enabled=True)
    retriever = FakeRetriever(rules_by_category={})
    section = build_editor_wisdom_section(
        chapter_outline="主角觉醒",
        config=config,
        retriever=retriever,
    )
    assert section.empty is True
    assert section.to_markdown() == ""


def test_opening_chapter_contains_opening_rules():
    """Integration: given an opening-chapter outline, exec package contains
    at least one rule with category='opening'."""
    opening_rules = [
        _make_rule(id="EW-0010", category="opening", rule="开篇第一段必须有冲突"),
        _make_rule(id="EW-0011", category="opening", rule="开头不能用时间描述"),
    ]
    hook_rules = [
        _make_rule(id="EW-0020", category="hook", rule="每章必须有钩子"),
    ]
    retriever = FakeRetriever(
        rules_by_category={
            "opening": opening_rules,
            "hook": hook_rules,
        }
    )
    config = EditorWisdomConfig(enabled=True, retrieval_top_k=5)

    section = build_editor_wisdom_section(
        chapter_outline="第一章：少年初入江湖，遭遇神秘老者",
        scene_type="opening",
        chapter_no=1,
        config=config,
        retriever=retriever,
    )

    assert not section.empty
    categories = {r.category for r in section.rules}
    assert "opening" in categories


def test_golden_three_injects_opening_rules():
    """Chapters 1-3 should additionally retrieve opening-category rules."""
    pacing_rule = _make_rule(id="EW-0030", category="pacing", rule="节奏不能拖")
    opening_rule = _make_rule(id="EW-0040", category="opening", rule="开篇要抓人")

    class SelectiveRetriever:
        """Returns pacing rules for general query, opening rules only for category='opening'."""

        def retrieve(self, query: str, k: int = 5, category: str | None = None) -> list[Rule]:
            if category == "opening":
                return [opening_rule]
            return [pacing_rule]

    retriever = SelectiveRetriever()
    config = EditorWisdomConfig(enabled=True, retrieval_top_k=5)

    section_ch1 = build_editor_wisdom_section(
        chapter_outline="第一章大纲",
        chapter_no=1,
        config=config,
        retriever=retriever,
    )
    section_ch10 = build_editor_wisdom_section(
        chapter_outline="第十章大纲",
        chapter_no=10,
        config=config,
        retriever=retriever,
    )

    ch1_categories = {r.category for r in section_ch1.rules}
    ch10_categories = {r.category for r in section_ch10.rules}

    assert "opening" in ch1_categories
    assert "opening" not in ch10_categories


def test_no_duplicate_rules_in_golden_three():
    """When golden-three adds opening rules, duplicates should not appear."""
    shared_rule = _make_rule(id="EW-0050", category="opening", rule="开篇抓人")
    retriever = FakeRetriever(
        rules_by_category={"opening": [shared_rule]}
    )
    config = EditorWisdomConfig(enabled=True, retrieval_top_k=5)

    section = build_editor_wisdom_section(
        chapter_outline="开篇",
        chapter_no=1,
        config=config,
        retriever=retriever,
    )

    ids = [r.id for r in section.rules]
    assert len(ids) == len(set(ids))


def test_scene_type_included_in_query():
    """Scene type should be prepended to the query for better retrieval."""
    calls: list[str] = []

    class TrackingRetriever(FakeRetriever):
        def retrieve(self, query: str, k: int = 5, category: str | None = None) -> list[Rule]:
            calls.append(query)
            return super().retrieve(query, k, category)

    retriever = TrackingRetriever(
        rules_by_category={"opening": [_make_rule()]}
    )
    config = EditorWisdomConfig(enabled=True, retrieval_top_k=5)

    build_editor_wisdom_section(
        chapter_outline="少年入江湖",
        scene_type="战斗",
        chapter_no=5,
        config=config,
        retriever=retriever,
    )

    assert any("战斗" in q for q in calls)


def test_retriever_failure_raises_when_enabled():
    """If retriever init fails and enabled=True, exception propagates."""
    config = EditorWisdomConfig(enabled=True)

    # v14 US-002：Step 2 US-006 改 context_injection 使用 get_retriever 单例，需 patch
    # get_retriever 而非 Retriever；同时清缓存防止被旧实例命中
    from ink_writer.editor_wisdom.retriever import clear_retriever_cache
    clear_retriever_cache()
    with patch(
        "ink_writer.editor_wisdom.context_injection.get_retriever",
        side_effect=FileNotFoundError("no index"),
    ):
        with pytest.raises(FileNotFoundError):
            build_editor_wisdom_section(
                chapter_outline="测试",
                config=config,
            )


def test_disabled_config_returns_empty_without_retriever():
    """When enabled=False, return empty section without attempting retrieval."""
    config = EditorWisdomConfig(enabled=False)
    section = build_editor_wisdom_section(
        chapter_outline="测试",
        config=config,
    )
    assert section.empty is True


def test_markdown_output_format():
    """Verify the markdown section follows expected board format."""
    rules = [
        _make_rule(id="EW-0001", category="opening", severity="hard", rule="开篇必须冲突"),
    ]
    section = EditorWisdomSection(rules=rules, query_used="开篇")
    md = section.to_markdown()

    assert md.startswith("### 12. 编辑建议")
    assert "[EW-0001]" in md
    assert "[opening]" in md
    assert "开篇必须冲突" in md
