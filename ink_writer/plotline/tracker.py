"""Plotline lifecycle tracker: scan, detect inactive lines, generate alerts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from ink_writer.plotline.config import PlotlineLifecycleConfig, load_config


VALID_LINE_TYPES = ("main", "sub", "dark")


@dataclass
class PlotlineRecord:
    thread_id: str
    title: str
    content: str
    line_type: str  # "main" | "sub" | "dark"
    status: str
    planted_chapter: int
    last_touched_chapter: int
    resolved_chapter: int | None


@dataclass
class InactiveInfo:
    record: PlotlineRecord
    gap_chapters: int
    max_gap: int
    severity: str  # "critical" | "high" | "medium"


@dataclass
class PlotlineScanResult:
    current_chapter: int
    total_active: int
    inactive: list[InactiveInfo] = field(default_factory=list)
    density_warning: bool = False
    forced_advances: list[InactiveInfo] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)


def _load_active_plotlines(db_path: str | Path) -> list[PlotlineRecord]:
    """Load all active plotlines from index.db."""
    db_path = str(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT thread_id, title, content, status, "
            "planted_chapter, last_touched_chapter, resolved_chapter, payload_json "
            "FROM plot_thread_registry WHERE status = 'active' AND thread_type = 'plotline' "
            "ORDER BY priority DESC, planted_chapter ASC"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    records = []
    for r in rows:
        payload = {}
        if r["payload_json"]:
            try:
                payload = json.loads(r["payload_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        line_type = payload.get("line_type", "sub")
        if line_type not in VALID_LINE_TYPES:
            line_type = "sub"

        records.append(PlotlineRecord(
            thread_id=r["thread_id"],
            title=r["title"] or "",
            content=r["content"] or "",
            line_type=line_type,
            status=r["status"],
            planted_chapter=r["planted_chapter"] or 0,
            last_touched_chapter=r["last_touched_chapter"] or 0,
            resolved_chapter=r["resolved_chapter"],
        ))
    return records


def _get_max_gap(line_type: str, config: PlotlineLifecycleConfig) -> int:
    rules = config.inactivity_rules
    if line_type == "main":
        return rules.main_max_gap
    elif line_type == "dark":
        return rules.dark_max_gap
    return rules.sub_max_gap


def _severity_for_line_type(line_type: str) -> str:
    if line_type == "main":
        return "critical"
    elif line_type == "sub":
        return "high"
    return "medium"


def _classify_inactive(
    record: PlotlineRecord,
    current_chapter: int,
    config: PlotlineLifecycleConfig,
) -> InactiveInfo | None:
    """Check if a plotline has been inactive beyond its allowed gap."""
    gap = current_chapter - record.last_touched_chapter
    max_gap = _get_max_gap(record.line_type, config)

    if gap > max_gap:
        return InactiveInfo(
            record=record,
            gap_chapters=gap,
            max_gap=max_gap,
            severity=_severity_for_line_type(record.line_type),
        )
    return None


def _severity_rank(severity: str) -> int:
    return {"critical": 3, "high": 2, "medium": 1}.get(severity, 0)


def scan_plotlines(
    db_path: str | Path,
    current_chapter: int,
    config: PlotlineLifecycleConfig | None = None,
) -> PlotlineScanResult:
    """Scan all active plotlines and detect inactivity."""
    if config is None:
        config = load_config()

    if not config.enabled:
        return PlotlineScanResult(current_chapter=current_chapter, total_active=0)

    records = _load_active_plotlines(db_path)
    result = PlotlineScanResult(
        current_chapter=current_chapter,
        total_active=len(records),
    )

    for rec in records:
        inactive = _classify_inactive(rec, current_chapter, config)
        if inactive:
            result.inactive.append(inactive)

    result.inactive.sort(key=lambda i: (-_severity_rank(i.severity), -i.gap_chapters))

    result.forced_advances = result.inactive[:config.max_forced_advances_per_chapter]

    if len(records) > config.active_plotline_warn_limit:
        result.density_warning = True

    result.alerts = _build_alerts(result, config)
    return result


def _build_alerts(result: PlotlineScanResult, config: PlotlineLifecycleConfig) -> list[str]:
    """Build human-readable alert strings."""
    alerts: list[str] = []
    type_labels = {"main": "主线", "sub": "支线", "dark": "暗线"}

    for ia in result.inactive:
        rec = ia.record
        label = type_labels.get(rec.line_type, "支线")
        forced = ia in result.forced_advances
        alerts.append(
            f"⚠️ {label}断更 [{ia.severity}] [{rec.thread_id}] {rec.title}："
            f"已{ia.gap_chapters}章未推进（上次ch{rec.last_touched_chapter}，"
            f"阈值{ia.max_gap}章）。"
            f"{'本章必须安排推进。' if forced else '建议尽快安排推进。'}"
        )

    if result.density_warning:
        alerts.append(
            f"📊 活跃线程数量告警：当前{result.total_active}条"
            f"（阈值{config.active_plotline_warn_limit}），考虑收束部分支线/暗线。"
        )

    return alerts


def build_plan_injection(scan: PlotlineScanResult, config: PlotlineLifecycleConfig | None = None) -> dict:
    """Build ink-plan injection payload for forced plotline advances."""
    if config is None:
        config = load_config()

    type_labels = {"main": "主线", "sub": "支线", "dark": "暗线"}
    advances = []
    for ia in scan.forced_advances:
        rec = ia.record
        advances.append({
            "thread_id": rec.thread_id,
            "title": rec.title,
            "content": rec.content,
            "line_type": rec.line_type,
            "line_type_label": type_labels.get(rec.line_type, "支线"),
            "severity": ia.severity,
            "gap_chapters": ia.gap_chapters,
            "max_gap": ia.max_gap,
            "last_touched_chapter": rec.last_touched_chapter,
        })

    return {
        "forced_advances": advances,
        "mode": config.plan_injection_mode,
        "alerts": scan.alerts,
        "total_active": scan.total_active,
        "total_inactive": len(scan.inactive),
    }


def build_plotline_heatmap(
    db_path: str | Path,
    max_chapter: int,
    bucket_size: int = 10,
) -> list[dict]:
    """Build plotline activity heatmap bucketed by chapter ranges."""
    db_path = str(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        all_plotlines = conn.execute(
            "SELECT planted_chapter, last_touched_chapter, resolved_chapter, "
            "status, payload_json "
            "FROM plot_thread_registry WHERE thread_type = 'plotline'"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    if max_chapter <= 0:
        return []

    num_buckets = (max_chapter + bucket_size - 1) // bucket_size
    buckets: list[dict] = []
    for i in range(num_buckets):
        start = i * bucket_size + 1
        end = min((i + 1) * bucket_size, max_chapter)
        buckets.append({
            "bucket_start": start,
            "bucket_end": end,
            "main_active": 0,
            "sub_active": 0,
            "dark_active": 0,
            "resolved": 0,
        })

    for t in all_plotlines:
        payload = {}
        if t["payload_json"]:
            try:
                payload = json.loads(t["payload_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        line_type = payload.get("line_type", "sub")
        planted = t["planted_chapter"] or 0
        resolved = t["resolved_chapter"] or 0
        status = t["status"]

        if resolved > 0:
            bi = min((resolved - 1) // bucket_size, num_buckets - 1)
            buckets[bi]["resolved"] += 1

        if status == "active":
            touch = t["last_touched_chapter"] or planted
            if touch > 0:
                bi = min((touch - 1) // bucket_size, num_buckets - 1)
                key = f"{line_type}_active"
                if key in buckets[bi]:
                    buckets[bi][key] += 1

    return buckets
