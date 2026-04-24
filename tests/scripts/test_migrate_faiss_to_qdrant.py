"""Tests for US-013 FAISS -> Qdrant migration script."""
from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np
import pytest
from ink_writer.qdrant.client import QdrantConfig, get_client_from_config
from ink_writer.qdrant.payload_schema import CollectionSpec
from scripts.qdrant.migrate_faiss_to_qdrant import (
    MigrationReport,
    migrate_faiss_index,
)


@pytest.fixture
def fake_faiss_dir(tmp_path: Path):
    dim = 8
    n = 5
    rng = np.random.default_rng(seed=42)
    vectors = rng.random((n, dim)).astype(np.float32)
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    faiss.write_index(index, str(tmp_path / "index.faiss"))

    metadata = [
        {"id": f"R-{i:03d}", "category": "opening", "text": f"rule {i}"}
        for i in range(n)
    ]
    with open(tmp_path / "metadata.jsonl", "w", encoding="utf-8") as fp:
        for row in metadata:
            fp.write(json.dumps(row, ensure_ascii=False))
            fp.write("\n")
    return tmp_path, dim, vectors, metadata


def test_migration_uploads_all_vectors(fake_faiss_dir) -> None:
    src_dir, dim, _vectors, metadata = fake_faiss_dir
    spec = CollectionSpec(
        name="test_migration",
        vector_size=dim,
        indexed_payload_fields={"category": "keyword"},
    )
    client = get_client_from_config(QdrantConfig(memory=True))
    report = migrate_faiss_index(
        client=client,
        spec=spec,
        faiss_index_path=src_dir / "index.faiss",
        metadata_jsonl=src_dir / "metadata.jsonl",
    )
    assert isinstance(report, MigrationReport)
    assert report.collection == "test_migration"
    assert report.uploaded == len(metadata)
    assert report.skipped == 0
    info = client.get_collection("test_migration")
    assert info.points_count == len(metadata)


def test_migration_is_idempotent(fake_faiss_dir) -> None:
    src_dir, dim, _vectors, metadata = fake_faiss_dir
    spec = CollectionSpec(
        name="test_migration_idem",
        vector_size=dim,
        indexed_payload_fields={"category": "keyword"},
    )
    client = get_client_from_config(QdrantConfig(memory=True))
    migrate_faiss_index(
        client, spec, src_dir / "index.faiss", src_dir / "metadata.jsonl"
    )
    migrate_faiss_index(
        client, spec, src_dir / "index.faiss", src_dir / "metadata.jsonl"
    )
    info = client.get_collection("test_migration_idem")
    assert info.points_count == len(metadata)
