"""Tests for the unified thread lifecycle tracker (US-025, F-004).

Verifies that ``ink_writer.thread_lifecycle.tracker.scan_all``:
    1. Runs both foreshadow and plotline scans.
    2. Returns a ``UnifiedScanResult`` with both sub-results preserved.
    3. Merges alerts in a stable order (foreshadow first, then plotline).
    4. Propagates configs and custom chapter numbers correctly.
    5. Exposes convenience aggregates (``total_active``, ``has_forced_actions``).
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from ink_writer.foreshadow.config import ForeshadowLifecycleConfig
from ink_writer.foreshadow.tracker import ForeshadowScanResult
from ink_writer.plotline.config import PlotlineLifecycleConfig
from ink_writer.plotline.tracker import PlotlineScanResult
from ink_writer.thread_lifecycle import UnifiedScanResult, scan_all
from ink_writer.thread_lifecycle.tracker import scan_all as scan_all_module_level


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_registry_db(rows: list[dict]) -> str:
    """Create a temp SQLite DB populated with the shared plot_thread_registry
    schema used by both foreshadow and plotline trackers."""
    fd = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = fd.name
    fd.close()
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
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
        """
    )
    for row in rows:
        conn.execute(
            "INSERT INTO plot_thread_registry "
            "(thread_id, title, content, thread_type, status, priority, "
            "planted_chapter, last_touched_chapter, target_payoff_chapter, "
            "resolved_chapter, payload_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row.get("thread_id"),
                row.get("title", "t"),
                row.get("content", ""),
                row.get("thread_type", "foreshadowing"),
                row.get("status", "active"),
                row.get("priority", 50),
                row.get("planted_chapter", 1),
                row.get("last_touched_chapter", 1),
                row.get("target_payoff_chapter"),
                row.get("resolved_chapter"),
                row.get("payload_json"),
            ),
        )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def mixed_db() -> str:
    """DB containing one critically overdue foreshadow + one inactive main plotline.

    Note on scanner semantics: ``_load_active_foreshadows`` selects every active
    row (it does not filter by ``thread_type``), while ``_load_active_plotlines``
    *does* filter ``thread_type = 'plotline'``. So foreshadow.total_active = 2
    (both rows) and plotline.total_active = 1. These tests assert that
    scan_all faithfully preserves the delegates' native semantics rather than
    silently reinterpreting them.
    """
    rows = [
        # Foreshadow: P0, target ch 50, current ch 60 ⇒ overdue by (60 - 55) = 5
        {
            "thread_id": "fs_001",
            "title": "关键伏笔",
            "thread_type": "foreshadowing",
            "priority": 90,
            "planted_chapter": 10,
            "last_touched_chapter": 20,
            "target_payoff_chapter": 50,
        },
        # Plotline: main line, last touched ch 20, current ch 60,
        # default main_max_gap is small enough that 40-chapter gap triggers inactive.
        {
            "thread_id": "pl_001",
            "title": "主线冲突",
            "thread_type": "plotline",
            "priority": 80,
            "planted_chapter": 5,
            "last_touched_chapter": 20,
            "payload_json": '{"line_type": "main"}',
        },
    ]
    return _create_registry_db(rows)


@pytest.fixture()
def empty_db() -> str:
    return _create_registry_db([])


# ---------------------------------------------------------------------------
# Basic smoke tests
# ---------------------------------------------------------------------------


class TestScanAllSmoke:
    def test_returns_unified_result_type(self, empty_db: str) -> None:
        result = scan_all(empty_db, current_chapter=10)
        assert isinstance(result, UnifiedScanResult)

    def test_empty_db_both_scanners_empty(self, empty_db: str) -> None:
        result = scan_all(empty_db, current_chapter=10)
        assert isinstance(result.foreshadow, ForeshadowScanResult)
        assert isinstance(result.plotline, PlotlineScanResult)
        assert result.foreshadow.total_active == 0
        assert result.plotline.total_active == 0
        assert result.total_active == 0
        assert result.has_forced_actions is False
        assert result.alerts == []

    def test_current_chapter_propagated(self, empty_db: str) -> None:
        result = scan_all(empty_db, current_chapter=42)
        assert result.current_chapter == 42
        assert result.foreshadow.current_chapter == 42
        assert result.plotline.current_chapter == 42

    def test_path_accepts_pathlib(self, empty_db: str) -> None:
        result = scan_all(Path(empty_db), current_chapter=1)
        assert result.total_active == 0


