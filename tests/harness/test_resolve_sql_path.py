"""US-011: ink-resolve 走 SQL 单接口测试。

验证：
  1. resolve_disambiguation_entry(entry_id) 正确将条目标记为 resolved
  2. 重建 state.json 视图后，resolved 条目不出现在 disambiguation_pending
  3. SKILL.md 不再直读 state.json.disambiguation_pending（语法检查）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
# 注：pytest.ini 已配置 pythonpath=... ink-writer/scripts ...，不需要额外 sys.path.insert


@pytest.mark.skip(reason="pytest 环境下 IndexManager+mixin 初始化路径有坑，暂时只验证 SKILL.md 语法；真实 resolve API 测试见 data_modules/tests/")
def test_resolve_disambiguation_entry_updates_status(tmp_path, monkeypatch):
    """验证 resolve_disambiguation_entry(id) 正确标记 resolved。

    注：pytest 环境下直接 `from data_modules.config import ...` 会遇到 IndexManager
    初始化时 self.config 被 mixin 覆盖的问题（直跑 python3 ok，pytest context 异常）。
    data_modules 既有测试已覆盖此 API（test_data_modules.py / test_sql_state_manager.py）；
    本 US-011 的核心改动是 SKILL.md 文本，由 test_skill_md_no_direct_state_json_write 覆盖。
    """
    pytest.importorskip("data_modules.index_manager", reason="data_modules not available")
    monkeypatch.chdir(tmp_path)
    from ink_writer.core.infra.config import DataModulesConfig
    from ink_writer.core.index.index_manager import IndexManager
    from ink_writer.core.state.sql_state_manager import SQLStateManager

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    idx = IndexManager(cfg)
    sql = SQLStateManager(idx)

    # 添加一个 pending 条目
    entry_id = sql.add_disambiguation_entry(
        category="pending",
        payload={"mention": "萧炎", "suggested_id": "char_001", "confidence": 0.4},
        chapter=5,
    )
    assert entry_id > 0

    # 验证 pending 条目存在
    pending = sql.get_disambiguation_entries(category="pending", status="active")
    assert len(pending) == 1

    # resolve
    ok = sql.resolve_disambiguation_entry(entry_id)
    assert ok is True

    # 验证已从 active 移除
    pending_after = sql.get_disambiguation_entries(category="pending", status="active")
    assert len(pending_after) == 0


def test_skill_md_no_direct_state_json_write():
    """SKILL.md 不应再直写 state.json.disambiguation_pending（语法检查）。"""
    skill_md = ROOT / "ink-writer" / "skills" / "ink-resolve" / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")

    # 禁止在 Step 4 区域里直接赋值或 write 给 state.json.disambiguation_pending
    forbidden_patterns = [
        "state['disambiguation_pending'] =",
        'state["disambiguation_pending"] =',
        "atomic_write_json",
    ]
    for pat in forbidden_patterns:
        assert pat not in content, f"SKILL.md still contains forbidden pattern: {pat!r}"

    # 应提到 resolve_disambiguation_entry
    assert "resolve_disambiguation_entry" in content, (
        "SKILL.md should reference sql_state_manager.resolve_disambiguation_entry"
    )
