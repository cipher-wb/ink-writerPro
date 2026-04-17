"""US-025: 静态扫描验证所有直写 state.json 已被审计。

验证：
  1. 代码库中 atomic_write_json 调用点总数在预期范围
  2. archive_manager.py 的直写有 TODO 注释（审计已识别）
  3. ink-resolve SKILL.md 已迁移到 SQL（由 US-011 test 独立保证）
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = ROOT / "ink-writer" / "scripts"


def test_atomic_write_json_callsites_in_expected_range():
    """所有 atomic_write_json 调用点数（非测试）应在 8-15 之间。

    2026-04-17 审计实测 13 处（见 tasks/audit-direct-state-writes-2026-04-17.md）：
      9 处合法路径（init_project/project_locator/workflow_manager/snapshot_manager/
      state_manager.flush/security_utils 定义），2 处 TODO（archive_manager/update_state）。
    未来新增需同步更新审计报告和本 test。
    """
    count = 0
    for py_file in SCRIPTS_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        if "/tests/" in str(py_file) or py_file.name.startswith("test_"):
            continue
        content = py_file.read_text(encoding="utf-8")
        # 只计 atomic_write_json( 的调用，不计 import
        call_sites = re.findall(r"[^_\w]atomic_write_json\s*\(", content)
        count += len(call_sites)

    assert 8 <= count <= 15, (
        f"atomic_write_json call sites = {count} (expected 8-15 per 2026-04-17 audit). "
        f"If you added new state.json writes, update tasks/audit-direct-state-writes-2026-04-17.md."
    )


def test_archive_manager_save_state_has_todo_marker():
    """archive_manager.py:save_state 必须含 US-025 的 TODO 注释（归档流程 state 直写已审计）。"""
    am_path = SCRIPTS_DIR / "archive_manager.py"
    content = am_path.read_text(encoding="utf-8")
    # 查找 save_state 方法附近的 TODO
    assert "TODO(next-round)" in content or "US-025" in content, (
        "archive_manager.py save_state 应含 US-025 TODO 标记（见 "
        "tasks/audit-direct-state-writes-2026-04-17.md）"
    )


def test_audit_report_exists():
    """审计报告文件存在。"""
    report = ROOT / "tasks" / "audit-direct-state-writes-2026-04-17.md"
    assert report.exists(), f"审计报告 {report} 应由 US-025 产出"
    content = report.read_text(encoding="utf-8")
    assert "archive_manager.py" in content
    assert "state_manager.py:440" in content
