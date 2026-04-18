"""Hybrid chapter retriever: semantic Top-K ∪ entity-forced ∪ recent-N."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ink_writer.semantic_recall.bm25 import BM25Index
from ink_writer.semantic_recall.chapter_index import ChapterCard, ChapterVectorIndex
from ink_writer.semantic_recall.config import SemanticRecallConfig

logger = logging.getLogger(__name__)


@dataclass
class RecallHit:
    chapter: int
    score: float
    source: str
    content: str
    involved_entities: list[str] = field(default_factory=list)


class SemanticChapterRetriever:
    """Three-way recall: semantic similarity + entity overlap + recency."""

    def __init__(
        self,
        index: ChapterVectorIndex,
        config: SemanticRecallConfig | None = None,
    ) -> None:
        self._index = index
        self._config = config or SemanticRecallConfig()
        self._bm25: Optional[BM25Index] = None
        self._bm25_fingerprint: Optional[int] = None

    # --- BM25 lazy (re)build ---------------------------------------------
    def _ensure_bm25(self) -> BM25Index:
        cards = self._index._cards
        fingerprint = len(cards)
        if self._bm25 is None or self._bm25_fingerprint != fingerprint:
            corpus = [c.to_embed_text() for c in cards]
            self._bm25 = BM25Index().fit(corpus)
            self._bm25_fingerprint = fingerprint
        return self._bm25

    def recall(
        self,
        query: str,
        chapter_num: int,
        scene_entities: list[str] | None = None,
        recent_n_override: int | None = None,
    ) -> list[RecallHit]:
        cfg = self._config
        recent_n = recent_n_override if recent_n_override is not None else cfg.recent_n
        scene_entities = scene_entities or []
        scene_entity_set = set(e.lower() for e in scene_entities if e)

        merged: dict[int, RecallHit] = {}

        semantic_hits = self._index.search(
            query=query,
            k=cfg.semantic_top_k,
            before_chapter=chapter_num,
        )
        # Track ranks for RRF fusion (semantic)
        semantic_ranks: dict[int, int] = {}
        for rank, (card, sim) in enumerate(semantic_hits):
            semantic_ranks[card.chapter] = rank
            if sim < cfg.min_semantic_score:
                continue
            boosted = self._apply_entity_boost(sim, card, scene_entity_set)
            merged[card.chapter] = RecallHit(
                chapter=card.chapter,
                score=boosted,
                source="semantic",
                content=self._card_to_content(card),
                involved_entities=card.involved_entities,
            )

        # US-022: BM25 lexical branch + reciprocal rank fusion.
        if cfg.hybrid_enabled and cfg.bm25_top_k > 0:
            bm25 = self._ensure_bm25()
            eligible = [
                i for i, c in enumerate(self._index._cards) if c.chapter < chapter_num
            ]
            bm25_hits = bm25.search(query, k=cfg.bm25_top_k, eligible=eligible)
            bm25_ranks: dict[int, int] = {}
            for rank, (doc_idx, bm25_score) in enumerate(bm25_hits):
                card = self._index._cards[doc_idx]
                bm25_ranks[card.chapter] = rank
                rrf_component = 1.0 / (cfg.rrf_k + rank + 1)
                if card.chapter in merged:
                    hit = merged[card.chapter]
                    # Fuse: boost existing semantic score with BM25 RRF contribution.
                    hit.score = hit.score + rrf_component
                    if "bm25" not in hit.source:
                        hit.source = f"{hit.source}+bm25"
                else:
                    merged[card.chapter] = RecallHit(
                        chapter=card.chapter,
                        score=rrf_component,
                        source="bm25",
                        content=self._card_to_content(card),
                        involved_entities=card.involved_entities,
                    )
            # Add RRF component for semantic-only hits too (symmetric fusion).
            for chap, rank in semantic_ranks.items():
                if chap in merged and "bm25" not in merged[chap].source:
                    rrf_component = 1.0 / (cfg.rrf_k + rank + 1)
                    merged[chap].score += rrf_component

        if scene_entity_set:
            entity_hits = self._entity_forced_recall(
                chapter_num, scene_entity_set, cfg.entity_forced_max
            )
            for card in entity_hits:
                if card.chapter in merged:
                    hit = merged[card.chapter]
                    hit.source = "semantic+entity"
                    hit.score = max(hit.score, cfg.min_semantic_score + cfg.entity_boost_weight)
                else:
                    merged[card.chapter] = RecallHit(
                        chapter=card.chapter,
                        score=cfg.min_semantic_score + cfg.entity_boost_weight,
                        source="entity_forced",
                        content=self._card_to_content(card),
                        involved_entities=card.involved_entities,
                    )

        recent_start = max(1, chapter_num - recent_n)
        for ch in range(recent_start, chapter_num):
            if ch in merged:
                merged[ch].source = (
                    merged[ch].source + "+recent"
                    if "recent" not in merged[ch].source
                    else merged[ch].source
                )
                merged[ch].score = max(merged[ch].score, 0.95)
                continue
            card = self._index.get_card(ch)
            if card is None:
                continue
            merged[ch] = RecallHit(
                chapter=ch,
                score=0.95,
                source="recent",
                content=self._card_to_content(card),
                involved_entities=card.involved_entities,
            )

        ranked = sorted(merged.values(), key=lambda h: (-h.score, -h.chapter))
        return ranked[: cfg.final_top_k]

    def _apply_entity_boost(
        self, base_score: float, card: ChapterCard, scene_entities: set[str]
    ) -> float:
        if not scene_entities or not card.involved_entities:
            return base_score
        card_entities = set(e.lower() for e in card.involved_entities)
        overlap = len(scene_entities & card_entities)
        if overlap == 0:
            return base_score
        return base_score + self._config.entity_boost_weight * min(overlap, 3)

    def _entity_forced_recall(
        self, chapter_num: int, scene_entities: set[str], max_hits: int
    ) -> list[ChapterCard]:
        results: list[tuple[int, ChapterCard]] = []
        for card in reversed(self._index._cards):
            if card.chapter >= chapter_num:
                continue
            card_entities = set(e.lower() for e in card.involved_entities)
            overlap = len(scene_entities & card_entities)
            if overlap > 0:
                results.append((overlap, card))
            if len(results) >= max_hits * 3:
                break
        results.sort(key=lambda x: (-x[0], -x[1].chapter))
        return [card for _, card in results[:max_hits]]

    def _card_to_content(self, card: ChapterCard) -> str:
        parts = [card.summary, card.goal, card.conflict, card.result]
        content = " ".join(p for p in parts if p).strip()
        return re.sub(r"\s+", " ", content)[:200]

    def to_payload(self, hits: list[RecallHit]) -> Dict[str, Any]:
        mode = "semantic_hybrid"
        if self._config.hybrid_enabled and any("bm25" in h.source for h in hits):
            mode = "semantic_hybrid+bm25_rrf"
        return {
            "invoked": True,
            "mode": mode,
            "reason": "ok" if hits else "no_hit",
            "intent": "continuity_memory",
            "needs_graph": False,
            "center_entities": list(
                set(
                    e
                    for h in hits
                    for e in h.involved_entities
                )
            )[:10],
            "hits": [
                {
                    "chapter": h.chapter,
                    "scene_index": 0,
                    "score": round(h.score, 6),
                    "source": h.source,
                    "source_file": "",
                    "content": h.content[:180],
                }
                for h in hits
            ],
        }

    def recall_to_payload(
        self,
        query: str,
        chapter_num: int,
        scene_entities: list[str] | None = None,
    ) -> Dict[str, Any]:
        hits = self.recall(query, chapter_num, scene_entities)
        payload = self.to_payload(hits)
        payload["query"] = query
        return payload
