"""Cache metrics tracking: records cache_creation_input_tokens and
cache_read_input_tokens from Anthropic API responses to measure hit rate.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator, Optional


@dataclass
class CacheMetrics:
    total_calls: int = 0
    total_input_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def cache_hit_rate(self) -> float:
        total_cache = self.cache_creation_tokens + self.cache_read_tokens
        if total_cache == 0:
            return 0.0
        return self.cache_read_tokens / total_cache

    @property
    def token_savings_pct(self) -> float:
        if self.total_input_tokens == 0:
            return 0.0
        return (self.cache_read_tokens / self.total_input_tokens) * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_hit_rate": round(self.cache_hit_rate, 4),
            "token_savings_pct": round(self.token_savings_pct, 2),
        }


class CacheMetricsTracker:
    """Persistent cache metrics tracker backed by SQLite."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or Path(".ink/cache_metrics.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                agent TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
                cache_read_tokens INTEGER NOT NULL DEFAULT 0,
                chapter INTEGER DEFAULT NULL
            )
        """)
        conn.commit()
        conn.close()

    @contextmanager
    def _get_conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record(
        self,
        agent: str,
        model: str,
        response_usage: dict[str, Any],
        chapter: Optional[int] = None,
    ) -> None:
        """Record cache metrics from an Anthropic API response's usage dict."""
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO cache_events
                   (timestamp, agent, model, input_tokens, output_tokens,
                    cache_creation_tokens, cache_read_tokens, chapter)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    time.time(),
                    agent,
                    model,
                    response_usage.get("input_tokens", 0),
                    response_usage.get("output_tokens", 0),
                    response_usage.get("cache_creation_input_tokens", 0),
                    response_usage.get("cache_read_input_tokens", 0),
                    chapter,
                ),
            )

    def get_metrics(
        self, agent: Optional[str] = None, last_n: Optional[int] = None
    ) -> CacheMetrics:
        """Aggregate cache metrics, optionally filtered by agent or last N calls."""
        with self._get_conn() as conn:
            query = "SELECT input_tokens, cache_creation_tokens, cache_read_tokens FROM cache_events"
            params: list[Any] = []
            conditions = []

            if agent:
                conditions.append("agent = ?")
                params.append(agent)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY id DESC"

            if last_n:
                query += " LIMIT ?"
                params.append(last_n)

            rows = conn.execute(query, params).fetchall()

        metrics = CacheMetrics()
        metrics.total_calls = len(rows)
        for input_t, creation_t, read_t in rows:
            metrics.total_input_tokens += input_t
            metrics.cache_creation_tokens += creation_t
            metrics.cache_read_tokens += read_t

        return metrics

    def get_report(self, last_n: int = 20) -> dict[str, Any]:
        """Generate a cache performance report."""
        overall = self.get_metrics(last_n=last_n)
        with self._get_conn() as conn:
            agents = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT agent FROM cache_events"
                ).fetchall()
            ]
        per_agent = {a: self.get_metrics(agent=a, last_n=last_n).to_dict() for a in agents}
        return {
            "overall": overall.to_dict(),
            "per_agent": per_agent,
            "window": last_n,
        }
