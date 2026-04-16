"""Style RAG — 人写风格参考检索。"""

from ink_writer.style_rag.polish_integration import (
    PolishStylePack,
    StyleReference,
    build_polish_style_pack,
)
from ink_writer.style_rag.retriever import StyleFragment, StyleRAGRetriever

__all__ = [
    "PolishStylePack",
    "StyleFragment",
    "StyleRAGRetriever",
    "StyleReference",
    "build_polish_style_pack",
]
