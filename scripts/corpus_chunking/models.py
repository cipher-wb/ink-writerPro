"""Corpus chunking dataclasses.

RawChunk: scene_segmenter 输出。
TaggedChunk: chunk_tagger 输出（含 raw + 7 个新字段 + 4 维 quality_breakdown）。
QualityBreakdown: tension/originality/language_density/readability 4 维度，加权
                  得 quality_score（spec §3.5 config 中的权重，默认 30/30/20/20）。
IngestReport: 一次 ingest 跑的统计聚合。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SourceType(StrEnum):
    BUILTIN = "builtin"
    USER = "user"


@dataclass
class QualityBreakdown:
    tension: float
    originality: float
    language_density: float
    readability: float

    def weighted_score(
        self,
        weights: tuple[float, float, float, float] = (0.3, 0.3, 0.2, 0.2),
    ) -> float:
        wt, wo, wl, wr = weights
        return (
            self.tension * wt
            + self.originality * wo
            + self.language_density * wl
            + self.readability * wr
        )


@dataclass
class RawChunk:
    chunk_id: str
    source_book: str
    source_chapter: str
    char_range: tuple[int, int]
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source_book": self.source_book,
            "source_chapter": self.source_chapter,
            "char_range": list(self.char_range),
            "text": self.text,
        }


@dataclass
class TaggedChunk:
    raw: RawChunk
    scene_type: str
    genre: list[str]
    tension_level: float
    character_count: int
    dialogue_ratio: float
    hook_type: str
    borrowable_aspects: list[str]
    quality_breakdown: QualityBreakdown
    source_type: SourceType
    ingested_at: str  # ISO date
    quality_weights: tuple[float, float, float, float] = (0.3, 0.3, 0.2, 0.2)

    @property
    def quality_score(self) -> float:
        return self.quality_breakdown.weighted_score(self.quality_weights)

    def to_dict(self) -> dict[str, Any]:
        d = self.raw.to_dict()
        d.update({
            "scene_type": self.scene_type,
            "genre": list(self.genre),
            "tension_level": self.tension_level,
            "character_count": self.character_count,
            "dialogue_ratio": self.dialogue_ratio,
            "hook_type": self.hook_type,
            "borrowable_aspects": list(self.borrowable_aspects),
            "quality_score": self.quality_score,
            "quality_breakdown": {
                "tension": self.quality_breakdown.tension,
                "originality": self.quality_breakdown.originality,
                "language_density": self.quality_breakdown.language_density,
                "readability": self.quality_breakdown.readability,
            },
            "source_type": self.source_type.value,
            "ingested_at": self.ingested_at,
        })
        return d


@dataclass
class IngestReport:
    chunks_raw: int = 0
    chunks_tagged: int = 0
    chunks_indexed: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.chunks_raw == 0:
            return 0.0
        return self.chunks_indexed / self.chunks_raw
