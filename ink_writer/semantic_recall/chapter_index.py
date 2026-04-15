"""FAISS vector index over chapter memory cards."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import faiss
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"


@dataclass
class ChapterCard:
    chapter: int
    summary: str
    goal: str
    conflict: str
    result: str
    next_chapter_bridge: str
    unresolved_questions: list[str]
    key_facts: list[str]
    involved_entities: list[str]
    plot_progress: list[str]

    def to_embed_text(self) -> str:
        parts = [
            f"第{self.chapter}章",
            self.summary,
            self.goal,
            self.conflict,
            self.result,
        ]
        if self.unresolved_questions:
            parts.append("悬念:" + "；".join(self.unresolved_questions[:3]))
        if self.key_facts:
            parts.append("关键:" + "；".join(self.key_facts[:3]))
        return " ".join(p for p in parts if p).strip()

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> ChapterCard:
        def _list_field(val: Any) -> list[str]:
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                try:
                    parsed = json.loads(val)
                    return parsed if isinstance(parsed, list) else []
                except (json.JSONDecodeError, TypeError):
                    return []
            return []

        return cls(
            chapter=int(row.get("chapter", 0)),
            summary=str(row.get("summary", "") or ""),
            goal=str(row.get("goal", "") or ""),
            conflict=str(row.get("conflict", "") or ""),
            result=str(row.get("result", "") or ""),
            next_chapter_bridge=str(row.get("next_chapter_bridge", "") or ""),
            unresolved_questions=_list_field(row.get("unresolved_questions")),
            key_facts=_list_field(row.get("key_facts")),
            involved_entities=_list_field(row.get("involved_entities")),
            plot_progress=_list_field(row.get("plot_progress")),
        )


class ChapterVectorIndex:
    """Builds and queries a FAISS index over chapter memory cards."""

    def __init__(
        self,
        index_dir: Path | str,
        model_name: str = DEFAULT_MODEL,
    ) -> None:
        self._index_dir = Path(index_dir)
        self._model_name = model_name
        self._model = None
        self._index: Optional[faiss.IndexFlatIP] = None
        self._cards: list[ChapterCard] = []
        self._chapter_to_idx: dict[int, int] = {}

        if self._index_files_exist():
            self._load()

    def _index_files_exist(self) -> bool:
        return (
            (self._index_dir / "chapters.faiss").exists()
            and (self._index_dir / "chapters_meta.json").exists()
        )

    @property
    def card_count(self) -> int:
        return len(self._cards)

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def build(self, cards: Sequence[ChapterCard], batch_size: int = 128) -> None:
        if not cards:
            return

        self._cards = list(cards)
        self._chapter_to_idx = {c.chapter: i for i, c in enumerate(self._cards)}

        texts = [c.to_embed_text() for c in self._cards]
        model = self._get_model()

        all_embeddings = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            embs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
            all_embeddings.append(np.array(embs, dtype=np.float32))

        vectors = np.vstack(all_embeddings)
        dim = vectors.shape[1]
        self._index = faiss.IndexFlatIP(dim)
        self._index.add(vectors)

    def save(self) -> None:
        if self._index is None or not self._cards:
            return
        self._index_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self._index_dir / "chapters.faiss"))

        meta = []
        for card in self._cards:
            meta.append({
                "chapter": card.chapter,
                "summary": card.summary[:200],
                "involved_entities": card.involved_entities,
                "unresolved_questions": card.unresolved_questions,
                "key_facts": card.key_facts,
            })
        (self._index_dir / "chapters_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self) -> None:
        faiss_path = self._index_dir / "chapters.faiss"
        meta_path = self._index_dir / "chapters_meta.json"
        self._index = faiss.read_index(str(faiss_path))
        raw_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self._cards = [ChapterCard.from_db_row(m) for m in raw_meta]
        self._chapter_to_idx = {c.chapter: i for i, c in enumerate(self._cards)}

    def add_chapter(self, card: ChapterCard) -> None:
        if self._index is None:
            dim = self._get_model().get_sentence_embedding_dimension()
            self._index = faiss.IndexFlatIP(dim)

        text = card.to_embed_text()
        emb = self._get_model().encode([text], normalize_embeddings=True, show_progress_bar=False)
        vec = np.array(emb, dtype=np.float32).reshape(1, -1)

        if card.chapter in self._chapter_to_idx:
            idx = self._chapter_to_idx[card.chapter]
            self._cards[idx] = card
            old_vec = self._index.reconstruct(idx)
            old_vec[:] = vec[0]
            self._index = self._rebuild_index()
        else:
            self._chapter_to_idx[card.chapter] = len(self._cards)
            self._cards.append(card)
            self._index.add(vec)

    def _rebuild_index(self) -> faiss.IndexFlatIP:
        n = self._index.ntotal
        if n == 0:
            return faiss.IndexFlatIP(self._index.d)
        vecs = np.array([self._index.reconstruct(i) for i in range(n)], dtype=np.float32)
        new_index = faiss.IndexFlatIP(self._index.d)
        new_index.add(vecs)
        return new_index

    def search(
        self,
        query: str,
        k: int = 10,
        before_chapter: Optional[int] = None,
    ) -> list[tuple[ChapterCard, float]]:
        if self._index is None or self._index.ntotal == 0:
            return []

        emb = self._get_model().encode([query], normalize_embeddings=True, show_progress_bar=False)
        q_vec = np.array(emb, dtype=np.float32).reshape(1, -1)

        if before_chapter is not None:
            eligible = [
                i for i, c in enumerate(self._cards) if c.chapter < before_chapter
            ]
            if not eligible:
                return []
            vecs = np.array(
                [self._index.reconstruct(i) for i in eligible], dtype=np.float32
            )
            sims = (vecs @ q_vec.T).flatten()
            top_k = min(k, len(eligible))
            ranked = np.argsort(-sims)[:top_k]
            return [
                (self._cards[eligible[pos]], float(sims[pos]))
                for pos in ranked
            ]

        actual_k = min(k, self._index.ntotal)
        scores, indices = self._index.search(q_vec, actual_k)
        results = []
        for sim, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            results.append((self._cards[idx], float(sim)))
        return results

    def get_card(self, chapter: int) -> Optional[ChapterCard]:
        idx = self._chapter_to_idx.get(chapter)
        if idx is None:
            return None
        return self._cards[idx]

    def get_cards_for_chapters(self, chapters: list[int]) -> list[ChapterCard]:
        return [
            self._cards[self._chapter_to_idx[ch]]
            for ch in chapters
            if ch in self._chapter_to_idx
        ]
