"""Reporter: SQLite → dual-view markdown."""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ink_writer.debug.config import DebugConfig

_SINCE_RE = re.compile(r"^(\d+)([hdwm])$")


def _parse_since(since: str) -> datetime:
    m = _SINCE_RE.match(since)
    if not m:
        return datetime.now(timezone.utc) - timedelta(days=1)
    n = int(m.group(1))
    unit = m.group(2)
    delta = {"h": timedelta(hours=n), "d": timedelta(days=n),
             "w": timedelta(weeks=n), "m": timedelta(days=30 * n)}[unit]
    return datetime.now(timezone.utc) - delta


class Reporter:
    def __init__(self, config: DebugConfig) -> None:
        self.config = config

    def _db(self) -> Path:
        return self.config.base_path() / "debug.db"

    def render(self, *, since: str, run_id: str | None, severity: str) -> str:
        db = self._db()
        if not db.exists():
            return "# Debug Report\n\n无数据（数据库不存在）。\n"

        from ink_writer.debug.config import SEVERITY_RANK
        min_rank = SEVERITY_RANK.get(severity, 0)

        cutoff_iso = _parse_since(since).isoformat()
        sql = "SELECT ts, run_id, skill, step, kind, severity, message FROM incidents WHERE ts >= ?"
        params: list = [cutoff_iso]
        if run_id:
            sql += " AND run_id = ?"
            params.append(run_id)

        conn = sqlite3.connect(db)
        rows = list(conn.execute(sql, params))
        conn.close()

        rows = [r for r in rows if SEVERITY_RANK.get(r[5], 0) >= min_rank]
        if not rows:
            return f"# Debug Report (since {since})\n\n无数据。\n"

        # View 1: skill × kind × severity counts
        agg = defaultdict(lambda: {"count": 0, "latest": ""})
        for ts, _rid, skill, _step, kind, sev, _msg in rows:
            key = (skill, kind, sev)
            agg[key]["count"] += 1
            if ts > agg[key]["latest"]:
                agg[key]["latest"] = ts

        view1_lines = [
            "## 视图 1：按发生位置（skill × kind × severity）",
            "",
            "| skill | kind | severity | count | latest |",
            "|---|---|---|---|---|",
        ]
        for (skill, kind, sev), info in sorted(agg.items(), key=lambda kv: -kv[1]["count"]):
            view1_lines.append(f"| {skill} | {kind} | {sev} | {info['count']} | {info['latest']} |")

        # View 2: rule-based root cause grouping by step
        step_groups: dict[str, list[tuple[str, int]]] = defaultdict(list)
        kind_counts: dict[tuple[str, str], int] = defaultdict(int)
        for _ts, _rid, _skill, step, kind, _sev, _msg in rows:
            kind_counts[(step or "", kind)] += 1
        for (step, kind), n in kind_counts.items():
            step_groups[step or "_unknown"].append((kind, n))

        view2_lines = ["## 视图 2：按疑似根因（按 step 归并）", ""]
        for step, kinds in sorted(step_groups.items()):
            total = sum(n for _, n in kinds)
            view2_lines.append(f"### 根因组「{step}」共 {total} 次")
            for kind, n in sorted(kinds, key=lambda kv: -kv[1]):
                view2_lines.append(f"- {kind} × {n}")
            view2_lines.append("")

        header = f"# Debug Report (since {since}{' run='+run_id if run_id else ''})\n"
        return header + "\n" + "\n".join(view1_lines) + "\n\n" + "\n".join(view2_lines)
