"""Alerter — per-chapter end-of-run summary + per-batch markdown report trigger."""
from __future__ import annotations

import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ink_writer.debug.config import DebugConfig
from ink_writer.debug.indexer import Indexer
from ink_writer.debug.reporter import Reporter


class Alerter:
    def __init__(self, config: DebugConfig) -> None:
        self.config = config

    def _enabled(self) -> bool:
        return self.config.master_enabled

    def _ensure_synced(self) -> None:
        try:
            Indexer(self.config).sync()
        except Exception:
            pass

    def _query_run_counts(self, run_id: str) -> tuple[Counter, list[str]]:
        db = self.config.base_path() / "debug.db"
        if not db.exists():
            return Counter(), []
        conn = sqlite3.connect(db)
        rows = list(conn.execute(
            "SELECT severity, kind FROM incidents WHERE run_id = ?", (run_id,),
        ))
        conn.close()
        sev = Counter(r[0] for r in rows)
        kinds = [r[1] for r in rows if r[0] in ("warn", "error")]
        return sev, kinds

    def _color_supported(self) -> bool:
        return sys.stdout.isatty() and not os.environ.get("NO_COLOR")

    def chapter_summary(self, *, run_id: str) -> None:
        if not self._enabled() or not self.config.alerts.per_chapter_summary:
            return
        self._ensure_synced()
        sev, kinds = self._query_run_counts(run_id)
        warn_n = sev.get("warn", 0)
        err_n = sev.get("error", 0)
        if warn_n == 0 and err_n == 0:
            line = "📊 debug: 本章 0 warn / 0 error ✅"
            color = "\033[32m"  # green
        elif err_n > 0:
            top = Counter(kinds).most_common(1)[0][0] if kinds else ""
            line = f"📊 debug: 本章 {warn_n} warn / {err_n} error，最高频 kind: {top}"
            color = "\033[31m"  # red
        else:
            top = Counter(kinds).most_common(1)[0][0] if kinds else ""
            line = f"📊 debug: 本章 {warn_n} warn / {err_n} error，最高频 kind: {top}"
            color = "\033[33m"  # yellow
        if self._color_supported():
            print(f"{color}{line}\033[0m")
        else:
            print(line)
        print("   完整报告：/ink-debug-report --since 1d")

    def batch_report(self, *, run_id: str) -> Path | None:
        if not self._enabled() or not self.config.alerts.per_batch_report:
            return None
        self._ensure_synced()
        md = Reporter(self.config).render(since="7d", run_id=run_id, severity="info")
        reports_dir = self.config.base_path() / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = reports_dir / f"{ts}-{run_id}.md"
        path.write_text(md, encoding="utf-8")
        print(f"📋 debug: 批次报告已生成 → {path}")
        return path
