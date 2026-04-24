"""Shared fixtures for corpus_chunking tests."""
from __future__ import annotations

import pytest
from scripts.corpus_chunking.models import (
    QualityBreakdown,
    RawChunk,
    SourceType,
    TaggedChunk,
)


@pytest.fixture
def sample_chapter_text() -> str:
    return "克莱恩盯着镜子。他不确定眼前的人是谁。" * 50  # ≈ 800 字


@pytest.fixture
def sample_raw_chunk() -> RawChunk:
    return RawChunk(
        chunk_id="CHUNK-诡秘之主-ch003-§1",
        source_book="诡秘之主",
        source_chapter="ch003",
        char_range=(0, 600),
        text="克莱恩盯着镜子。" * 30,
    )


@pytest.fixture
def sample_tagged_chunk(sample_raw_chunk: RawChunk) -> TaggedChunk:
    return TaggedChunk(
        raw=sample_raw_chunk,
        scene_type="opening",
        genre=["异世大陆", "玄幻"],
        tension_level=0.85,
        character_count=1,
        dialogue_ratio=0.0,
        hook_type="identity_reveal",
        borrowable_aspects=["psychological_buffer"],
        quality_breakdown=QualityBreakdown(0.95, 0.90, 0.92, 0.90),
        source_type=SourceType.BUILTIN,
        ingested_at="2026-04-25",
    )
