#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for migration_auditor.py — discover, create-tables, audit."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

import migration_auditor


def _load_module():
    return migration_auditor


@pytest.fixture
def mod():
    return _load_module()


@pytest.fixture
def project(tmp_path):
    """Create a minimal v8-style project for migration testing."""
    ink = tmp_path / ".ink"
    ink.mkdir()

    state = {
        "schema_version": 5,
        "progress": {"current_chapter": 3},
        "harness_config": {},
    }
    (ink / "state.json").write_text(json.dumps(state), encoding="utf-8")

    # Create index.db with a basic table
    db_path = ink / "index.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE entities (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute(
        "CREATE TABLE plot_threads "
        "(thread_id TEXT, planted_chapter INTEGER, expected_payoff_chapter INTEGER, status TEXT)"
    )
    conn.commit()
    conn.close()

    # Create chapter files
    chapters = tmp_path / "正文"
    chapters.mkdir()
    for i in range(1, 4):
        (chapters / f"第{i}章.md").write_text(f"# 第{i}章\n测试内容", encoding="utf-8")

    # Create summaries
    summaries = ink / "summaries"
    summaries.mkdir()
    for i in range(1, 3):
        (summaries / f"ch{i}.md").write_text(f"摘要{i}", encoding="utf-8")

    return tmp_path


@pytest.fixture
def v9_project(tmp_path):
    """Create a v9-style project (already migrated)."""
    ink = tmp_path / ".ink"
    ink.mkdir()

    state = {
        "schema_version": 7,
        "progress": {"current_chapter": 5},
        "harness_config": {"reader_agent_mode": "core_judge"},
    }
    (ink / "state.json").write_text(json.dumps(state), encoding="utf-8")

    db_path = ink / "index.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE entities (id INTEGER PRIMARY KEY)")
    conn.execute(
        "CREATE TABLE harness_evaluations "
        "(id INTEGER PRIMARY KEY, chapter INTEGER, total REAL)"
    )
    conn.execute(
        "CREATE TABLE computational_gate_log "
        "(id INTEGER PRIMARY KEY, chapter INTEGER, gate_pass INTEGER)"
    )
    conn.execute(
        "CREATE TABLE plot_threads "
        "(thread_id TEXT, planted_chapter INTEGER, expected_payoff_chapter INTEGER, status TEXT)"
    )
    conn.commit()
    conn.close()

    chapters = tmp_path / "正文"
    chapters.mkdir()
    for i in range(1, 6):
        (chapters / f"第{i}章.md").write_text(f"# 第{i}章", encoding="utf-8")

    summaries = ink / "summaries"
    summaries.mkdir()
    for i in range(1, 6):
        (summaries / f"ch{i}.md").write_text(f"摘要{i}", encoding="utf-8")

    return tmp_path


# ===========================================================================
# Helper functions
# ===========================================================================

class TestHelpers:
    def test_ink_dir(self, mod, tmp_path):
        assert mod._ink_dir(tmp_path) == tmp_path / ".ink"

    def test_state_path(self, mod, tmp_path):
        assert mod._state_path(tmp_path) == tmp_path / ".ink" / "state.json"

    def test_index_db_path(self, mod, tmp_path):
        assert mod._index_db_path(tmp_path) == tmp_path / ".ink" / "index.db"

    def test_list_tables(self, mod, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE foo (id INTEGER)")
        conn.execute("CREATE TABLE bar (id INTEGER)")
        conn.commit()
        conn.close()
        tables = mod._list_tables(db)
        assert "foo" in tables
        assert "bar" in tables

    def test_list_tables_nonexistent(self, mod, tmp_path):
        assert mod._list_tables(tmp_path / "nope.db") == []


# ===========================================================================
# discover_assets
# ===========================================================================

class TestDiscoverAssets:
    def test_basic_discovery(self, mod, project):
        assets = mod.discover_assets(project)
        assert assets["state_json"]["exists"] is True
        assert assets["state_json"]["schema_version"] == 5
        assert assets["chapters"]["count"] == 3
        assert assets["summaries"]["count"] == 2
        assert assets["index_db"]["exists"] is True

    def test_no_state(self, mod, tmp_path):
        (tmp_path / ".ink").mkdir()
        assets = mod.discover_assets(tmp_path)
        assert assets["state_json"]["exists"] is False

    def test_no_index_db(self, mod, tmp_path):
        ink = tmp_path / ".ink"
        ink.mkdir()
        (ink / "state.json").write_text('{"schema_version": 5}', encoding="utf-8")
        assets = mod.discover_assets(tmp_path)
        assert assets["index_db"]["exists"] is False

    def test_vectors_db_detection(self, mod, project):
        assets = mod.discover_assets(project)
        assert assets["vectors_db"]["exists"] is False
        (project / ".ink" / "vectors.db").touch()
        assets2 = mod.discover_assets(project)
        assert assets2["vectors_db"]["exists"] is True

    def test_outline_and_review_counting(self, mod, project):
        (project / "大纲").mkdir()
        (project / "大纲" / "v1.md").write_text("大纲", encoding="utf-8")
        (project / "审查报告").mkdir()
        (project / "审查报告" / "r1.md").write_text("报告", encoding="utf-8")
        assets = mod.discover_assets(project)
        assert assets["outlines"]["count"] == 1
        assert assets["reviews"]["count"] == 1


# ===========================================================================
# cmd_discover
# ===========================================================================

class TestCmdDiscover:
    def test_no_state_returns_error(self, mod, tmp_path):
        (tmp_path / ".ink").mkdir()
        assert mod.cmd_discover(tmp_path) == 1

    def test_already_v9(self, mod, v9_project, capsys):
        result = mod.cmd_discover(v9_project)
        assert result == 0
        assert "v9.0" in capsys.readouterr().out

    def test_needs_migration(self, mod, project, capsys):
        result = mod.cmd_discover(project)
        assert result == 0
        out = capsys.readouterr().out
        assert "资产发现" in out
        # Verify inventory saved
        inv = project / ".ink" / "migration" / "asset_inventory.json"
        assert inv.exists()


# ===========================================================================
# cmd_create_tables
# ===========================================================================

class TestCmdCreateTables:
    def test_creates_new_tables(self, mod, project):
        result = mod.cmd_create_tables(project)
        assert result == 0
        db = project / ".ink" / "index.db"
        conn = sqlite3.connect(str(db))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]
        conn.close()
        assert "harness_evaluations" in tables
        assert "computational_gate_log" in tables

    def test_no_db_returns_error(self, mod, tmp_path):
        (tmp_path / ".ink").mkdir()
        assert mod.cmd_create_tables(tmp_path) == 1

    def test_idempotent(self, mod, project):
        mod.cmd_create_tables(project)
        result = mod.cmd_create_tables(project)
        assert result == 0


