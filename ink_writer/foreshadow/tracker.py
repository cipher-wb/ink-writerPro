"""Foreshadow lifecycle tracker: scan, classify overdue/silent, generate alerts.

.. deprecated:: US-025
    This module is now a transitional shim. New call sites should import from
    :mod:`ink_writer.thread_lifecycle.tracker` (``scan_all``) which unifies the
    foreshadow + plotline scans behind a single entry point. The function
    signatures here remain unchanged for backward compatibility; the module
    will be removed in a future iteration once all callers have migrated.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from ink_writer.foreshadow.config import ForeshadowLifecycleConfig, load_config


@dataclass
class ForeshadowRecord:
    thread_id: str
    title: str
    content: str
    priority: int
    status: str
    planted_chapter: int
    last_touched_chapter: int
    target_payoff_chapter: int | None
    resolved_chapter: int | None


@dataclass
class OverdueInfo:
    record: ForeshadowRecord
    overdue_chapters: int
    severity: str  # "critical" | "high" | "medium"
    grace_used: int


@dataclass
class SilentInfo:
    record: ForeshadowRecord
    silent_chapters: int


@dataclass
class ForeshadowScanResult:
    current_chapter: int
    total_active: int
    overdue: list[OverdueInfo] = field(default_factory=list)
    silent: list[SilentInfo] = field(default_factory=list)
    density_warning: bool = False
    forced_payoffs: list[OverdueInfo] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)


def _load_active_foreshadows(db_path: str | Path) -> list[ForeshadowRecord]:
    """Load all active foreshadows from index.db."""
    db_path = str(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT thread_id, title, content, priority, status, "
            "planted_chapter, last_touched_chapter, target_payoff_chapter, resolved_chapter "
            "FROM plot_thread_registry WHERE status = 'active' "
            "ORDER BY priority DESC, planted_chapter ASC"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    records = []
    for r in rows:
        records.append(ForeshadowRecord(
            thread_id=r["thread_id"],
            title=r["title"] or "",
            content=r["content"] or "",
            priority=r["priority"] or 50,
            status=r["status"],
            planted_chapter=r["planted_chapter"] or 0,
            last_touched_chapter=r["last_touched_chapter"] or 0,
            target_payoff_chapter=r["target_payoff_chapter"],
            resolved_chapter=r["resolved_chapter"],
        ))
    return records


def _classify_overdue(
    record: ForeshadowRecord,
    current_chapter: int,
    config: ForeshadowLifecycleConfig,
) -> OverdueInfo | None:
    """Check if a foreshadow is overdue based on priority-aware grace periods."""
    if record.target_payoff_chapter is None or record.target_payoff_chapter <= 0:
        return None

    rules = config.priority_overdue_rules

    if record.priority >= rules.p0_threshold:
        grace = rules.p0_grace
        severity = "critical"
    elif record.priority >= rules.p1_threshold:
        grace = rules.p1_grace
        severity = "high"
    else:
        grace = rules.p2_grace
        severity = "medium"

    overdue_by = current_chapter - (record.target_payoff_chapter + grace)
    if overdue_by > 0:
        return OverdueInfo(
            record=record,
            overdue_chapters=overdue_by,
            severity=severity,
            grace_used=grace,
        )
    return None


def _classify_silent(
    record: ForeshadowRecord,
    current_chapter: int,
    config: ForeshadowLifecycleConfig,
) -> SilentInfo | None:
    """Check if a foreshadow has been silent too long."""
    silent_for = current_chapter - record.last_touched_chapter
    if silent_for > config.silence_threshold_chapters:
        return SilentInfo(record=record, silent_chapters=silent_for)
    return None


def scan_foreshadows(
    db_path: str | Path,
    current_chapter: int,
    config: ForeshadowLifecycleConfig | None = None,
) -> ForeshadowScanResult:
    """Scan all active foreshadows and classify overdue/silent status."""
    if config is None:
        config = load_config()

    if not config.enabled:
        return ForeshadowScanResult(current_chapter=current_chapter, total_active=0)

    records = _load_active_foreshadows(db_path)
    result = ForeshadowScanResult(
        current_chapter=current_chapter,
        total_active=len(records),
    )

    for rec in records:
        overdue = _classify_overdue(rec, current_chapter, config)
        if overdue:
            result.overdue.append(overdue)

        silent = _classify_silent(rec, current_chapter, config)
        if silent:
            result.silent.append(silent)

    result.overdue.sort(key=lambda o: (-_severity_rank(o.severity), -o.overdue_chapters))

    result.forced_payoffs = result.overdue[:config.max_forced_payoffs_per_chapter]

    if len(records) > config.active_foreshadow_warn_limit:
        result.density_warning = True

    result.alerts = _build_alerts(result, config)
    return result


def _severity_rank(severity: str) -> int:
    return {"critical": 3, "high": 2, "medium": 1}.get(severity, 0)


def _build_alerts(result: ForeshadowScanResult, config: ForeshadowLifecycleConfig) -> list[str]:
    """Build human-readable alert strings for Context Agent Board 7."""
    alerts: list[str] = []

    for od in result.overdue:
        rec = od.record
        alerts.append(
            f"⚠️ 伏笔逾期 [{od.severity}] [{rec.thread_id}] {rec.title}："
            f"目标ch{rec.target_payoff_chapter}, 已逾期{od.overdue_chapters}章"
            f"（宽限{od.grace_used}章已耗尽）。"
            f"{'本章必须安排兑现。' if od in result.forced_payoffs else '建议尽快安排兑现。'}"
        )

    for si in result.silent:
        rec = si.record
        alerts.append(
            f"💤 伏笔沉默 [{rec.thread_id}] {rec.title}："
            f"已{si.silent_chapters}章未推进（上次ch{rec.last_touched_chapter}），"
            f"建议本章推进或提及。"
        )

    if result.density_warning:
        alerts.append(
            f"📊 活跃伏笔数量告警：当前{result.total_active}条"
            f"（阈值{config.active_foreshadow_warn_limit}），考虑加速兑现部分伏笔。"
        )

    return alerts


def build_plan_injection(scan: ForeshadowScanResult, config: ForeshadowLifecycleConfig | None = None) -> dict:
    """Build ink-plan injection payload for forced payoffs.

    Returns dict with:
      - forced_payoffs: list of {thread_id, title, content, priority, severity, overdue_chapters}
      - mode: "force" | "warn"
      - alerts: list of alert strings
    """
    if config is None:
        config = load_config()

    payoffs = []
    for od in scan.forced_payoffs:
        rec = od.record
        payoffs.append({
            "thread_id": rec.thread_id,
            "title": rec.title,
            "content": rec.content,
            "priority": rec.priority,
            "severity": od.severity,
            "overdue_chapters": od.overdue_chapters,
            "target_payoff_chapter": rec.target_payoff_chapter,
        })

    return {
        "forced_payoffs": payoffs,
        "mode": config.plan_injection_mode,
        "alerts": scan.alerts,
        "total_active": scan.total_active,
        "total_overdue": len(scan.overdue),
        "total_silent": len(scan.silent),
    }


def build_heatmap_data(
    db_path: str | Path,
    max_chapter: int,
    bucket_size: int = 10,
) -> list[dict]:
    """Build foreshadow heatmap data bucketed by chapter ranges.

    Returns list of {bucket_start, bucket_end, planted, active, resolved, overdue_risk}.
    """
    db_path = str(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        all_threads = conn.execute(
            "SELECT planted_chapter, last_touched_chapter, target_payoff_chapter, "
            "resolved_chapter, status, priority "
            "FROM plot_thread_registry"
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
            "planted": 0,
            "active": 0,
            "resolved": 0,
            "overdue_risk": 0,
        })

    for t in all_threads:
        planted = t["planted_chapter"] or 0
        resolved = t["resolved_chapter"] or 0
        target = t["target_payoff_chapter"]
        status = t["status"]

        if planted > 0:
            bi = min((planted - 1) // bucket_size, num_buckets - 1)
            buckets[bi]["planted"] += 1

        if resolved > 0:
            bi = min((resolved - 1) // bucket_size, num_buckets - 1)
            buckets[bi]["resolved"] += 1

        if status == "active":
            touch = t["last_touched_chapter"] or planted
            if touch > 0:
                bi = min((touch - 1) // bucket_size, num_buckets - 1)
                buckets[bi]["active"] += 1

            if target and target > 0:
                bi = min((target - 1) // bucket_size, num_buckets - 1)
                buckets[bi]["overdue_risk"] += 1

    return buckets
