"""v18 US-001: A/B test for retrieval_top_k 5 -> 15 token inflation.

Verifies that expanding retrieval_top_k from 5 to 15 keeps the writer-prompt
token inflation within the 30% budget specified in PRD v18 US-001.

The inflation is measured against a representative writer-prompt baseline
(agent spec) rather than the raw rules markdown, because the absolute rule
section is a small fraction of the total prompt.
"""

from __future__ import annotations

import re
from pathlib import Path

from ink_writer.editor_wisdom.config import EditorWisdomConfig
from ink_writer.editor_wisdom.retriever import Rule
from ink_writer.editor_wisdom.writer_injection import build_writer_constraints

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WRITER_AGENT_SPEC = PROJECT_ROOT / "ink-writer" / "agents" / "writer-agent.md"
TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+")


def _tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text)


class _FakeRetriever:
    def __init__(self, rules: list[Rule]) -> None:
        self._rules = rules

    def retrieve(self, query: str, k: int = 5, category: str | None = None) -> list[Rule]:
        results = self._rules
        if category is not None:
            results = [r for r in results if r.category == category]
        return results[:k]


def _make_rules(count: int) -> list[Rule]:
    """Create N plausibly-sized rules mirroring the real corpus."""
    categories = ["opening", "hook", "taboo", "pacing", "voice", "character", "worldview"]
    rules = []
    for i in range(count):
        rules.append(
            Rule(
                id=f"EW-{i:04d}",
                category=categories[i % len(categories)],
                rule=f"规则 {i}：主角在开篇需要在三百字内落定核心冲突与情感锚点，避免无效信息铺陈。",
                why="编辑反馈：读者留存曲线在前 300 字出现陡降。",
                severity="hard" if i % 3 == 0 else "soft",
                applies_to=["golden_three"] if i < 5 else [],
                source_files=[],
            )
        )
    return rules


def _build_prompt_snippet(chapter_no: int, top_k: int, rule_pool: list[Rule]) -> str:
    """Build a writer prompt snippet: agent spec baseline + injected rules markdown."""
    baseline = WRITER_AGENT_SPEC.read_text(encoding="utf-8") if WRITER_AGENT_SPEC.exists() else ""
    config = EditorWisdomConfig(retrieval_top_k=top_k)
    retriever = _FakeRetriever(rule_pool)
    section = build_writer_constraints(
        "主角初入学院，第一次见证宗门遗址",
        chapter_no=chapter_no,
        config=config,
        retriever=retriever,
    )
    return baseline + "\n\n" + section.to_markdown()


def test_top_k_15_inflation_within_30pct_for_generic_chapter():
    """Chapter >3: top_k=15 vs top_k=5 — prompt token inflation must be ≤30%."""
    rule_pool = _make_rules(40)
    prompt_k5 = _build_prompt_snippet(chapter_no=10, top_k=5, rule_pool=rule_pool)
    prompt_k15 = _build_prompt_snippet(chapter_no=10, top_k=15, rule_pool=rule_pool)

    tokens_k5 = len(_tokenize(prompt_k5))
    tokens_k15 = len(_tokenize(prompt_k15))

    assert tokens_k5 > 0, "baseline prompt must not be empty"
    inflation = (tokens_k15 - tokens_k5) / tokens_k5
    assert inflation <= 0.30, (
        f"top_k 5->15 inflation {inflation:.2%} exceeds 30% budget "
        f"(k5={tokens_k5}, k15={tokens_k15})"
    )


def test_top_k_15_inflation_within_30pct_for_golden_three():
    """Chapter ≤3 (golden three): same ≤30% budget must hold."""
    rule_pool = _make_rules(40)
    prompt_k5 = _build_prompt_snippet(chapter_no=1, top_k=5, rule_pool=rule_pool)
    prompt_k15 = _build_prompt_snippet(chapter_no=1, top_k=15, rule_pool=rule_pool)

    tokens_k5 = len(_tokenize(prompt_k5))
    tokens_k15 = len(_tokenize(prompt_k15))

    inflation = (tokens_k15 - tokens_k5) / tokens_k5
    assert inflation <= 0.30, (
        f"golden-three top_k 5->15 inflation {inflation:.2%} exceeds 30% budget "
        f"(k5={tokens_k5}, k15={tokens_k15})"
    )


def test_top_k_15_actually_retrieves_more_rules():
    """Sanity check: top_k=15 returns strictly more rules than top_k=5."""
    rule_pool = _make_rules(40)
    config_k5 = EditorWisdomConfig(retrieval_top_k=5)
    config_k15 = EditorWisdomConfig(retrieval_top_k=15)
    retriever = _FakeRetriever(rule_pool)

    sec_k5 = build_writer_constraints(
        "第 10 章大纲", chapter_no=10, config=config_k5, retriever=retriever
    )
    sec_k15 = build_writer_constraints(
        "第 10 章大纲", chapter_no=10, config=config_k15, retriever=retriever
    )
    assert len(sec_k15.rules) > len(sec_k5.rules)
    assert len(sec_k5.rules) == 5
    assert len(sec_k15.rules) == 15


def test_default_config_uses_top_k_15():
    """The on-disk config must ship top_k=15 (v18 US-001)."""
    from ink_writer.editor_wisdom.config import load_config

    actual = PROJECT_ROOT / "config" / "editor-wisdom.yaml"
    if actual.exists():
        cfg = load_config(actual)
        assert cfg.retrieval_top_k == 15, (
            "v18 US-001 requires retrieval_top_k>=15 for f2 uplift to ≥7"
        )