# ===========================================================================
# cmd_audit
# ===========================================================================

class TestCmdAudit:
    def test_audit_v9_all_pass(self, mod, v9_project):
        result = mod.cmd_audit(v9_project)
        assert result == 0
        report = v9_project / ".ink" / "migration" / "audit_report.md"
        assert report.exists()
        content = report.read_text(encoding="utf-8")
        assert "迁移审计报告" in content

    def test_audit_v8_has_failures(self, mod, project):
        result = mod.cmd_audit(project)
        assert result == 1  # schema < 7 → fail

    def test_audit_no_state(self, mod, tmp_path):
        (tmp_path / ".ink").mkdir()
        assert mod.cmd_audit(tmp_path) == 1

    def test_overdue_threads_detected(self, mod, v9_project):
        db = v9_project / ".ink" / "index.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO plot_threads VALUES (?, ?, ?, ?)",
            ("古老预言", 1, 2, "active"),
        )
        conn.commit()
        conn.close()
        # current_chapter=5, expected=2, delay=3 (<20, so not severe)
        result = mod.cmd_audit(v9_project)
        assert result == 0

    def test_severely_overdue_threads(self, mod, v9_project):
        # Update current chapter to 50 and add a thread expected at ch 5
        state_path = v9_project / ".ink" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["progress"]["current_chapter"] = 50
        state_path.write_text(json.dumps(state), encoding="utf-8")

        db = v9_project / ".ink" / "index.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO plot_threads VALUES (?, ?, ?, ?)",
            ("神秘宝藏", 1, 5, "active"),
        )
        conn.commit()
        conn.close()

        result = mod.cmd_audit(v9_project)
        assert result == 0
        report = (v9_project / ".ink" / "migration" / "audit_report.md").read_text(encoding="utf-8")
        assert "逾期" in report


# ===========================================================================
# _check_overdue_threads
# ===========================================================================

class TestCheckOverdueThreads:
    def test_no_db(self, mod, tmp_path):
        (tmp_path / ".ink").mkdir()
        assert mod._check_overdue_threads(tmp_path, 100) == []

    def test_no_overdue(self, mod, v9_project):
        result = mod._check_overdue_threads(v9_project, 5)
        assert result == []


# ===========================================================================
# main (CLI argument parsing)
# ===========================================================================

class TestMain:
    def test_invalid_directory(self, mod):
        with patch("sys.argv", ["prog", "--project-root", "/nonexistent/dir", "discover"]):
            assert mod.main() == 1

    def test_discover_command(self, mod, v9_project):
        with patch("sys.argv", ["prog", "--project-root", str(v9_project), "discover"]):
            result = mod.main()
            assert result == 0

    def test_create_tables_command(self, mod, project):
        with patch("sys.argv", ["prog", "--project-root", str(project), "create-tables"]):
            result = mod.main()
            assert result == 0

    def test_audit_command(self, mod, v9_project):
        with patch("sys.argv", ["prog", "--project-root", str(v9_project), "audit"]):
            result = mod.main()
            assert result == 0
