"""Inverted sqlite index over the YAML case library.

The authoritative source of truth is the YAML files on disk
(``CaseStore``). This module keeps a sidecar sqlite file with five tables
(``cases`` + four inverted lists) purely as an *accelerator*: ``build`` is
destructive (DROP + CREATE) so a rebuild from YAML always produces a
deterministic index regardless of prior state.

Query helpers return ``case_id`` lists sorted ascending so callers can
compose results by set operations without re-sorting.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ink_writer.case_library.store import CaseStore


class CaseIndex:
    """Sidecar sqlite index built by iterating a ``CaseStore``."""

    def __init__(self, sqlite_path: Path) -> None:
        self.sqlite_path = Path(sqlite_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.sqlite_path)

    def build(self, store: CaseStore) -> int:
        """DROP + CREATE the five tables and reinsert every case.

        Returns the number of cases indexed. Repeated calls are idempotent
        by construction (DROP happens first).
        """
        indexed = 0
        with self._connect() as conn:
            cur = conn.cursor()
            for table in (
                "case_tags",
                "case_layers",
                "case_genres",
                "case_chapters",
                "cases",
            ):
                cur.execute(f"DROP TABLE IF EXISTS {table}")
            cur.executescript(
                """
                CREATE TABLE cases (
                    case_id  TEXT PRIMARY KEY,
                    status   TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    domain   TEXT NOT NULL
                );
                CREATE INDEX idx_cases_status   ON cases(status);
                CREATE INDEX idx_cases_severity ON cases(severity);
                CREATE INDEX idx_cases_domain   ON cases(domain);

                CREATE TABLE case_tags (
                    case_id TEXT NOT NULL,
                    tag     TEXT NOT NULL
                );
                CREATE INDEX idx_case_tags_tag ON case_tags(tag);

                CREATE TABLE case_layers (
                    case_id TEXT NOT NULL,
                    layer   TEXT NOT NULL
                );
                CREATE INDEX idx_case_layers_layer ON case_layers(layer);

                CREATE TABLE case_genres (
                    case_id TEXT NOT NULL,
                    genre   TEXT NOT NULL
                );
                CREATE INDEX idx_case_genres_genre ON case_genres(genre);

                CREATE TABLE case_chapters (
                    case_id TEXT NOT NULL,
                    chapter TEXT NOT NULL
                );
                CREATE INDEX idx_case_chapters_chapter ON case_chapters(chapter);
                """
            )
            for case in store.iter_cases():
                cur.execute(
                    "INSERT INTO cases (case_id, status, severity, domain) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        case.case_id,
                        case.status.value,
                        case.severity.value,
                        case.domain.value,
                    ),
                )
                cur.executemany(
                    "INSERT INTO case_tags (case_id, tag) VALUES (?, ?)",
                    [(case.case_id, tag) for tag in case.tags],
                )
                cur.executemany(
                    "INSERT INTO case_layers (case_id, layer) VALUES (?, ?)",
                    [(case.case_id, layer.value) for layer in case.layer],
                )
                cur.executemany(
                    "INSERT INTO case_genres (case_id, genre) VALUES (?, ?)",
                    [(case.case_id, genre) for genre in case.scope.genre],
                )
                cur.executemany(
                    "INSERT INTO case_chapters (case_id, chapter) VALUES (?, ?)",
                    [(case.case_id, chapter) for chapter in case.scope.chapter],
                )
                indexed += 1
            conn.commit()
        return indexed

    def _select_sorted(self, sql: str, *params: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return sorted({row[0] for row in rows})

    def query_by_tag(self, tag: str) -> list[str]:
        return self._select_sorted(
            "SELECT case_id FROM case_tags WHERE tag = ?", tag
        )

    def query_by_layer(self, layer: str) -> list[str]:
        return self._select_sorted(
            "SELECT case_id FROM case_layers WHERE layer = ?", layer
        )

    def query_by_genre(self, genre: str) -> list[str]:
        return self._select_sorted(
            "SELECT case_id FROM case_genres WHERE genre = ?", genre
        )

    def query_by_chapter(self, chapter: str) -> list[str]:
        return self._select_sorted(
            "SELECT case_id FROM case_chapters WHERE chapter = ?", chapter
        )

    def query_by_status(self, status: str) -> list[str]:
        return self._select_sorted(
            "SELECT case_id FROM cases WHERE status = ?", status
        )
