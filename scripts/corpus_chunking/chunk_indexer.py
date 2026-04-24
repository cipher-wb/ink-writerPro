"""chunk_indexer: TaggedChunk 列表 → 向量化 → Qdrant batch upsert。

UUID5(NAMESPACE_URL, chunk_id) 作为 Qdrant point id，保证重跑相同 chunk_id
覆盖同一 point（spec §3.3 沿用 M1 US-013 pattern）。

失败处理：Qdrant upsert 失败 → 失败 batch 的 chunks 写入 ``unindexed_path``
（jsonl，单行 ``{chunk_id, error}``），不阻断后续 batches。成功 indexed 的
chunks 同时 append 到 ``metadata_path``（jsonl 备份）。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.corpus_chunking.models import TaggedChunk


@dataclass
class IndexerConfig:
    qdrant_collection: str
    upsert_batch_size: int


def _stable_uuid_from_id(chunk_id: str) -> str:
    """Deterministic UUID5 so repeated runs upsert the same point id."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def _build_point(chunk: TaggedChunk, vector: list[float]) -> Any:
    """Return a qdrant_client PointStruct (lazy import for test environments)."""
    from qdrant_client.http import models as rest
    return rest.PointStruct(
        id=_stable_uuid_from_id(chunk.raw.chunk_id),
        vector=vector,
        payload=chunk.to_dict(),
    )


def index_chunks(
    *,
    chunks: list[TaggedChunk],
    qdrant_client: Any,
    embedder: Any,
    cfg: IndexerConfig,
    metadata_path: Path,
    unindexed_path: Path,
) -> int:
    """Embed + upsert chunks; returns number of chunks successfully indexed."""
    indexed_count = 0
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    unindexed_path.parent.mkdir(parents=True, exist_ok=True)

    for start in range(0, len(chunks), cfg.upsert_batch_size):
        batch = chunks[start : start + cfg.upsert_batch_size]
        texts = [c.raw.text for c in batch]
        try:
            vectors = embedder.embed_batch(texts)
            points = [_build_point(c, v) for c, v in zip(batch, vectors, strict=False)]
            qdrant_client.upsert(
                collection_name=cfg.qdrant_collection,
                points=points,
            )
            indexed_count += len(batch)
            with open(metadata_path, "a", encoding="utf-8") as fp:
                for c in batch:
                    fp.write(json.dumps(c.to_dict(), ensure_ascii=False))
                    fp.write("\n")
        except Exception as err:  # noqa: BLE001 — per-batch failure isolation
            with open(unindexed_path, "a", encoding="utf-8") as fp:
                for c in batch:
                    fp.write(
                        json.dumps(
                            {"chunk_id": c.raw.chunk_id, "error": str(err)},
                            ensure_ascii=False,
                        )
                    )
                    fp.write("\n")
    return indexed_count
