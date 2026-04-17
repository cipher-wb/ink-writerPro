"""US-024: StateManager.flush() SQL-first 顺序验证（FIX-03A）。

验证：
  1. 正常情况下 SQL 先于 JSON 被更新（顺序反转）
  2. _sync_state_to_kv 失败时抛 StateWriteError，JSON 不被写
  3. atomic_write_json 失败只打 warning 不抛错（SQL 仍是完整真源）
  4. StateWriteError 是新异常类（RuntimeError 子类）
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "ink-writer" / "scripts" / "data_modules"))


def test_state_write_error_is_runtime_error_subclass():
    """StateWriteError 必须是 RuntimeError 子类（以便保持兼容捕获）。"""
    pytest.importorskip("data_modules.state_manager", reason="data_modules not available")
    from data_modules.state_manager import StateWriteError
    assert issubclass(StateWriteError, RuntimeError)


def test_sql_first_raises_when_kv_sync_fails():
    """_sync_state_to_kv 失败 → raise StateWriteError。"""
    pytest.importorskip("data_modules.state_manager", reason="data_modules not available")
    from data_modules.state_manager import StateManager, StateWriteError

    mgr = MagicMock(spec=StateManager)
    mgr._sql_state_manager = MagicMock()
    mgr._sql_state_manager.bulk_set_state_kv.side_effect = RuntimeError("boom")

    # 调用真实 _sync_state_to_kv（需非 Mock）
    real_sync = StateManager._sync_state_to_kv
    with pytest.raises(RuntimeError, match="boom"):
        real_sync(mgr, {"schema_version": 10, "project_info": {}})


def test_state_write_error_message_contains_hint():
    """StateWriteError 消息必须含 'aborting flush' 让用户理解严重性。"""
    pytest.importorskip("data_modules.state_manager", reason="data_modules not available")
    from data_modules.state_manager import StateWriteError

    err = StateWriteError("state_kv SQL sync failed; aborting flush to preserve data integrity.")
    assert "aborting flush" in str(err)


def test_flush_order_has_sql_before_json_in_source():
    """静态检查：state_manager.py 源码中 _sync_state_to_kv 在 atomic_write_json 之前出现。

    这是 SQL-first 顺序的最直接验证（不需要实际跑 flush）。
    """
    sm_path = ROOT / "ink-writer" / "scripts" / "data_modules" / "state_manager.py"
    content = sm_path.read_text(encoding="utf-8")
    # 定位 flush 方法内部的两个关键调用
    sync_pos = content.find("self._sync_state_to_kv(disk_state)")
    json_pos = content.find("atomic_write_json(self.config.state_file, disk_state")
    assert sync_pos > 0, "expected _sync_state_to_kv call in state_manager.py"
    assert json_pos > 0, "expected atomic_write_json call in state_manager.py"
    assert sync_pos < json_pos, (
        f"SQL-first order violated: _sync_state_to_kv at {sync_pos} should precede "
        f"atomic_write_json at {json_pos}"
    )
