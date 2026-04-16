"""Semantic retriever over human-written style fragments using FAISS."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

DEFAULT_INDEX_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "style_rag"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"


@dataclass
class StyleFragment:
    id: str
    book_title: str
    book_genre: str
    chapter_num: int
    scene_index: int
    scene_type: str
    emotion: str
    content: str
    word_count: int
    avg_sentence_length: float = 0.0
    short_sentence_ratio: float = 0.0
    long_sentence_ratio: float = 0.0
    dialogue_ratio: float = 0.0
    exclamation_density: float = 0.0
    ellipsis_density: float = 0.0
    question_density: float = 0.0
    quality_score: float = 0.0
    score: float = 0.0


class StyleRAGRetriever:
    """Retrieve human-written style fragments by semantic similarity."""

    def __init__(self, index_dir: Path | str = DEFAULT_INDEX_DIR) -> None:
        index_dir = Path(index_dir)
        faiss_path = index_dir / "style_rag.faiss"
        meta_path = index_dir / "metadata.json"
        contents_path = index_dir / "contents.json"

        missing = [p for p in (faiss_path, meta_path, contents_path) if not p.exists()]
        if missing:
            raise FileNotFoundError(
                f"Style RAG index files missing: {[str(p) for p in missing]}. "
                f"Run 'python scripts/build_style_rag.py' to build the index."
            )

        self._index = faiss.read_index(str(faiss_path))
        self._metadata: list[dict] = json.loads(
            meta_path.read_text(encoding="utf-8")
        )
        contents_raw = json.loads(contents_path.read_text(encoding="utf-8"))
        self._contents: dict[str, str] = {c["id"]: c["content"] for c in contents_raw}
        self._model = SentenceTransformer(MODEL_NAME)

    @property
    def fragment_count(self) -> int:
        return len(self._metadata)

    def retrieve(
        self,
        query: str,
        k: int = 5,
        scene_type: str | None = None,
        emotion: str | None = None,
        genre: str | None = None,
        min_quality: float = 0.0,
    ) -> list[StyleFragment]:
        q_emb = self._model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        )
        q_vec = np.array(q_emb, dtype=np.float32).reshape(1, -1)

        filters = self._build_filter_mask(scene_type, emotion, genre, min_quality)

        if filters is not None:
            indices = [i for i, keep in enumerate(filters) if keep]
            if not indices:
                return []
            return self._filtered_search(q_vec, indices, k)

        return self._full_search(q_vec, k)

    def _build_filter_mask(
        self,
        scene_type: str | None,
        emotion: str | None,
        genre: str | None,
        min_quality: float,
    ) -> list[bool] | None:
        if scene_type is None and emotion is None and genre is None and min_quality <= 0:
            return None

        mask = []
        for m in self._metadata:
            keep = True
            if scene_type is not None and m.get("scene_type") != scene_type:
                keep = False
            if emotion is not None and m.get("emotion") != emotion:
                keep = False
            if genre is not None and genre not in (m.get("book_genre") or ""):
                keep = False
            if min_quality > 0 and (m.get("quality_score") or 0) < min_quality:
                keep = False
            mask.append(keep)
        return mask

    def _filtered_search(
        self, q_vec: np.ndarray, indices: Sequence[int], k: int
    ) -> list[StyleFragment]:
        vecs = np.array(
            [self._index.reconstruct(i) for i in indices], dtype=np.float32
        )
        sims = (vecs @ q_vec.T).flatten()
        top_k = min(k, len(indices))
        ranked = np.argsort(-sims)[:top_k]

        results: list[StyleFragment] = []
        for pos in ranked:
            orig_idx = indices[pos]
            meta = self._metadata[orig_idx]
            results.append(self._meta_to_fragment(meta, float(sims[pos])))
        return results

    def _full_search(self, q_vec: np.ndarray, k: int) -> list[StyleFragment]:
        actual_k = min(k, len(self._metadata))
        scores, faiss_indices = self._index.search(q_vec, actual_k)
        results: list[StyleFragment] = []
        for sim, idx in zip(scores[0], faiss_indices[0]):
            if idx < 0:
                continue
            results.append(self._meta_to_fragment(self._metadata[idx], float(sim)))
        return results

    def _meta_to_fragment(self, meta: dict, score: float) -> StyleFragment:
        fid = meta["id"]
        content = self._contents.get(fid, meta.get("content_preview", ""))
        return StyleFragment(
            id=fid,
            book_title=meta.get("book_title", ""),
            book_genre=meta.get("book_genre", ""),
            chapter_num=meta.get("chapter_num", 0),
            scene_index=meta.get("scene_index", 0),
            scene_type=meta.get("scene_type", ""),
            emotion=meta.get("emotion", ""),
            content=content,
            word_count=meta.get("word_count", 0),
            avg_sentence_length=meta.get("avg_sentence_length", 0.0),
            short_sentence_ratio=meta.get("short_sentence_ratio", 0.0),
            long_sentence_ratio=meta.get("long_sentence_ratio", 0.0),
            dialogue_ratio=meta.get("dialogue_ratio", 0.0),
            exclamation_density=meta.get("exclamation_density", 0.0),
            ellipsis_density=meta.get("ellipsis_density", 0.0),
            question_density=meta.get("question_density", 0.0),
            quality_score=meta.get("quality_score", 0.0),
            score=score,
        )
