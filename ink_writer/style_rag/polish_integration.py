"""Bridge between polish-agent and Style RAG retriever.

Given AI-tasting paragraphs (from anti-detection-checker fix_priority),
retrieves similar human-written snippets and formats them as rewrite
reference for the polish prompt.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Sequence

from ink_writer.style_rag.retriever import StyleFragment

logger = logging.getLogger(__name__)

FIX_TYPE_TO_SCENE_HINT: dict[str, str | None] = {
    "句长平坦区": None,
    "信息密度无波动": None,
    "因果链过密": None,
    "对话同质": "对话",
    "段落过于工整": None,
    "视角泄露": None,
    "句子碎片化": None,
    "对话缺失": "对话",
    "对话不足": "对话",
    "情感标点不足": None,
}

DEFAULT_TOP_K = 3
MIN_QUALITY = 0.5


class RetrieverProtocol(Protocol):
    """Minimal interface for StyleRAGRetriever to allow easy testing."""

    def retrieve(
        self,
        query: str,
        k: int = 5,
        scene_type: str | None = None,
        emotion: str | None = None,
        genre: str | None = None,
        min_quality: float = 0.0,
    ) -> list[StyleFragment]: ...


@dataclass
class StyleReference:
    """A human-written reference snippet for polish rewriting."""

    fix_location: str
    fix_type: str
    fragments: list[StyleFragment]

    def format_prompt_block(self) -> str:
        if not self.fragments:
            return ""
        lines = [f"【人写参考 · {self.fix_type} · {self.fix_location}】"]
        for i, frag in enumerate(self.fragments, 1):
            stats = (
                f"句长均值{frag.avg_sentence_length:.0f}字 | "
                f"对话占比{frag.dialogue_ratio:.0%} | "
                f"质量{frag.quality_score:.2f}"
            )
            lines.append(f"参考{i}（{frag.book_title}/{frag.scene_type}/{frag.emotion}，{stats}）：")
            lines.append(frag.content)
            lines.append("")
        return "\n".join(lines)


@dataclass
class PolishStylePack:
    """Collection of style references for a single chapter's polish pass."""

    chapter: int
    references: list[StyleReference] = field(default_factory=list)

    @property
    def has_references(self) -> bool:
        return any(r.fragments for r in self.references)

    def format_full_prompt(self) -> str:
        if not self.has_references:
            return ""
        blocks = [r.format_prompt_block() for r in self.references if r.fragments]
        header = (
            "以下为人写标杆片段，仅供改写时参考句式节奏和表达手法，"
            "不可照搬内容或剧情：\n"
        )
        return header + "\n---\n".join(blocks)


def _extract_paragraph_text(
    chapter_text: str, location: str
) -> str:
    """Extract approximate text from chapter based on location string.

    Supports formats like '第3段', '第3-5段', '第12-17行', '段3-5'.
    Returns the text of those paragraphs/lines for use as search query.
    """
    paragraphs = [p.strip() for p in chapter_text.split("\n\n") if p.strip()]

    para_match = re.search(r"[第段](\d+)[-\-–~到]?(\d+)?段?", location)
    if para_match:
        start = int(para_match.group(1)) - 1
        end = int(para_match.group(2)) if para_match.group(2) else start + 1
        if start >= len(paragraphs):
            return ""
        selected = paragraphs[max(0, start) : min(end, len(paragraphs))]
        if selected:
            return "\n".join(selected)

    line_match = re.search(r"[第行](\d+)[-\-–~到](\d+)[行]?", location)
    if line_match:
        lines = chapter_text.split("\n")
        start = int(line_match.group(1)) - 1
        end = int(line_match.group(2))
        selected = lines[max(0, start) : min(end, len(lines))]
        if selected:
            return "\n".join(selected)

    if paragraphs:
        return paragraphs[0][:500]
    return chapter_text[:500]


def build_polish_style_pack(
    fix_priorities: list[dict],
    chapter_text: str,
    chapter_no: int,
    retriever: RetrieverProtocol,
    genre: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    min_quality: float = MIN_QUALITY,
) -> PolishStylePack:
    """Build a PolishStylePack from anti-detection-checker fix_priority list.

    Args:
        fix_priorities: List of dicts with 'location', 'type', 'fix' keys
            from anti-detection-checker output.
        chapter_text: Full chapter text for extracting query context.
        chapter_no: Current chapter number.
        retriever: StyleRAGRetriever or compatible object.
        genre: Optional genre filter for retrieval.
        top_k: Number of reference fragments per fix item.
        min_quality: Minimum quality score filter.

    Returns:
        PolishStylePack with references for each fixable issue.
    """
    pack = PolishStylePack(chapter=chapter_no)

    for fix_item in fix_priorities:
        location = fix_item.get("location", "")
        fix_type = fix_item.get("type", "")

        query_text = _extract_paragraph_text(chapter_text, location)
        if not query_text.strip():
            continue

        scene_hint = FIX_TYPE_TO_SCENE_HINT.get(fix_type)

        try:
            fragments = retriever.retrieve(
                query=query_text[:500],
                k=top_k,
                scene_type=scene_hint,
                genre=genre,
                min_quality=min_quality,
            )
        except Exception:
            logger.warning(
                "Style RAG retrieval failed for %s at %s", fix_type, location,
                exc_info=True,
            )
            fragments = []

        pack.references.append(
            StyleReference(
                fix_location=location,
                fix_type=fix_type,
                fragments=fragments,
            )
        )

    return pack
