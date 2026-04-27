"""ink_writer.retrieval — 爆款示例语义检索子系统 (US-011/012)."""

from ink_writer.retrieval.explosive_retriever import (
    ExplosiveRetriever,
    build_retriever,
    get_retriever,
)
from ink_writer.retrieval.inject import inject_explosive_examples

__all__ = [
    "ExplosiveRetriever",
    "build_retriever",
    "get_retriever",
    "inject_explosive_examples",
]
