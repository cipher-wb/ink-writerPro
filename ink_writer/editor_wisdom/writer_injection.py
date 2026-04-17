"""Inject editor-wisdom rules as hard constraints into the writer-agent prompt."""

from __future__ import annotations

from dataclasses import dataclass, field

from ink_writer.editor_wisdom.config import EditorWisdomConfig, load_config
from ink_writer.editor_wisdom.exceptions import EditorWisdomIndexMissingError
from ink_writer.editor_wisdom.golden_three import GOLDEN_THREE_CATEGORIES
from ink_writer.editor_wisdom.retriever import Retriever, Rule, get_retriever


@dataclass
class WriterConstraintsSection:
    rules: list[Rule] = field(default_factory=list)
    chapter_no: int = 1

    @property
    def empty(self) -> bool:
        return len(self.rules) == 0

    def to_markdown(self) -> str:
        if self.empty:
            return ""
        hard = [r for r in self.rules if r.severity == "hard"]
        soft = [r for r in self.rules if r.severity == "soft"]
        if not hard and not soft:
            return ""
        lines: list[str] = ["### 编辑智慧硬约束（Editor Wisdom Constraints）", ""]
        if hard:
            lines.append("**【硬约束 — 必须遵守，违反将触发返工】**：")
            for r in hard:
                lines.append(f"- [{r.id}][{r.category}] {r.rule}")
            lines.append("")
        if soft:
            lines.append("**【软约束 — 建议遵守】**：")
            for r in soft:
                lines.append(f"- [{r.id}][{r.category}] {r.rule}")
            lines.append("")
        return "\n".join(lines)


def build_writer_constraints(
    chapter_outline: str,
    chapter_no: int = 1,
    *,
    config: EditorWisdomConfig | None = None,
    retriever: Retriever | None = None,
) -> WriterConstraintsSection:
    """Build the 硬约束 section for writer-agent prompt injection.

    Groups rules by severity (hard first, soft next, info omitted).
    When chapter_no <= 3, additionally injects rules whose applies_to includes 'golden_three'.
    """
    if config is None:
        config = load_config()

    if not config.enabled or not config.inject_into.writer:
        return WriterConstraintsSection(chapter_no=chapter_no)

    if retriever is None:
        try:
            retriever = get_retriever()  # v13 US-006：单例复用，避免每章重加载 BAAI 模型
        except EditorWisdomIndexMissingError:
            if config.enabled:
                raise
            return WriterConstraintsSection(chapter_no=chapter_no)
        except Exception:
            if config.enabled:
                raise
            return WriterConstraintsSection(chapter_no=chapter_no)

    k = config.retrieval_top_k
    rules = retriever.retrieve(query=chapter_outline, k=k)

    if chapter_no <= 3:
        golden_rules = [
            r for r in retriever.retrieve(query=chapter_outline, k=k * 2)
            if r.category in GOLDEN_THREE_CATEGORIES
        ]
        seen_ids = {r.id for r in rules}
        for r in golden_rules:
            if r.id not in seen_ids:
                rules.append(r)
                seen_ids.add(r.id)

    filtered = [r for r in rules if r.severity in ("hard", "soft")]
    if not filtered:
        return WriterConstraintsSection(chapter_no=chapter_no)

    return WriterConstraintsSection(rules=filtered, chapter_no=chapter_no)
