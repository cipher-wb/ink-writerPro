"""Semantic retriever over editor-wisdom rules using a local FAISS index."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from ink_writer.editor_wisdom.exceptions import EditorWisdomIndexMissingError

DEFAULT_INDEX_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "editor-wisdom" / "vector_index"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"

# v13 US-006 单例缓存：Retriever 实例化代价高（BAAI/bge-small-zh-v1.5 加载 ~30s），
# 生产链路多处（step3_harness_gate / writer_injection / context_injection）每章重建
# 导致重复加载。get_retriever() 按 index_dir 做 module-level 缓存，默认路径下首次
# 调用后常驻。仍允许显式 Retriever(index_dir=...) 构造用于测试隔离。
_RETRIEVER_CACHE: dict[str, "Retriever"] = {}


def get_retriever(index_dir: Path | str = DEFAULT_INDEX_DIR) -> "Retriever":
    """返回 process-level 单例。同一 index_dir 的 Retriever 只加载一次。

    v13 US-006：替代裸 `Retriever()` 调用，避免每章重复加载 BAAI/bge 模型。
    若需测试隔离请直接 Retriever(index_dir=tmp_path)。
    """
    key = str(Path(index_dir).resolve())
    if key not in _RETRIEVER_CACHE:
        _RETRIEVER_CACHE[key] = Retriever(index_dir)
    return _RETRIEVER_CACHE[key]


def clear_retriever_cache() -> None:
    """Test hook: 清空 module-level 缓存。"""
    _RETRIEVER_CACHE.clear()


@dataclass
class Rule:
    id: str
    category: str
    rule: str
    why: str
    severity: str
    applies_to: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    score: float = 0.0


class Retriever:
    def __init__(self, index_dir: Path | str = DEFAULT_INDEX_DIR) -> None:
        index_dir = Path(index_dir)
        faiss_path = index_dir / "rules.faiss"
        meta_path = index_dir / "metadata.json"
        missing = [p for p in (faiss_path, meta_path) if not p.exists()]
        if missing:
            raise EditorWisdomIndexMissingError(
                f"Editor-wisdom index files missing: {[str(p) for p in missing]}. "
                f"Run 'ink editor-wisdom rebuild' to generate the index."
            )
        self._index = faiss.read_index(str(faiss_path))
        self._metadata: list[dict] = json.loads(
            meta_path.read_text(encoding="utf-8")
        )
        self._model = SentenceTransformer(MODEL_NAME)

    def retrieve(
        self,
        query: str,
        k: int = 5,
        category: str | None = None,
    ) -> list[Rule]:
        q_emb = self._model.encode([query], normalize_embeddings=True, show_progress_bar=False)
        q_vec = np.array(q_emb, dtype=np.float32).reshape(1, -1)

        if category is not None:
            indices = [i for i, m in enumerate(self._metadata) if m["category"] == category]
            if not indices:
                return []
            cat_vecs = np.array(
                [self._index.reconstruct(i) for i in indices], dtype=np.float32
            )
            sims = (cat_vecs @ q_vec.T).flatten()
            top_k = min(k, len(indices))
            ranked = np.argsort(-sims)[:top_k]
            results: list[Rule] = []
            for pos in ranked:
                meta = self._metadata[indices[pos]]
                results.append(self._meta_to_rule(meta, float(sims[pos])))
            return results

        scores, faiss_indices = self._index.search(q_vec, min(k, len(self._metadata)))
        results = []
        for sim, idx in zip(scores[0], faiss_indices[0]):
            if idx < 0:
                continue
            results.append(self._meta_to_rule(self._metadata[idx], float(sim)))
        return results

    @staticmethod
    def _meta_to_rule(meta: dict, score: float) -> Rule:
        return Rule(
            id=meta["id"],
            category=meta["category"],
            rule=meta["rule"],
            why=meta["why"],
            severity=meta["severity"],
            applies_to=meta.get("applies_to", []),
            source_files=meta.get("source_files", []),
            score=score,
        )
