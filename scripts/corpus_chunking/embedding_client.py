"""Qwen3-Embedding-8B client wrapper with batching + exponential backoff.

Uses OpenAI-compatible client (modelscope endpoint). Errors are retried up to
``max_retries`` with backoff ``[1s, 2s, 4s, ...]``. Raises ``EmbeddingError``
after exhausting retries. Tests inject a ``_client`` MagicMock so the real
openai package is optional at import time.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover — optional dependency
    from openai import OpenAI  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    OpenAI = None  # caller must inject _client in tests


class EmbeddingError(Exception):
    """Raised when embedding API call exhausts retries."""


@dataclass
class EmbeddingConfig:
    model: str
    base_url: str
    api_key: str
    batch_size: int
    max_retries: int


class EmbeddingClient:
    def __init__(self, cfg: EmbeddingConfig, _client: Any | None = None) -> None:
        self.cfg = cfg
        if _client is not None:
            self._client = _client
        else:
            if OpenAI is None:
                raise RuntimeError("openai package not installed")
            self._client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)

    def embed_batch(
        self,
        texts: list[str],
        *,
        _sleep: Callable[[float], None] = time.sleep,
    ) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), self.cfg.batch_size):
            batch = texts[start : start + self.cfg.batch_size]
            out.extend(self._call_with_retry(batch, _sleep=_sleep))
        return out

    def _call_with_retry(
        self,
        texts: list[str],
        *,
        _sleep: Callable[[float], None],
    ) -> list[list[float]]:
        last_err: Exception | None = None
        for attempt in range(self.cfg.max_retries + 1):
            try:
                resp = self._client.embeddings.create(
                    model=self.cfg.model,
                    input=texts,
                )
                return [item.embedding for item in resp.data]
            except Exception as err:  # noqa: BLE001 — broad retry
                last_err = err
                if attempt >= self.cfg.max_retries:
                    break
                _sleep(2 ** attempt)
        raise EmbeddingError(
            f"embedding failed after {self.cfg.max_retries} retries: {last_err}"
        )
