"""Tests for EmbeddingClient: batching + exponential backoff retry."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from scripts.corpus_chunking.embedding_client import (
    EmbeddingClient,
    EmbeddingConfig,
    EmbeddingError,
)


@pytest.fixture
def cfg() -> EmbeddingConfig:
    return EmbeddingConfig(
        model="Qwen/Qwen3-Embedding-8B",
        base_url="https://api-inference.modelscope.cn/v1",
        api_key="test-key",
        batch_size=32,
        max_retries=3,
    )


def test_embed_batch_returns_vectors(cfg: EmbeddingConfig) -> None:
    inner = MagicMock()
    inner.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.1] * 4096), MagicMock(embedding=[0.2] * 4096)]
    )
    ec = EmbeddingClient(cfg=cfg, _client=inner)
    vectors = ec.embed_batch(["hello", "world"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 4096


def test_embed_batch_chunks_input_by_batch_size(cfg: EmbeddingConfig) -> None:
    cfg.batch_size = 2
    inner = MagicMock()
    # Every call returns 2 vectors; the client ignores the surplus for the
    # last (size-1) sub-batch because it only extends with ``resp.data``.
    inner.embeddings.create.side_effect = [
        MagicMock(data=[MagicMock(embedding=[0.0] * 4096)] * 2),
        MagicMock(data=[MagicMock(embedding=[0.0] * 4096)] * 2),
        MagicMock(data=[MagicMock(embedding=[0.0] * 4096)]),
    ]
    ec = EmbeddingClient(cfg=cfg, _client=inner)
    vectors = ec.embed_batch(["a", "b", "c", "d", "e"])  # 5 → 3 calls of size 2/2/1
    assert len(vectors) == 5
    assert inner.embeddings.create.call_count == 3


def test_embed_retries_on_429(cfg: EmbeddingConfig) -> None:
    inner = MagicMock()
    err = Exception("429 rate limit")
    ok = MagicMock(data=[MagicMock(embedding=[0.0] * 4096)])
    inner.embeddings.create.side_effect = [err, err, ok]
    ec = EmbeddingClient(cfg=cfg, _client=inner)
    vectors = ec.embed_batch(["x"], _sleep=lambda _: None)
    assert len(vectors) == 1
    assert inner.embeddings.create.call_count == 3


def test_embed_raises_after_max_retries(cfg: EmbeddingConfig) -> None:
    inner = MagicMock()
    err = Exception("permanent")
    inner.embeddings.create.side_effect = [err, err, err, err]
    ec = EmbeddingClient(cfg=cfg, _client=inner)
    with pytest.raises(EmbeddingError):
        ec.embed_batch(["x"], _sleep=lambda _: None)
    # max_retries=3 → 4 attempts total (initial + 3 retries)
    assert inner.embeddings.create.call_count == 4
