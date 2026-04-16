"""Tests for plotline lifecycle tracker: scan, classify, alerts, heatmap."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from ink_writer.plotline.config import InactivityRules, PlotlineLifecycleConfig
from ink_writer.plotline.tracker import (
    InactiveInfo,
    PlotlineRecord,
    PlotlineScanResult,
    _classify_inactive,
    _get_max_gap,
    _load_active_plotlines,
    _severity_for_line_type,
    build_plan_injection,
    build_plotline_heatmap,
    scan_plotlines,
)


def _default_config(**overrides) -> PlotlineLifecycleConfig:
    return PlotlineLifecycleConfig(**overrides)


def _make_record(
    thread_id: str = "pl_main",
    title: str = "主线测试",
    line_type: str = "main",
    planted: int = 1,
    last_touched: int = 10,
    resolved: int | None = None,
) -> PlotlineRecord:
    return PlotlineRecord(
        thread_id=thread_id,
        title=title,
        content=f"线程内容: {title}",
        line_type=line_type,
        status="active",
        planted_chapter=planted,
        last_touched_chapter=last_touched,
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
    for r in records:
        payload = json.dumps({"line_type": r.get("line_type", "sub")})
        conn.execute(
            "INSERT INTO plot_thread_registry "
            "(thread_id, title, content, thread_type, status, priority, "
            "planted_chapter, last_touched_chapter, resolved_chapter, payload_json) "
            "VALUES (?, ?, ?, 'plotline', ?, ?, ?, ?, ?, ?)",
            (
                r.get("thread_id", "pl_001"),
                r.get("title", "测试线程"),
                r.get("content", "线程内容"),
                r.get("status", "active"),
                r.get("priority", 50),
                r.get("planted_chapter", 1),
                r.get("last_touched_chapter", 1),
                r.get("resolved_chapter"),
                payload,
            ),
        )
    conn.commit()
    conn.close()
    return db_path


# === Unit tests: helpers ===


class TestGetMaxGap:
    def test_main(self):
        cfg = _default_config()
        assert _get_max_gap("main", cfg) == 3

    def test_sub(self):
        cfg = _default_config()
        assert _get_max_gap("sub", cfg) == 8

    def test_dark(self):
        cfg = _default_config()
        assert _get_max_gap("dark", cfg) == 15

    def test_unknown_defaults_to_sub(self):
        cfg = _default_config()
        assert _get_max_gap("unknown", cfg) == 8


class TestSeverityForLineType:
    def test_main_is_critical(self):
        assert _severity_for_line_type("main") == "critical"

    def test_sub_is_high(self):
        assert _severity_for_line_type("sub") == "high"

    def test_dark_is_medium(self):
        assert _severity_for_line_type("dark") == "medium"


# === Unit tests: classify_inactive ===


class TestClassifyInactive:
    def test_within_gap_returns_none(self):
        rec = _make_record(line_type="main", last_touched=97)
        cfg = _default_config()
        assert _classify_inactive(rec, 100, cfg) is None

    def test_main_overdue_critical(self):
        rec = _make_record(line_type="main", last_touched=90)
        cfg = _default_config()
        result = _classify_inactive(rec, 100, cfg)
        assert result is not None
        assert result.severity == "critical"
        assert result.gap_chapters == 10
        assert result.max_gap == 3

    def test_sub_overdue_high(self):
        rec = _make_record(line_type="sub", last_touched=80)
        cfg = _default_config()
        result = _classify_inactive(rec, 100, cfg)
        assert result is not None
        assert result.severity == "high"
        assert result.gap_chapters == 20

    def test_dark_overdue_medium(self):
        rec = _make_record(line_type="dark", last_touched=80)
        cfg = _default_config()
        result = _classify_inactive(rec, 100, cfg)
        assert result is not None
        assert result.severity == "medium"

    def test_dark_within_gap(self):
        rec = _make_record(line_type="dark", last_touched=90)
        cfg = _default_config()
        assert _classify_inactive(rec, 100, cfg) is None

    def test_exact_boundary_no_trigger(self):
        rec = _make_record(line_type="main", last_touched=97)
        cfg = _default_config()
        assert _classify_inactive(rec, 100, cfg) is None

    def test_one_past_boundary_triggers(self):
        rec = _make_record(line_type="main", last_touched=96)
        cfg = _default_config()
        result = _classify_inactive(rec, 100, cfg)
        assert result is not None
        assert result.gap_chapters == 4


# === Integration tests: scan_plotlines ===


class TestScanPlotlines:
    def test_empty_db(self):
        db_path = _create_test_db([])
        result = scan_plotlines(db_path, 100)
        assert result.total_active == 0
        assert result.inactive == []

    def test_disabled_config(self):
        db_path = _create_test_db([{"thread_id": "pl_1"}])
        cfg = _default_config(enabled=False)
        result = scan_plotlines(db_path, 100, config=cfg)
        assert result.total_active == 0

    def test_single_active_within_gap(self):
        db_path = _create_test_db([
            {"thread_id": "pl_main", "last_touched_chapter": 98, "line_type": "main"},
        ])
        result = scan_plotlines(db_path, 100)
        assert result.total_active == 1
        assert result.inactive == []

    def test_main_line_inactive(self):
        db_path = _create_test_db([
            {"thread_id": "pl_main", "last_touched_chapter": 90, "line_type": "main", "priority": 90},
        ])
        result = scan_plotlines(db_path, 100)
        assert len(result.inactive) == 1
        assert result.inactive[0].severity == "critical"

    def test_multiple_lines_mixed(self):
        db_path = _create_test_db([
            {"thread_id": "pl_main", "last_touched_chapter": 99, "line_type": "main", "priority": 90},
            {"thread_id": "pl_sub", "last_touched_chapter": 80, "line_type": "sub", "priority": 60},
            {"thread_id": "pl_dark", "last_touched_chapter": 50, "line_type": "dark", "priority": 30},
        ])
        result = scan_plotlines(db_path, 100)
        assert result.total_active == 3
        assert len(result.inactive) == 2
        assert result.inactive[0].severity == "high"
        assert result.inactive[1].severity == "medium"

    def test_forced_advances_limited(self):
        db_path = _create_test_db([
            {"thread_id": f"pl_{i}", "last_touched_chapter": 1, "line_type": "sub", "priority": 50}
            for i in range(5)
        ])
        cfg = _default_config(max_forced_advances_per_chapter=2)
        result = scan_plotlines(db_path, 100, config=cfg)
        assert len(result.forced_advances) == 2

    def test_density_warning(self):
        db_path = _create_test_db([
            {"thread_id": f"pl_{i}", "last_touched_chapter": 99, "line_type": "sub"}
            for i in range(15)
        ])
        cfg = _default_config(active_plotline_warn_limit=10)
        result = scan_plotlines(db_path, 100, config=cfg)
        assert result.density_warning is True

    def test_resolved_lines_not_scanned(self):
        db_path = _create_test_db([
            {"thread_id": "pl_done", "last_touched_chapter": 10, "status": "resolved", "line_type": "main"},
        ])
        result = scan_plotlines(db_path, 100)
        assert result.total_active == 0

    def test_nonexistent_table(self):
        fd = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = fd.name
        fd.close()
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE dummy (id TEXT)")
        conn.commit()
        conn.close()
        result = scan_plotlines(db_path, 100)
        assert result.total_active == 0

    def test_alerts_contain_type_labels(self):
        db_path = _create_test_db([
            {"thread_id": "pl_main", "last_touched_chapter": 90, "line_type": "main", "title": "核心冲突"},
        ])
        result = scan_plotlines(db_path, 100)
        assert any("主线断更" in a for a in result.alerts)
        assert any("核心冲突" in a for a in result.alerts)


# === build_plan_injection ===


class TestBuildPlanInjection:
    def test_empty_scan(self):
        scan = PlotlineScanResult(current_chapter=10, total_active=3)
        payload = build_plan_injection(scan)
        assert payload["forced_advances"] == []
        assert payload["total_active"] == 3
        assert payload["total_inactive"] == 0

    def test_with_forced_advances(self):
        rec = _make_record(thread_id="pl_sub", line_type="sub", last_touched=80)
        ia = InactiveInfo(record=rec, gap_chapters=20, max_gap=8, severity="high")
        scan = PlotlineScanResult(
            current_chapter=100, total_active=5, inactive=[ia], forced_advances=[ia],
        )
        payload = build_plan_injection(scan)
        assert len(payload["forced_advances"]) == 1
        adv = payload["forced_advances"][0]
        assert adv["thread_id"] == "pl_sub"
        assert adv["line_type"] == "sub"
        assert adv["line_type_label"] == "支线"
        assert adv["gap_chapters"] == 20
        assert payload["mode"] == "force"


# === build_plotline_heatmap ===


class TestBuildPlotlineHeatmap:
    def test_empty_db(self):
        db_path = _create_test_db([])
        assert build_plotline_heatmap(db_path, 0) == []

    def test_basic_heatmap(self):
        db_path = _create_test_db([
            {"thread_id": "pl_main", "planted_chapter": 1, "last_touched_chapter": 5, "line_type": "main"},
            {"thread_id": "pl_sub", "planted_chapter": 3, "last_touched_chapter": 15, "line_type": "sub"},
        ])
        result = build_plotline_heatmap(db_path, 20, bucket_size=10)
        assert len(result) == 2
        assert result[0]["main_active"] == 1
        assert result[1]["sub_active"] == 1

    def test_resolved_counted(self):
        records = [
            {"thread_id": "pl_done", "planted_chapter": 1, "last_touched_chapter": 10,
             "status": "resolved", "resolved_chapter": 10, "line_type": "sub"},
        ]
        db_path = _create_test_db(records)
        # Mark it resolved
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE plot_thread_registry SET status='resolved', resolved_chapter=10 WHERE thread_id='pl_done'")
        conn.commit()
        conn.close()

        result = build_plotline_heatmap(db_path, 20, bucket_size=10)
        assert result[0]["resolved"] == 1


# === 300-chapter simulation ===


class TestSimulation300Chapters:
    def test_300_chapter_no_dropped_plotlines(self):
        """Simulate 300 chapters with plotline tracking; verify no dropped lines."""
        cfg = _default_config()
        records = []

        plotlines = [
            {"thread_id": "pl_main_quest", "title": "主线任务", "line_type": "main", "priority": 90},
            {"thread_id": "pl_romance", "title": "感情线", "line_type": "sub", "priority": 60},
            {"thread_id": "pl_dark_conspiracy", "title": "暗线阴谋", "line_type": "dark", "priority": 30},
            {"thread_id": "pl_side_mission", "title": "支线任务", "line_type": "sub", "priority": 50},
        ]

        for pl in plotlines:
            records.append({
                "thread_id": pl["thread_id"],
                "title": pl["title"],
                "line_type": pl["line_type"],
                "priority": pl["priority"],
                "planted_chapter": 1,
                "last_touched_chapter": 1,
            })

        db_path = _create_test_db(records)

        last_touched = {pl["thread_id"]: 1 for pl in plotlines}
        dropped_count = 0

        for ch in range(1, 301):
            scan = scan_plotlines(db_path, ch, config=cfg)

            for ia in scan.forced_advances:
                tid = ia.record.thread_id
                last_touched[tid] = ch
                conn = sqlite3.connect(db_path)
                conn.execute(
                    "UPDATE plot_thread_registry SET last_touched_chapter = ? WHERE thread_id = ?",
                    (ch, tid),
                )
                conn.commit()
                conn.close()

            if scan.inactive:
                for ia in scan.inactive:
                    if ia.severity == "critical":
                        dropped_count += 1

            for pl in plotlines:
                tid = pl["thread_id"]
                line_type = pl["line_type"]
                max_gap = _get_max_gap(line_type, cfg)
                if ch - last_touched[tid] >= max_gap and ch % (max_gap + 1) == 0:
                    last_touched[tid] = ch
                    conn = sqlite3.connect(db_path)
                    conn.execute(
                        "UPDATE plot_thread_registry SET last_touched_chapter = ? WHERE thread_id = ?",
                        (ch, tid),
                    )
                    conn.commit()
                    conn.close()

        final_scan = scan_plotlines(db_path, 300, config=cfg)
        for ia in final_scan.inactive:
            assert ia.severity != "critical", (
                f"Plotline {ia.record.thread_id} dropped at chapter 300"
            )
