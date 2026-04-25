"""Qdrant collection + payload-index specifications for ink-writer.

Freezes the production collection names, vector dimensions and payload filter
fields so that the M2 chunker pipeline and the FAISS -> Qdrant migration script
target identical schemas.

Two production collections:

- ``editor_wisdom_rules`` — editor rules embedded for rule retrieval.
- ``corpus_chunks`` — scene-level paragraph chunks from 30 reference books.

Both use ZhipuAI GLM ``embedding-3`` (dim=2048) with cosine distance.

Vector dim history:
- v23 spec §8 originally assumed Qwen3-Embedding-8B (dim=4096) via modelscope.
- Real ``~/.claude/ink-writer/.env`` ships ZhipuAI ``embedding-3`` instead.
- M2 (2026-04-24) switched to dim=2048 to match the actual EMBED_API_KEY.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PayloadSchemaType, VectorParams

_FIELD_TYPE_MAP: Mapping[str, PayloadSchemaType] = MappingProxyType(
    {
        "keyword": PayloadSchemaType.KEYWORD,
        "float": PayloadSchemaType.FLOAT,
        "integer": PayloadSchemaType.INTEGER,
        "bool": PayloadSchemaType.BOOL,
    }
)


@dataclass(frozen=True)
class CollectionSpec:
    """Frozen description of one Qdrant collection.

    ``indexed_payload_fields`` maps payload key -> string tag from
    ``_FIELD_TYPE_MAP`` (``"keyword"`` / ``"float"`` / ``"integer"`` / ``"bool"``).
    """

    name: str
    vector_size: int
    indexed_payload_fields: Mapping[str, str] = field(default_factory=dict)
    distance: Distance = Distance.COSINE


EDITOR_WISDOM_RULES_SPEC = CollectionSpec(
    name="editor_wisdom_rules",
    vector_size=2048,  # ZhipuAI GLM embedding-3 (M2 修订；spec §8 原假设 Qwen3 4096)
    indexed_payload_fields=MappingProxyType(
        {
            "category": "keyword",
            "applies_to": "keyword",
            "scoring_dimensions": "keyword",
        }
    ),
)


CORPUS_CHUNKS_SPEC = CollectionSpec(
    name="corpus_chunks",
    vector_size=2048,  # ZhipuAI GLM embedding-3 (M2 修订；spec §8 原假设 Qwen3 4096)
    indexed_payload_fields=MappingProxyType(
        {
            "genre": "keyword",
            "scene_type": "keyword",
            "quality_score": "float",
            "source_type": "keyword",
            "source_book": "keyword",
            "case_ids": "keyword",
        }
    ),
)


def ensure_collection(client: QdrantClient, spec: CollectionSpec) -> bool:
    """Create ``spec`` on ``client`` if missing; idempotent.

    Returns ``True`` if the collection was created (including payload indexes),
    ``False`` if it already existed and nothing was done.
    """
    if client.collection_exists(spec.name):
        return False
    client.create_collection(
        collection_name=spec.name,
        vectors_config=VectorParams(size=spec.vector_size, distance=spec.distance),
    )
    for field_name, type_tag in spec.indexed_payload_fields.items():
        client.create_payload_index(
            collection_name=spec.name,
            field_name=field_name,
            field_schema=_FIELD_TYPE_MAP[type_tag],
        )
    return True
