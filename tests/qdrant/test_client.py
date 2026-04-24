from __future__ import annotations

import pytest
from ink_writer.qdrant.client import QdrantConfig, get_client_from_config
from ink_writer.qdrant.errors import QdrantUnreachableError


def test_in_memory_client_via_helper() -> None:
    config = QdrantConfig(memory=True)
    client = get_client_from_config(config)
    assert client.get_collections().collections == []


def test_unreachable_raises() -> None:
    config = QdrantConfig(host="127.0.0.1", port=1, timeout=0.5)  # port 1 is closed
    with pytest.raises(QdrantUnreachableError):
        get_client_from_config(config)
