"""Qdrant test fixtures.

Use the in-memory client (``:memory:``) for unit tests so they never need a
running Qdrant container. Integration tests against a real container are
marked separately and not in this task.
"""
from __future__ import annotations

import pytest
from qdrant_client import QdrantClient


@pytest.fixture
def in_memory_client() -> QdrantClient:
    return QdrantClient(":memory:")
