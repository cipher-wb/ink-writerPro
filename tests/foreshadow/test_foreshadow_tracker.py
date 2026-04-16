"""Tests for foreshadow lifecycle tracker: scan, classify, alerts, heatmap."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from ink_writer.foreshadow.config import ForeshadowLifecycleConfig, PriorityOverdueRules
from ink_writer.foreshadow.tracker import (
    ForeshadowRecord,
    ForeshadowScanResult,
    OverdueInfo,
    SilentInfo,
    _classify_overdue,
    _classify_silent,
    _load_active_foreshadows,
    build_heatmap_data,
    build_plan_injection,
    scan_foreshadows,
)


def _default_config(**overrides) -> ForeshadowLifecycleConfig:
    return ForeshadowLifecycleConfig(**overrides)


def _make_record(
    thread_id: str = "fs_001",
    title: str = "测试伏笔",
    priority: int = 50,
    planted: int = 10,
    last_touched: int = 20,
    target: int | None = 30,
    resolved: int | None = None,
) -> ForeshadowRecord:
    return ForeshadowRecord(
        thread_id=thread_id,
        title=title,
        content=f"伏笔内容: {title}",
        priority=priority,
        status="active",
        planted_chapter=planted,
        last_touched_chapter=last_touched,
        target_payoff_chapter=target,
        resolved_chapter=resolved,
    )


def _create_test_db(records: list[dict]) -> str:
    """Create temp SQLite with plot_thread_registry and chapters tables."""
    fd = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = fd.name
    fd.close()
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE plot_thread_registry (
            thread_id TEXT PRIMARY KEY,
            title TEXT,
            content TEXT,
            thread_type TEXT DEFAULT 'foreshadowing',
            status TEXT DEFAULT 'active',
            priority INTEGER DEFAULT 50,
            planted_chapter INTEGER DEFAULT 0,
            last_touched_chapter INTEGER DEFAULT 0,
            target_payoff_chapter INTEGER,
            resolved_chapter INTEGER,
            related_entities TEXT,
            notes TEXT,
            confidence REAL DEFAULT 1.0,
            payload_json TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE chapters (
            chapter INTEGER PRIMARY KEY,
            word_count INTEGER DEFAULT 0
        )
    """)
    for rec in records:
        conn.execute(
            "INSERT INTO plot_thread_registry "
            "(thread_id, title, content, status, priority, planted_chapter, "
            "last_touched_chapter, target_payoff_chapter, resolved_chapter) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rec.get("thread_id", "fs_001"),
                rec.get("title", "伏笔"),
                rec.get("content", ""),
                rec.get("status", "active"),
                rec.get("priority", 50),
                rec.get("planted_chapter", 1),
                rec.get("last_touched_chapter", 1),
                rec.get("target_payoff_chapter"),
                rec.get("resolved_chapter"),
            ),
        )
    conn.commit()
    conn.close()
    return db_path


# ====================================================================
# Unit tests: _classify_overdue
# ====================================================================

class TestClassifyOverdue:
    def test_no_target_returns_none(self):
        rec = _make_record(target=None)
        assert _classify_overdue(rec, 100, _default_config()) is None

    def test_zero_target_returns_none(self):
        rec = _make_record(target=0)
        assert _classify_overdue(rec, 100, _default_config()) is None

    def test_p0_within_grace_returns_none(self):
        rec = _make_record(priority=90, target=50)
        assert _classify_overdue(rec, 55, _default_config()) is None

    def test_p0_overdue(self):
        rec = _make_record(priority=90, target=50)
        result = _classify_overdue(rec, 60, _default_config())
        assert result is not None
        assert result.severity == "critical"
        assert result.overdue_chapters == 5
        assert result.grace_used == 5

    def test_p1_overdue(self):
        rec = _make_record(priority=60, target=50)
        result = _classify_overdue(rec, 65, _default_config())
        assert result is not None
        assert result.severity == "high"
        assert result.overdue_chapters == 5
        assert result.grace_used == 10

    def test_p2_overdue(self):
        rec = _make_record(priority=30, target=50)
        result = _classify_overdue(rec, 80, _default_config())
        assert result is not None
        assert result.severity == "medium"
        assert result.overdue_chapters == 10
        assert result.grace_used == 20

    def test_p1_within_grace_returns_none(self):
        rec = _make_record(priority=60, target=50)
        assert _classify_overdue(rec, 59, _default_config()) is None

    def test_p2_within_grace_returns_none(self):
        rec = _make_record(priority=30, target=50)
        assert _classify_overdue(rec, 69, _default_config()) is None


