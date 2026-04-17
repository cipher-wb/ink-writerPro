"""Inject editor-wisdom rules into the context-agent execution package."""

from __future__ import annotations

from dataclasses import dataclass, field

from ink_writer.editor_wisdom.config import EditorWisdomConfig, load_config
from ink_writer.editor_wisdom.exceptions import EditorWisdomIndexMissingError
from ink_writer.editor_wisdom.golden_three import GOLDEN_THREE_CATEGORIES
from ink_writer.editor_wisdom.retriever import Retriever, Rule, get_retriever


@dataclass
class EditorWisdomSection:
    rules: list[Rule] = field(default_factory=list)
    query_used: str = ""

    @property
    def empty(self) -> bool:
        return len(self.rules) == 0

    def to_markdown(self) -> str:
        if self.empty:
            return ""
        lines: list[str] = ["### 12. 编辑建议（Editor Wisdom）", ""]
        hard = [r for r in self.rules if r.severity == "hard"]
        soft = [r for r in self.rules if r.severity == "soft"]
        info = [r for r in self.rules if r.severity == "info"]
        if hard:
            lines.append("**硬约束（必须遵守）**：")
            for r in hard:
                lines.append(f"- [{r.id}][{r.category}] {r.rule}")
            lines.append("")
        if soft:
            lines.append("**软约束（建议遵守）**：")
            for r in soft:
                lines.append(f"- [{r.id}][{r.category}] {r.rule}")
            lines.append("")
        if info:
            lines.append("**参考信息**：")
            for r in info:
                lines.append(f"- [{r.id}][{r.category}] {r.rule}")
            lines.append("")
        return "\n".join(lines)


def build_editor_wisdom_section(
    chapter_outline: str,
    scene_type: str | None = None,
    chapter_no: int = 1,
    *,
    config: EditorWisdomConfig | None = None,
    retriever: Retriever | None = None,
) -> EditorWisdomSection:
    """Build the 编辑建议 section for the context-agent execution package.

    Returns an empty section when the module is disabled or retrieval yields nothing.
    """
    if config is None:
        config = load_config()

    if not config.enabled or not config.inject_into.context:
        return EditorWisdomSection()

    query = chapter_outline
    if scene_type:
        query = f"{scene_type} {query}"

    if retriever is None:
        try:
            retriever = get_retriever()  # v13 US-006：单例复用，避免每章重加载 BAAI 模型
        except EditorWisdomIndexMissingError:
            if config.enabled:
                raise
            return EditorWisdomSection()
        except Exception:
            if config.enabled:
                raise
            return EditorWisdomSection()

    k = config.retrieval_top_k
    rules = retriever.retrieve(query=query, k=k)

    if chapter_no <= 3:
        seen_ids = {r.id for r in rules}
        for cat in sorted(GOLDEN_THREE_CATEGORIES):
            golden_rules = retriever.retrieve(query=query, k=k, category=cat)
            for r in golden_rules:
                if r.id not in seen_ids:
                    rules.append(r)
                    seen_ids.add(r.id)

    if not rules:
        return EditorWisdomSection()

    return EditorWisdomSection(rules=rules, query_used=query)