# ---------------------------------------------------------------------------
# Mixed DB: verifies delegation to both scanners works
# ---------------------------------------------------------------------------


class TestScanAllDelegation:
    def test_both_sub_results_populated(self, mixed_db: str) -> None:
        result = scan_all(mixed_db, current_chapter=60)

        # foreshadow scanner treats every active row as a foreshadow (by design);
        # plotline scanner filters thread_type='plotline'. scan_all preserves
        # both scanners' native semantics — see mixed_db docstring.
        assert result.foreshadow.total_active == 2
        assert result.plotline.total_active == 1
        assert result.total_active == 3

    def test_foreshadow_overdue_detected(self, mixed_db: str) -> None:
        result = scan_all(mixed_db, current_chapter=60)
        assert len(result.foreshadow.overdue) == 1
        overdue = result.foreshadow.overdue[0]
        assert overdue.record.thread_id == "fs_001"
        assert overdue.severity == "critical"

    def test_plotline_inactive_detected(self, mixed_db: str) -> None:
        result = scan_all(mixed_db, current_chapter=60)
        assert len(result.plotline.inactive) == 1
        inactive = result.plotline.inactive[0]
        assert inactive.record.thread_id == "pl_001"
        assert inactive.record.line_type == "main"
        assert inactive.severity == "critical"

    def test_has_forced_actions_true_when_both_fire(self, mixed_db: str) -> None:
        result = scan_all(mixed_db, current_chapter=60)
        assert result.has_forced_actions is True
        assert len(result.foreshadow.forced_payoffs) >= 1
        assert len(result.plotline.forced_advances) >= 1


# ---------------------------------------------------------------------------
# Alert merging order
# ---------------------------------------------------------------------------


class TestAlertMerging:
    def test_alerts_ordered_foreshadow_first(self, mixed_db: str) -> None:
        result = scan_all(mixed_db, current_chapter=60)
        # Both sides produce at least one alert string
        assert len(result.alerts) >= 2

        foreshadow_alerts = result.foreshadow.alerts
        plotline_alerts = result.plotline.alerts

        # Merged list should be exactly foreshadow + plotline (in that order)
        assert result.alerts == foreshadow_alerts + plotline_alerts

    def test_empty_db_produces_no_alerts(self, empty_db: str) -> None:
        result = scan_all(empty_db, current_chapter=5)
        assert result.alerts == []


# ---------------------------------------------------------------------------
# Config propagation
# ---------------------------------------------------------------------------


class TestConfigPropagation:
    def test_disabled_foreshadow_config_zeros_foreshadow_scan(self, mixed_db: str) -> None:
        disabled_cfg = ForeshadowLifecycleConfig(enabled=False)
        result = scan_all(
            mixed_db,
            current_chapter=60,
            foreshadow_config=disabled_cfg,
        )
        # Foreshadow side reports zero active; plotline side still fires with
        # its normally-filtered count.
        assert result.foreshadow.total_active == 0
        assert result.foreshadow.overdue == []
        assert result.plotline.total_active == 1

    def test_disabled_plotline_config_zeros_plotline_scan(self, mixed_db: str) -> None:
        disabled_cfg = PlotlineLifecycleConfig(enabled=False)
        result = scan_all(
            mixed_db,
            current_chapter=60,
            plotline_config=disabled_cfg,
        )
        assert result.plotline.total_active == 0
        assert result.plotline.inactive == []
        # Foreshadow scanner still fires on all active rows (see mixed_db docstring)
        assert result.foreshadow.total_active == 2


# ---------------------------------------------------------------------------
# Import surface
# ---------------------------------------------------------------------------


class TestImportSurface:
    def test_package_reexport_matches_module(self) -> None:
        # Package-level import and module-level import reference the same callable
        assert scan_all is scan_all_module_level

    def test_unified_scan_result_has_expected_fields(self, empty_db: str) -> None:
        result = scan_all(empty_db, current_chapter=1)
        assert hasattr(result, "current_chapter")
        assert hasattr(result, "foreshadow")
        assert hasattr(result, "plotline")
        assert hasattr(result, "alerts")
        assert hasattr(result, "total_active")
        assert hasattr(result, "has_forced_actions")
