"""Inject cultural lexicon terms into the context-agent execution package."""

from __future__ import annotations

from dataclasses import dataclass, field

from ink_writer.cultural_lexicon.config import CulturalLexiconConfig, load_config
from ink_writer.cultural_lexicon.loader import LexiconEntry, load_lexicon, sample_lexicon


@dataclass
class CulturalLexiconSection:
    genre: str = ""
    entries: list[LexiconEntry] = field(default_factory=list)
    min_terms: int = 0

    @property
    def empty(self) -> bool:
        return len(self.entries) == 0

    def to_markdown(self) -> str:
        if self.empty:
            return ""
        lines: list[str] = [
            "### 13. 文化语料库（Cultural Lexicon）",
            "",
            f"**题材**：{self.genre} | **本章最低使用数**：{self.min_terms}",
            "",
            "**推荐用词**（自然融入，禁止堆砌）：",
            "",
        ]
        by_cat: dict[str, list[LexiconEntry]] = {}
        for e in self.entries:
            by_cat.setdefault(e.category, []).append(e)

        for cat, cat_entries in sorted(by_cat.items()):
            lines.append(f"**[{cat}]**")
            for e in cat_entries:
                lines.append(f"- **{e.term}**（{e.type}）：{e.usage_example}")
            lines.append("")

        lines.append(
            f"> 硬约束：本章正文须自然使用 ≥{self.min_terms} 个上述或同类文化词汇，"
            "不得机械罗列。"
        )
        lines.append("")
        return "\n".join(lines)


def build_cultural_lexicon_section(
    genre: str,
    chapter_no: int = 1,
    *,
    config: CulturalLexiconConfig | None = None,
    lexicon: list[LexiconEntry] | None = None,
    categories: list[str] | None = None,
) -> CulturalLexiconSection:
    """Build the 文化语料库 section for the context-agent execution package."""
    if config is None:
        config = load_config()

    if not config.enabled or not config.inject_into.context:
        return CulturalLexiconSection()

    if lexicon is None:
        lexicon = load_lexicon(genre)

    if not lexicon:
        return CulturalLexiconSection()

    min_terms = config.min_terms_per_chapter.get(genre, 3)

    sampled = sample_lexicon(
        lexicon,
        config.inject_count,
        chapter_no=chapter_no,
        seed_offset=config.seed_offset,
        categories=categories,
    )

    if not sampled:
        return CulturalLexiconSection()

    return CulturalLexiconSection(
        genre=genre,
        entries=sampled,
        min_terms=min_terms,
    )
