"""Thin wrapper around qdrant-client for ink-writer.

Two production modes:
- HTTP (default; talks to a running ``scripts/qdrant/start.sh`` instance)
- ``:memory:`` (used by unit tests; no docker required)
"""
from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from ink_writer.qdrant.errors import QdrantUnreachableError


@dataclass
class QdrantConfig:
    host: str = "127.0.0.1"
    port: int = 6333
    timeout: float = 5.0
    memory: bool = False
    api_key: str | None = None


def get_client_from_config(config: QdrantConfig) -> QdrantClient:
    if config.memory:
        return QdrantClient(":memory:")
    try:
        client = QdrantClient(
            host=config.host,
            port=config.port,
            timeout=config.timeout,
            api_key=config.api_key,
        )
        client.get_collections()
        return client
    except (ResponseHandlingException, UnexpectedResponse, ConnectionError, OSError) as err:
        raise QdrantUnreachableError(
            f"Qdrant at {config.host}:{config.port} unreachable: {err}"
        ) from err


_singleton: QdrantClient | None = None


def get_qdrant_client(config: QdrantConfig | None = None) -> QdrantClient:
    """Return a process-wide singleton client. ``config`` honored on first call."""
    global _singleton
    if _singleton is None:
        _singleton = get_client_from_config(config or QdrantConfig())
    return _singleton


def reset_singleton_for_tests() -> None:
    global _singleton
    _singleton = None