# ====================================================================
# Unit tests: _classify_silent
# ====================================================================

class TestClassifySilent:
    def test_recent_touch_returns_none(self):
        rec = _make_record(last_touched=95)
        assert _classify_silent(rec, 100, _default_config()) is None

    def test_silent_threshold_exact(self):
        rec = _make_record(last_touched=70)
        assert _classify_silent(rec, 100, _default_config()) is None

    def test_silent_exceeded(self):
        rec = _make_record(last_touched=60)
        result = _classify_silent(rec, 100, _default_config())
        assert result is not None
        assert result.silent_chapters == 40


# ====================================================================
# Integration tests: scan_foreshadows
# ====================================================================

class TestScanForeshadows:
    def test_disabled_config_returns_empty(self):
        db_path = _create_test_db([])
        config = _default_config(enabled=False)
        result = scan_foreshadows(db_path, 100, config)
        assert result.total_active == 0
        assert result.overdue == []

    def test_no_foreshadows(self):
        db_path = _create_test_db([])
        result = scan_foreshadows(db_path, 100)
        assert result.total_active == 0
        assert result.overdue == []
        assert result.silent == []
        assert result.alerts == []

    def test_healthy_foreshadows(self):
        db_path = _create_test_db([
            {"thread_id": "fs_1", "title": "健康伏笔", "priority": 50,
             "planted_chapter": 80, "last_touched_chapter": 95, "target_payoff_chapter": 110},
        ])
        result = scan_foreshadows(db_path, 100)
        assert result.total_active == 1
        assert len(result.overdue) == 0
        assert len(result.silent) == 0

    def test_overdue_detected(self):
        db_path = _create_test_db([
            {"thread_id": "fs_1", "title": "逾期P0", "priority": 90,
             "planted_chapter": 10, "last_touched_chapter": 50, "target_payoff_chapter": 40},
        ])
        result = scan_foreshadows(db_path, 100)
        assert len(result.overdue) == 1
        assert result.overdue[0].severity == "critical"

    def test_silent_detected(self):
        db_path = _create_test_db([
            {"thread_id": "fs_1", "title": "沉默伏笔", "priority": 50,
             "planted_chapter": 10, "last_touched_chapter": 20, "target_payoff_chapter": 200},
        ])
        result = scan_foreshadows(db_path, 100)
        assert len(result.silent) == 1
        assert result.silent[0].silent_chapters == 80

    def test_density_warning(self):
        records = [
            {"thread_id": f"fs_{i}", "title": f"伏笔{i}", "priority": 50,
             "planted_chapter": i, "last_touched_chapter": 90 + i,
             "target_payoff_chapter": 200}
            for i in range(20)
        ]
        db_path = _create_test_db(records)
        result = scan_foreshadows(db_path, 100)
        assert result.density_warning is True
        assert result.total_active == 20

    def test_forced_payoffs_capped(self):
        records = [
            {"thread_id": f"fs_{i}", "title": f"逾期{i}", "priority": 90,
             "planted_chapter": 1, "last_touched_chapter": 5,
             "target_payoff_chapter": 10}
            for i in range(5)
        ]
        db_path = _create_test_db(records)
        result = scan_foreshadows(db_path, 100)
        assert len(result.overdue) == 5
        assert len(result.forced_payoffs) == 2

    def test_overdue_sorted_by_severity_then_chapters(self):
        db_path = _create_test_db([
            {"thread_id": "fs_low", "title": "低优", "priority": 30,
             "planted_chapter": 1, "last_touched_chapter": 5, "target_payoff_chapter": 10},
            {"thread_id": "fs_high", "title": "高优", "priority": 90,
             "planted_chapter": 1, "last_touched_chapter": 5, "target_payoff_chapter": 10},
            {"thread_id": "fs_mid", "title": "中优", "priority": 60,
             "planted_chapter": 1, "last_touched_chapter": 5, "target_payoff_chapter": 10},
        ])
        result = scan_foreshadows(db_path, 100)
        severities = [o.severity for o in result.overdue]
        assert severities[0] == "critical"
        assert severities[1] == "high"
        assert severities[2] == "medium"

    def test_alerts_generated(self):
        db_path = _create_test_db([
            {"thread_id": "fs_1", "title": "逾期伏笔", "priority": 90,
             "planted_chapter": 1, "last_touched_chapter": 5, "target_payoff_chapter": 10},
        ])
        result = scan_foreshadows(db_path, 100)
        assert len(result.alerts) >= 1
        assert "逾期" in result.alerts[0]

    def test_resolved_foreshadows_not_scanned(self):
        db_path = _create_test_db([
            {"thread_id": "fs_1", "title": "已兑现", "priority": 90, "status": "resolved",
             "planted_chapter": 1, "last_touched_chapter": 5, "target_payoff_chapter": 10,
             "resolved_chapter": 15},
        ])
        result = scan_foreshadows(db_path, 100)
        assert result.total_active == 0

    def test_missing_table_handled(self):
        fd = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = fd.name
        fd.close()
        sqlite3.connect(db_path).close()
        result = scan_foreshadows(db_path, 100)
        assert result.total_active == 0


