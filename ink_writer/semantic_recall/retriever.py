"""Hybrid chapter retriever: semantic Top-K ∪ entity-forced ∪ recent-N."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

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
        for card, sim in semantic_hits:
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
        return {
            "invoked": True,
            "mode": "semantic_hybrid",
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
