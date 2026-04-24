"""Preflight test fixtures.

Re-export the in-memory Qdrant client fixture from the qdrant test package so
preflight tests can use ``in_memory_client`` without duplicating its body.
"""
from __future__ import annotations

from tests.qdrant.conftest import in_memory_client  # noqa: F401