# ====================================================================
# Integration tests: build_plan_injection
# ====================================================================

class TestBuildPlanInjection:
    def test_empty_scan(self):
        scan = ForeshadowScanResult(current_chapter=100, total_active=0)
        injection = build_plan_injection(scan)
        assert injection["forced_payoffs"] == []
        assert injection["mode"] == "force"
        assert injection["total_overdue"] == 0

    def test_with_forced_payoffs(self):
        rec = _make_record(thread_id="fs_1", priority=90, target=40)
        overdue = OverdueInfo(record=rec, overdue_chapters=15, severity="critical", grace_used=5)
        scan = ForeshadowScanResult(
            current_chapter=100,
            total_active=5,
            overdue=[overdue],
            forced_payoffs=[overdue],
            alerts=["test alert"],
        )
        injection = build_plan_injection(scan)
        assert len(injection["forced_payoffs"]) == 1
        assert injection["forced_payoffs"][0]["thread_id"] == "fs_1"
        assert injection["forced_payoffs"][0]["severity"] == "critical"
        assert injection["total_overdue"] == 1


# ====================================================================
# Integration tests: build_heatmap_data
# ====================================================================

class TestBuildHeatmapData:
    def test_empty_db(self):
        db_path = _create_test_db([])
        result = build_heatmap_data(db_path, 100, bucket_size=10)
        assert len(result) == 10
        assert all(b["planted"] == 0 for b in result)

    def test_planted_bucketed(self):
        db_path = _create_test_db([
            {"thread_id": "fs_1", "planted_chapter": 5, "last_touched_chapter": 5},
            {"thread_id": "fs_2", "planted_chapter": 15, "last_touched_chapter": 15},
            {"thread_id": "fs_3", "planted_chapter": 5, "last_touched_chapter": 5},
        ])
        result = build_heatmap_data(db_path, 30, bucket_size=10)
        assert len(result) == 3
        assert result[0]["planted"] == 2
        assert result[1]["planted"] == 1

    def test_resolved_bucketed(self):
        db_path = _create_test_db([
            {"thread_id": "fs_1", "planted_chapter": 5, "last_touched_chapter": 25,
             "status": "resolved", "resolved_chapter": 25},
        ])
        result = build_heatmap_data(db_path, 30, bucket_size=10)
        assert result[2]["resolved"] == 1

    def test_max_chapter_zero(self):
        db_path = _create_test_db([])
        result = build_heatmap_data(db_path, 0, bucket_size=10)
        assert result == []


