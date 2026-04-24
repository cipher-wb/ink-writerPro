"""Tests for chunk_indexer: Qdrant batch upsert + UUID5 idempotency + failure jsonl."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from scripts.corpus_chunking.chunk_indexer import (
    IndexerConfig,
    _stable_uuid_from_id,
    index_chunks,
)
from scripts.corpus_chunking.models import (
    QualityBreakdown,
    RawChunk,
    SourceType,
    TaggedChunk,
)


def _make_tagged(book: str, chapter: str, n: int) -> list[TaggedChunk]:
    out: list[TaggedChunk] = []
    for i in range(1, n + 1):
        raw = RawChunk(
            chunk_id=f"CHUNK-{book}-{chapter}-§{i}",
            source_book=book,
            source_chapter=chapter,
            char_range=(0, 200),
            text=f"text {i}",
        )
        out.append(
            TaggedChunk(
                raw=raw,
                scene_type="opening",
                genre=["x"],
                tension_level=0.5,
                character_count=1,
                dialogue_ratio=0.0,
                hook_type="",
                borrowable_aspects=[],
                quality_breakdown=QualityBreakdown(0.5, 0.5, 0.5, 0.5),
                source_type=SourceType.BUILTIN,
                ingested_at="2026-04-25",
            )
        )
    return out


def test_index_chunks_upserts_to_qdrant(tmp_path: Path) -> None:
    qdrant = MagicMock()
    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.1] * 4096, [0.2] * 4096]
    cfg = IndexerConfig(qdrant_collection="corpus_chunks", upsert_batch_size=256)
    chunks = _make_tagged("b", "c1", 2)

    n = index_chunks(
        chunks=chunks,
        qdrant_client=qdrant,
        embedder=embedder,
        cfg=cfg,
        metadata_path=tmp_path / "metadata.jsonl",
        unindexed_path=tmp_path / "unindexed.jsonl",
    )

    assert n == 2
    qdrant.upsert.assert_called_once()
    kwargs = qdrant.upsert.call_args.kwargs
    assert kwargs["collection_name"] == "corpus_chunks"
    assert len(kwargs["points"]) == 2


def test_index_chunks_writes_metadata_jsonl(tmp_path: Path) -> None:
    qdrant = MagicMock()
    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.0] * 4096]
    cfg = IndexerConfig(qdrant_collection="corpus_chunks", upsert_batch_size=256)
    chunks = _make_tagged("b", "c", 1)
    metadata = tmp_path / "metadata.jsonl"

    index_chunks(
        chunks=chunks,
        qdrant_client=qdrant,
        embedder=embedder,
        cfg=cfg,
        metadata_path=metadata,
        unindexed_path=tmp_path / "unindexed.jsonl",
    )

    line = metadata.read_text(encoding="utf-8").strip()
    assert "CHUNK-b-c-§1" in line
    parsed = json.loads(line)
    assert parsed["source_book"] == "b"
    assert parsed["scene_type"] == "opening"


def test_index_chunks_records_qdrant_failure_in_unindexed(tmp_path: Path) -> None:
    qdrant = MagicMock()
    qdrant.upsert.side_effect = Exception("qdrant down")
    embedder = MagicMock()
    embedder.embed_batch.return_value = [[0.0] * 4096]
    cfg = IndexerConfig(qdrant_collection="corpus_chunks", upsert_batch_size=256)
    chunks = _make_tagged("b", "c", 1)
    unindexed = tmp_path / "unindexed.jsonl"

    n = index_chunks(
        chunks=chunks,
        qdrant_client=qdrant,
        embedder=embedder,
        cfg=cfg,
        metadata_path=tmp_path / "metadata.jsonl",
        unindexed_path=unindexed,
    )

    assert n == 0
    line = unindexed.read_text(encoding="utf-8").strip()
    assert "CHUNK-b-c-§1" in line
    record = json.loads(line)
    assert record["chunk_id"] == "CHUNK-b-c-§1"
    assert "qdrant down" in record["error"]


def test_index_chunks_uuid5_is_idempotent_id() -> None:
    """Same chunk_id → same Qdrant point id (UUID5 stable)."""
    a = _stable_uuid_from_id("CHUNK-x-c1-§1")
    b = _stable_uuid_from_id("CHUNK-x-c1-§1")
    c = _stable_uuid_from_id("CHUNK-x-c1-§2")
    assert a == b
    assert a != c
