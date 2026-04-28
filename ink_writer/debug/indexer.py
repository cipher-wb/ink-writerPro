"""SQLite indexer: incrementally sync events.jsonl into debug.db."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ink_writer.debug.config import DebugConfig

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  run_id TEXT NOT NULL,
  session_id TEXT,
  project TEXT,
  chapter INTEGER,
  source TEXT NOT NULL,
  skill TEXT NOT NULL,
  step TEXT,
  kind TEXT NOT NULL,
  severity TEXT NOT NULL,
  message TEXT NOT NULL,
  evidence_json TEXT,
  trace_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_ts ON incidents(ts);
CREATE INDEX IF NOT EXISTS idx_kind_sev ON incidents(kind, severity);
CREATE INDEX IF NOT EXISTS idx_run_skill ON incidents(run_id, skill);
CREATE TABLE IF NOT EXISTS indexer_watermark (
  jsonl_path TEXT PRIMARY KEY,
  last_byte_offset INTEGER NOT NULL,
  last_indexed_ts TEXT NOT NULL
);
"""


class Indexer:
    def __init__(self, config: DebugConfig) -> None:
        self.config = config

    def _events_path(self) -> Path:
        return self.config.base_path() / "events.jsonl"

    def _db_path(self) -> Path:
        return self.config.base_path() / "debug.db"

    def _connect(self) -> sqlite3.Connection:
        self.config.base_path().mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path())
        conn.executescript(SCHEMA)
        return conn

    def _watermark(self, conn: sqlite3.Connection, jsonl_path: str) -> int:
        row = conn.execute(
            "SELECT last_byte_offset FROM indexer_watermark WHERE jsonl_path = ?",
            (jsonl_path,),
        ).fetchone()
        return row[0] if row else 0

    def _save_watermark(self, conn: sqlite3.Connection, jsonl_path: str, offset: int, ts: str) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO indexer_watermark (jsonl_path, last_byte_offset, last_indexed_ts) "
            "VALUES (?, ?, ?)",
            (jsonl_path, offset, ts),
        )

    def sync(self) -> int:
        """Read JSONL from watermark to EOF, insert above sqlite_threshold rows. Returns count inserted."""
        conn = self._connect()
        events = self._events_path()
        if not events.exists():
            conn.commit()
            conn.close()
            return 0

        path_str = str(events)
        offset = self._watermark(conn, path_str)
        inserted = 0
        last_ts = ""
        try:
            with events.open("rb") as f:
                f.seek(offset)
                while True:
                    line_bytes = f.readline()
                    if not line_bytes:
                        break
                    line_text = line_bytes.decode("utf-8", errors="replace").strip()
                    if not line_text:
                        continue
                    try:
                        rec = json.loads(line_text)
                    except json.JSONDecodeError:
                        continue
                    sev = rec.get("severity", "info")
                    if not self.config.passes_threshold(sev, "sqlite_threshold"):
                        continue
                    conn.execute(
                        "INSERT INTO incidents (ts, run_id, session_id, project, chapter, "
                        "source, skill, step, kind, severity, message, evidence_json, trace_json) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            rec.get("ts", ""),
                            rec.get("run_id", ""),
                            rec.get("session_id"),
                            rec.get("project"),
                            rec.get("chapter"),
                            rec.get("source", ""),
                            rec.get("skill", ""),
                            rec.get("step"),
                            rec.get("kind", ""),
                            sev,
                            rec.get("message", ""),
                            json.dumps(rec["evidence"], ensure_ascii=False) if rec.get("evidence") else None,
                            json.dumps(rec["trace"], ensure_ascii=False) if rec.get("trace") else None,
                        ),
                    )
                    inserted += 1
                    last_ts = rec.get("ts", last_ts)
                final_offset = f.tell()
            self._save_watermark(conn, path_str, final_offset, last_ts)
            conn.commit()
        finally:
            conn.close()
        return inserted
