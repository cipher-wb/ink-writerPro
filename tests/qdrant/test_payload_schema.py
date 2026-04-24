from __future__ import annotations

from ink_writer.qdrant.payload_schema import (
    CORPUS_CHUNKS_SPEC,
    EDITOR_WISDOM_RULES_SPEC,
    ensure_collection,
)
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance


def test_collection_specs_have_expected_names_and_dims() -> None:
    assert EDITOR_WISDOM_RULES_SPEC.name == "editor_wisdom_rules"
    assert EDITOR_WISDOM_RULES_SPEC.vector_size == 4096
    assert EDITOR_WISDOM_RULES_SPEC.distance == Distance.COSINE

    assert CORPUS_CHUNKS_SPEC.name == "corpus_chunks"
    assert CORPUS_CHUNKS_SPEC.vector_size == 4096
    assert CORPUS_CHUNKS_SPEC.distance == Distance.COSINE


def test_corpus_chunks_payload_has_filter_fields() -> None:
    fields = CORPUS_CHUNKS_SPEC.indexed_payload_fields
    assert fields["genre"] == "keyword"
    assert fields["scene_type"] == "keyword"
    assert fields["quality_score"] == "float"
    assert fields["source_type"] == "keyword"
    assert fields["source_book"] == "keyword"
    assert fields["case_ids"] == "keyword"

    wisdom = EDITOR_WISDOM_RULES_SPEC.indexed_payload_fields
    assert wisdom["category"] == "keyword"
    assert wisdom["applies_to"] == "keyword"
    assert wisdom["scoring_dimensions"] == "keyword"


def test_ensure_collection_creates_then_skips(
    in_memory_client: QdrantClient, monkeypatch
) -> None:
    indexed_calls: list[tuple[str, str]] = []
    real_create_payload_index = in_memory_client.create_payload_index

    def _spy(collection_name: str, field_name: str, field_schema, **kwargs):
        indexed_calls.append((collection_name, field_name))
        return real_create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=field_schema,
            **kwargs,
        )

    monkeypatch.setattr(in_memory_client, "create_payload_index", _spy)

    created = ensure_collection(in_memory_client, EDITOR_WISDOM_RULES_SPEC)
    assert created is True
    assert in_memory_client.collection_exists(EDITOR_WISDOM_RULES_SPEC.name)

    indexed_field_names = {field for (_, field) in indexed_calls}
    assert indexed_field_names == set(EDITOR_WISDOM_RULES_SPEC.indexed_payload_fields)

    indexed_calls.clear()
    skipped = ensure_collection(in_memory_client, EDITOR_WISDOM_RULES_SPEC)
    assert skipped is False
    assert indexed_calls == []
