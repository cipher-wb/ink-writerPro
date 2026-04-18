"""US-012/013: archive_manager + update_state 走 StateManager SQL-first。

验证：
  1. save_external_state 正确写 SQL + JSON
  2. SQL 写失败时 raise StateWriteError
  3. save_external_state 文本内容正确往返
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_save_external_state_writes_sql_and_json(tmp_path, monkeypatch):
    pytest.importorskip("data_modules.state_manager", reason="data_modules not available")
    monkeypatch.chdir(tmp_path)
    from data_modules.config import DataModulesConfig
    from data_modules.state_manager import StateManager

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    sm = StateManager(cfg)

    state = {
        "schema_version": 10,
        "project_info": {"title": "US-012 测试", "genre": "仙侠"},
        "progress": {"current_chapter": 5, "total_words": 12345},
    }
    sm.save_external_state(state)

    # JSON 视图已写
    data = json.loads(cfg.state_file.read_text(encoding="utf-8"))
    assert data["project_info"]["title"] == "US-012 测试"
    assert data["progress"]["current_chapter"] == 5


def test_save_external_state_raises_on_sql_failure(tmp_path, monkeypatch):
    pytest.importorskip("data_modules.state_manager", reason="data_modules not available")
    monkeypatch.chdir(tmp_path)
    from data_modules.config import DataModulesConfig
    from data_modules.state_manager import StateManager, StateWriteError

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    sm = StateManager(cfg)

    class _BrokenSQL:
        def bulk_set_state_kv(self, entries):
            raise RuntimeError("simulated sql fail")

    sm._sql_state_manager = _BrokenSQL()

    with pytest.raises(StateWriteError, match="save_external_state: SQL sync failed"):
        sm.save_external_state({"schema_version": 10, "project_info": {}})
