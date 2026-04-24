from __future__ import annotations

import pytest
from scripts.corpus_chunking.models import (
    IngestReport,
    QualityBreakdown,
    RawChunk,
    SourceType,
    TaggedChunk,
)


def test_raw_chunk_serializes() -> None:
    c = RawChunk(
        chunk_id="CHUNK-诡秘之主-ch003-§2",
        source_book="诡秘之主",
        source_chapter="ch003",
        char_range=(1234, 1890),
        text="克莱恩盯着镜子。",
    )
    d = c.to_dict()
    assert d["chunk_id"] == "CHUNK-诡秘之主-ch003-§2"
    assert d["char_range"] == [1234, 1890]


def test_tagged_chunk_round_trip() -> None:
    raw = RawChunk(
        chunk_id="CHUNK-x-ch001-§1",
        source_book="x",
        source_chapter="ch001",
        char_range=(0, 500),
        text="...",
    )
    tagged = TaggedChunk(
        raw=raw,
        scene_type="opening",
        genre=["都市", "现实"],
        tension_level=0.7,
        character_count=2,
        dialogue_ratio=0.4,
        hook_type="introduction",
        borrowable_aspects=["sensory_grounding"],
        quality_breakdown=QualityBreakdown(0.8, 0.7, 0.6, 0.9),
        source_type=SourceType.BUILTIN,
        ingested_at="2026-04-25",
    )
    assert tagged.quality_score == pytest.approx(0.8 * 0.3 + 0.7 * 0.3 + 0.6 * 0.2 + 0.9 * 0.2)
    d = tagged.to_dict()
    assert d["quality_score"] == pytest.approx(tagged.quality_score)
    assert d["genre"] == ["都市", "现实"]


def test_ingest_report_aggregates() -> None:
    r = IngestReport()
    r.chunks_raw += 5
    r.chunks_tagged += 4
    r.chunks_indexed += 4
    r.failures.append(("ch003", "scene_segmenter JSON parse"))
    assert r.success_rate == 0.8
