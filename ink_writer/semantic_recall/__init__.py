"""Semantic chapter recall: vector-based retrieval replacing keyword matching."""

from ink_writer.semantic_recall.config import SemanticRecallConfig
from ink_writer.semantic_recall.chapter_index import ChapterVectorIndex
from ink_writer.semantic_recall.retriever import SemanticChapterRetriever

__all__ = [
    "SemanticRecallConfig",
    "ChapterVectorIndex",
    "SemanticChapterRetriever",
]
