#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for index.db integrity check, backup, rebuild, and restore.
"""

import sqlite3

import pytest

from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager, ChapterMeta


@pytest.fixture
def temp_project(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return cfg


@pytest.fixture
def populated_project(tmp_path):
    """Create a project with chapters and index.db data."""
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    mgr = IndexManager(cfg)

    # Create chapter files
    chapters_dir = cfg.chapters_dir
    chapters_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, 4):
        chapter_file = chapters_dir / f"第{i:04d}章-测试章节{i}.md"
        chapter_file.write_text(f"# 第{i}章\n\n这是测试内容。" * 100, encoding="utf-8")

    # Create summaries
    summaries_dir = cfg.ink_dir / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, 4):
        summary_file = summaries_dir / f"ch{i:04d}.md"
        summary_file.write_text(f"第{i}章摘要：测试内容。", encoding="utf-8")

    # Add chapter data to index.db
    for i in range(1, 4):
        meta = ChapterMeta(
            chapter=i,
            title=f"测试章节{i}",
            location="测试地点",
            word_count=2500,
            characters=["主角", "配角"],
            summary=f"第{i}章摘要",
        )
        mgr.add_chapter(meta)

    return cfg


# ==================== check_integrity ====================

def test_check_integrity_healthy_db(temp_project):
    mgr = IndexManager(temp_project)
    result = mgr.check_integrity()
    assert result["ok"] is True
    assert result["detail"] == "ok"
    assert result["table_count"] > 0


def test_check_integrity_missing_db(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    # Don't create IndexManager (which creates the db)
    mgr = IndexManager.__new__(IndexManager)
    mgr.config = cfg
    result = mgr.check_integrity()
    assert result["ok"] is False
    assert "not found" in result["detail"]


def test_check_integrity_corrupted_db(temp_project):
    mgr = IndexManager(temp_project)
    db_path = temp_project.index_db

    # Corrupt the database by writing garbage
    with open(db_path, "wb") as f:
        f.write(b"THIS IS NOT A VALID SQLITE DATABASE FILE" * 10)

    result = mgr.check_integrity()
    assert result["ok"] is False


# ==================== backup_db ====================

def test_backup_db_success(temp_project):
    mgr = IndexManager(temp_project)
    path = mgr.backup_db(reason="test")
    assert path is not None
    assert path.exists()
    assert "test" in path.name
    assert path.suffix == ".bak"


def test_backup_db_no_db(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    mgr = IndexManager.__new__(IndexManager)
    mgr.config = cfg
    path = mgr.backup_db()
    assert path is None


def test_backup_db_creates_valid_copy(populated_project):
    mgr = IndexManager(populated_project)
    path = mgr.backup_db(reason="valid_test")
    assert path is not None

    # Verify the backup is a valid SQLite database
    conn = sqlite3.connect(str(path))
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        assert result[0] == "ok"
        chapters = conn.execute("SELECT count(*) FROM chapters").fetchone()
        assert chapters[0] == 3
    finally:
        conn.close()


# ==================== list_backups ====================

def test_list_backups_empty(tmp_path):
    backups = IndexManager.list_backups(tmp_path)
    assert backups == []


def test_list_backups_with_files(temp_project):
    mgr = IndexManager(temp_project)
    mgr.backup_db(reason="a")
    mgr.backup_db(reason="b")
    backups = IndexManager.list_backups(temp_project.ink_dir)
    assert len(backups) == 2
    assert all("name" in b and "size" in b for b in backups)


# ==================== restore_from_backup ====================

def test_restore_from_backup(populated_project):
    mgr = IndexManager(populated_project)

    # Backup
    backup_path = mgr.backup_db(reason="before_damage")
    assert backup_path is not None

    # Damage the database
    db_path = populated_project.index_db
    with open(db_path, "wb") as f:
        f.write(b"CORRUPTED" * 100)

    # Verify it's broken
    check = mgr.check_integrity()
    assert check["ok"] is False

    # Restore
    ok = mgr.restore_from_backup(backup_path)
    assert ok is True

    # Verify restoration
    check = mgr.check_integrity()
    assert check["ok"] is True

    # Verify data survived
    mgr2 = IndexManager(populated_project)
    with mgr2._get_conn() as conn:
        count = conn.execute("SELECT count(*) FROM chapters").fetchone()[0]
    assert count == 3


def test_restore_from_nonexistent_file(temp_project):
    mgr = IndexManager(temp_project)
    from pathlib import Path
    ok = mgr.restore_from_backup(Path("/nonexistent/backup.bak"))
    assert ok is False


# ==================== rebuild_db ====================

def test_rebuild_db_from_chapters(populated_project):
    mgr = IndexManager(populated_project)

    # Delete the database
    populated_project.index_db.unlink()
    assert not populated_project.index_db.exists()

    # Rebuild
    result = mgr.rebuild_db()
    assert result["ok"] is True
    assert result["chapters_recovered"] == 3

    # Verify rebuilt database
    check = mgr.check_integrity()
    assert check["ok"] is True

    mgr2 = IndexManager(populated_project)
    with mgr2._get_conn() as conn:
        count = conn.execute("SELECT count(*) FROM chapters").fetchone()[0]
    assert count == 3


def test_rebuild_db_creates_backup_first(populated_project):
    mgr = IndexManager(populated_project)
    result = mgr.rebuild_db()
    assert result["ok"] is True

    # Check that a pre_rebuild backup was created
    backups = IndexManager.list_backups(populated_project.ink_dir)
    assert any("pre_rebuild" in b["name"] for b in backups)


def test_rebuild_db_empty_project(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    mgr = IndexManager(cfg)

    result = mgr.rebuild_db()
    assert result["ok"] is True
    assert result["chapters_recovered"] == 0


def test_rebuild_db_recovers_summaries(populated_project):
    mgr = IndexManager(populated_project)
    populated_project.index_db.unlink()

    result = mgr.rebuild_db()
    assert result["ok"] is True

    # Check that summaries were loaded into rebuilt chapters
    mgr2 = IndexManager(populated_project)
    with mgr2._get_conn() as conn:
        row = conn.execute("SELECT summary FROM chapters WHERE chapter=1").fetchone()
    assert row is not None
    assert len(row[0]) > 0