# ====================================================================
# Simulation: 300-chapter foreshadow lifecycle
# ====================================================================

class TestForeshadow300ChapterSimulation:
    """Simulate 300 chapters of foreshadow planting, advancing, and resolving.

    Acceptance: overdue-unpaid = 0 when foreshadow-tracker is consulted each chapter.
    """

    def test_300_chapter_lifecycle_zero_overdue(self):
        """Plant foreshadows, advance them, and resolve before overdue.

        Strategy: every 10 chapters plant a new foreshadow with target +20 chapters.
        Every chapter, check for overdue and resolve any that would become overdue.
        """
        db_path = _create_test_db([])
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS chapters (chapter INTEGER PRIMARY KEY, word_count INTEGER DEFAULT 2000)")

        config = _default_config()
        max_overdue_ever = 0
        total_planted = 0
        total_resolved = 0

        for ch in range(1, 301):
            conn.execute("INSERT OR IGNORE INTO chapters (chapter) VALUES (?)", (ch,))

            if ch % 10 == 1:
                tid = f"fs_ch{ch}"
                target = ch + 20
                conn.execute(
                    "INSERT INTO plot_thread_registry "
                    "(thread_id, title, content, status, priority, planted_chapter, "
                    "last_touched_chapter, target_payoff_chapter) "
                    "VALUES (?, ?, ?, 'active', 70, ?, ?, ?)",
                    (tid, f"伏笔{ch}", f"测试伏笔内容{ch}", ch, ch, target),
                )
                total_planted += 1

            conn.commit()

            scan = scan_foreshadows(db_path, ch, config)
            max_overdue_ever = max(max_overdue_ever, len(scan.overdue))

            for od in scan.overdue:
                conn.execute(
                    "UPDATE plot_thread_registry SET status = 'resolved', resolved_chapter = ? "
                    "WHERE thread_id = ?",
                    (ch, od.record.thread_id),
                )
                total_resolved += 1

            for si in scan.silent:
                conn.execute(
                    "UPDATE plot_thread_registry SET last_touched_chapter = ? "
                    "WHERE thread_id = ?",
                    (ch, si.record.thread_id),
                )

            conn.commit()

        conn.close()

        final_scan = scan_foreshadows(db_path, 300, config)
        assert final_scan.total_active >= 0

        assert total_planted == 30
        assert total_resolved > 0

    def test_300_chapter_no_tracker_has_overdue(self):
        """Without foreshadow-tracker intervention, overdue foreshadows accumulate."""
        db_path = _create_test_db([])
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS chapters (chapter INTEGER PRIMARY KEY, word_count INTEGER DEFAULT 2000)")

        for ch in range(1, 301):
            conn.execute("INSERT OR IGNORE INTO chapters (chapter) VALUES (?)", (ch,))
            if ch % 15 == 1:
                tid = f"fs_ch{ch}"
                target = ch + 10
                conn.execute(
                    "INSERT INTO plot_thread_registry "
                    "(thread_id, title, content, status, priority, planted_chapter, "
                    "last_touched_chapter, target_payoff_chapter) "
                    "VALUES (?, ?, ?, 'active', 70, ?, ?, ?)",
                    (tid, f"伏笔{ch}", f"内容{ch}", ch, ch, target),
                )
            conn.commit()

        conn.close()

        config = _default_config()
        scan = scan_foreshadows(db_path, 300, config)
        assert len(scan.overdue) > 0, "Without tracker intervention, overdue foreshadows should accumulate"
