"""Qdrant errors."""
from __future__ import annotations


class QdrantError(Exception):
    """Base class for Qdrant errors."""


class QdrantUnreachableError(QdrantError):
    """Raised when the Qdrant service cannot be reached within the timeout."""
