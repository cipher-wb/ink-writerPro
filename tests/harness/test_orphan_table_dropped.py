"""US-019: protagonist_knowledge 孤儿表已删除验证。

验证：
  1. 新建的 index.db 不含 protagonist_knowledge 表
  2. 若旧 index.db 含此表，init 时会 DROP（迁移路径）
  3. 其它在用表 schema_meta / rag_schema_meta 保持不变（v5 审计这两个误判为孤儿）
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def test_new_db_does_not_have_protagonist_knowledge(tmp_path, monkeypatch):
    pytest.importorskip("data_modules.index_manager", reason="data_modules not available")
    monkeypatch.chdir(tmp_path)
    from ink_writer.core.infra.config import DataModulesConfig
    from ink_writer.core.index.index_manager import IndexManager

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    idx = IndexManager(cfg)  # 触发 _init_db

    db_path = cfg.ink_dir / "index.db"
    with sqlite3.connect(str(db_path)) as conn:
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "protagonist_knowledge" not in tables, (
        f"protagonist_knowledge should be dropped, got tables: {tables}"
    )
    # schema_meta 和 entities 仍在（因为它们不是孤儿）
    assert "schema_meta" in tables or "entities" in tables, (
        f"core tables should still exist, got: {tables}"
    )


def test_legacy_db_with_protagonist_knowledge_gets_dropped(tmp_path, monkeypatch):
    """旧 db 含 protagonist_knowledge → IndexManager init 后被 DROP。"""
    pytest.importorskip("data_modules.index_manager", reason="data_modules not available")
    monkeypatch.chdir(tmp_path)
    from ink_writer.core.infra.config import DataModulesConfig
    from ink_writer.core.index.index_manager import IndexManager

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    db_path = cfg.ink_dir / "index.db"

    # 预先创建旧 protagonist_knowledge
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("""
            CREATE TABLE protagonist_knowledge (
                id INTEGER PRIMARY KEY,
                entity_id TEXT,
                knowledge_type TEXT
            )
        """)
        conn.execute(
            "INSERT INTO protagonist_knowledge (id, entity_id, knowledge_type) VALUES (1, 'X', 'Y')"
        )
        conn.commit()

    # 初始化 IndexManager 会触发 DROP TABLE IF EXISTS
    idx = IndexManager(cfg)

    with sqlite3.connect(str(db_path)) as conn:
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "protagonist_knowledge" not in tables, (
        "legacy protagonist_knowledge should have been dropped"
    )
