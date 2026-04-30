"""state-db 一致性自动修复回归（task #20251130 Bug C）

历史现象（cipher 实测 2026-04-30）：
  Step 5 Data Agent 跑到一半被中断，导致：
  - chapter / appearances / review_metrics / summaries 表 / 文件已写
  - state.json.progress.current_chapter 未更新
  ↓
  下次 ink-auto 启动 → 用错误的 current_chapter 重写已完成的章

修复：scripts/state_consistency_check.py 自动检测 + 修正。
ink-auto.sh 在主循环开始前 + 每章写作前各调一次。

本测试守护 5 件事：
  1. state_consistency_check.py 模块可导入
  2. detect_truth 从 4 个来源探测最大章号
  3. 不一致时返回 changed=True 并备份原 state.json
  4. dry-run 模式不改文件
  5. ink-auto.sh 主流程接入了一致性检查（_s1_outline_precheck_if_root + run_chapter）
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "ink-writer" / "scripts"
INK_AUTO_SH = REPO_ROOT / "ink-writer" / "scripts" / "ink-auto.sh"

# 让 import 找得到
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _make_project(root: Path, *, db_max_chapter: int | None,
                  appearances_max: int | None,
                  summaries_chapters: list[int] | None,
                  body_chapters: list[int] | None,
                  state_current: int) -> Path:
    """构造测试项目目录骨架。"""
    (root / ".ink").mkdir(parents=True)
    (root / ".ink" / "summaries").mkdir()
    (root / "正文").mkdir()

    # state.json
    state = {
        "progress": {"current_chapter": state_current, "current_volume": 1, "is_completed": False}
    }
    (root / ".ink" / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # index.db
    db_path = root / ".ink" / "index.db"
    con = sqlite3.connect(str(db_path))
    con.execute("CREATE TABLE chapters (chapter INTEGER PRIMARY KEY, title TEXT)")
    con.execute("CREATE TABLE appearances (chapter INTEGER, entity TEXT)")
    if db_max_chapter is not None:
        for ch in range(1, db_max_chapter + 1):
            con.execute("INSERT INTO chapters (chapter, title) VALUES (?, ?)", (ch, f"ch{ch}"))
    if appearances_max is not None:
        for ch in range(1, appearances_max + 1):
            con.execute("INSERT INTO appearances (chapter, entity) VALUES (?, ?)", (ch, f"e{ch}"))
    con.commit()
    con.close()

    # summaries
    if summaries_chapters:
        for ch in summaries_chapters:
            (root / ".ink" / "summaries" / f"ch{ch:04d}.md").write_text("摘要", encoding="utf-8")

    # 正文
    if body_chapters:
        for ch in body_chapters:
            (root / "正文" / f"第{ch:04d}章-test.md").write_text("正文" * 1500, encoding="utf-8")

    return root


# ───────────────────────────────────────────────────────────────
# Python 模块测试
# ───────────────────────────────────────────────────────────────


def test_module_importable():
    import state_consistency_check  # noqa: F401


def test_detect_truth_uses_chapter_files_as_authority(tmp_path):
    """v2 策略：章节文件最大数 = 权威，不取最小值。

    这是 cipher 实测 2026-04-30 撞墙后修订的策略。v1 取最小值会让
    chapters 表只有 ch1 但章节文件 ch1-4 齐全时把 state.current 改回 1。
    """
    import state_consistency_check as scc

    proj = tmp_path / "novel"
    _make_project(
        proj,
        db_max_chapter=1,              # chapters 表只到 1（Step 5 中断）
        appearances_max=2,              # appearances 到 2
        summaries_chapters=[1, 2, 3],  # summaries 到 3
        body_chapters=[1, 2, 3, 4],     # 章节文件到 4 ← 这才是真相
        state_current=1,
    )
    truth, sources = scc.detect_truth(proj)
    assert truth == 4, f"应以章节文件为权威 = 4，实际 {truth}"
    # 4 个来源都被正确探测
    assert sources["chapters_table"] == 1
    assert sources["appearances"] == 2
    assert sources["summaries"] == 3
    assert sources["chapter_files"] == 4


def test_detect_truth_falls_back_to_summaries_when_no_chapter_files(tmp_path):
    """章节文件全没时，回退到 summaries。"""
    import state_consistency_check as scc

    proj = tmp_path / "novel"
    _make_project(
        proj,
        db_max_chapter=2, appearances_max=2,
        summaries_chapters=[1, 2, 3],   # summaries 到 3
        body_chapters=None,              # 章节文件不存在
        state_current=1,
    )
    truth, sources = scc.detect_truth(proj)
    assert truth == 3, f"无章节文件时应用 summaries=3，实际 {truth}"


def test_detect_truth_falls_back_to_chapters_table_when_no_files_no_summaries(tmp_path):
    """章节文件 + summaries 都没时，回退到 db.chapters。"""
    import state_consistency_check as scc

    proj = tmp_path / "novel"
    _make_project(
        proj,
        db_max_chapter=2, appearances_max=3,
        summaries_chapters=None, body_chapters=None,
        state_current=0,
    )
    truth, sources = scc.detect_truth(proj)
    assert truth == 2, f"应回退到 chapters_table=2，实际 {truth}"


def test_detect_truth_returns_none_for_empty_project(tmp_path):
    """空项目（无任何章节产物）应返回 None。"""
    import state_consistency_check as scc

    proj = tmp_path / "novel"
    _make_project(
        proj,
        db_max_chapter=None, appearances_max=None,
        summaries_chapters=None, body_chapters=None,
        state_current=0,
    )
    truth, _ = scc.detect_truth(proj)
    assert truth is None


def test_repair_state_fixes_lagging_current_chapter(tmp_path):
    """state.current=1 但 db 真相=2 时应修到 2。"""
    import state_consistency_check as scc

    proj = tmp_path / "novel"
    _make_project(
        proj,
        db_max_chapter=2, appearances_max=2,
        summaries_chapters=[1, 2], body_chapters=[1, 2],
        state_current=1,
    )
    changed, msg = scc.repair_state(proj, dry_run=False)
    assert changed, f"应该修改：{msg}"

    # state.json 应该被改了
    state = json.loads((proj / ".ink" / "state.json").read_text(encoding="utf-8"))
    assert state["progress"]["current_chapter"] == 2

    # 备份应该存在
    backup_dir = proj / ".ink" / "backups"
    assert backup_dir.is_dir()
    assert any(p.name.startswith("state.before_consistency_fix") for p in backup_dir.iterdir())


def test_repair_state_no_change_when_consistent(tmp_path):
    """一致时不该改文件。"""
    import state_consistency_check as scc

    proj = tmp_path / "novel"
    _make_project(
        proj,
        db_max_chapter=3, appearances_max=3,
        summaries_chapters=[1, 2, 3], body_chapters=[1, 2, 3],
        state_current=3,
    )
    changed, msg = scc.repair_state(proj, dry_run=False)
    assert not changed, f"一致时不该改：{msg}"
    assert "一致" in msg


def test_repair_state_dry_run_does_not_modify(tmp_path):
    import state_consistency_check as scc

    proj = tmp_path / "novel"
    _make_project(
        proj,
        db_max_chapter=2, appearances_max=2,
        summaries_chapters=[1, 2], body_chapters=[1, 2],
        state_current=1,
    )
    state_before = (proj / ".ink" / "state.json").read_text(encoding="utf-8")
    changed, msg = scc.repair_state(proj, dry_run=True)
    assert not changed, "dry-run 不该返回 changed=True"
    assert "dry-run" in msg
    state_after = (proj / ".ink" / "state.json").read_text(encoding="utf-8")
    assert state_before == state_after, "dry-run 不该改文件"


# ───────────────────────────────────────────────────────────────
# CLI 测试
# ───────────────────────────────────────────────────────────────


def test_cli_quiet_mode_silent_when_consistent(tmp_path, capsys):
    import subprocess
    proj = tmp_path / "novel"
    _make_project(
        proj,
        db_max_chapter=2, appearances_max=2,
        summaries_chapters=[1, 2], body_chapters=[1, 2],
        state_current=2,
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "state_consistency_check.py"),
         "--project-root", str(proj), "--quiet"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "", f"--quiet 一致时应不输出: {result.stdout!r}"


def test_cli_outputs_repair_message_on_inconsistency(tmp_path):
    import subprocess
    proj = tmp_path / "novel"
    _make_project(
        proj,
        db_max_chapter=2, appearances_max=2,
        summaries_chapters=[1, 2], body_chapters=[1, 2],
        state_current=1,
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "state_consistency_check.py"),
         "--project-root", str(proj)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "已修复" in result.stdout
    assert "1 → 2" in result.stdout


# ───────────────────────────────────────────────────────────────
# ink-auto.sh 主流程接入守护
# ───────────────────────────────────────────────────────────────


def test_ink_auto_sh_invokes_consistency_check_in_s1():
    """_s1_outline_precheck_if_root 必须调 state_consistency_check.py。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    m = re.search(
        r"^_s1_outline_precheck_if_root\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m, "_s1_outline_precheck_if_root 函数应可解析"
    body = m.group(1)
    assert "state_consistency_check.py" in body, (
        "_s1_outline_precheck_if_root 必须调 state_consistency_check.py 防漂移"
    )


def test_ink_auto_sh_invokes_consistency_check_in_run_chapter():
    """run_chapter 也必须调一致性检查（每章写前防漂移）。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    m = re.search(
        r"^run_chapter\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m
    body = m.group(1)
    assert "state_consistency_check.py" in body, (
        "run_chapter 必须每章写作前调一致性检查"
    )


def test_ink_auto_sh_heartbeat_reads_data_agent_timing():
    """write 心跳必须读 data_agent_timing.jsonl 显示最近 Data Agent 调用。

    这是 task #1 的核心：让 Step 5 期间用户能看到 Data Agent 在工作，
    避免误杀后状态漂移循环。
    """
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    assert "data_agent_timing.jsonl" in src, (
        "心跳必须读 data_agent_timing.jsonl 显示 Step 5 Data Agent 进度"
    )
    # 必须显示工具名 + 是否成功 + 距今时长
    assert "DataAgent:" in src or "tool_name" in src, (
        "心跳必须解析 data_agent_timing 里的 tool_name 字段"
    )


def test_ink_write_skill_constrains_process_chapter_to_once():
    """ink-write SKILL.md Step 5 必须含'process-chapter 全章只调 1 次'强约束。"""
    skill = REPO_ROOT / "ink-writer" / "skills" / "ink-write" / "SKILL.md"
    src = skill.read_text(encoding="utf-8")
    # 找到 Step 5 章节
    m = re.search(r"### Step 5：Data Agent.*?(?=###\s|\Z)", src, re.DOTALL)
    assert m, "Step 5 章节应可定位"
    step5 = m.group(0)
    assert "全章只能调用 1 次" in step5 or "全章只调" in step5, (
        "Step 5 必须明确硬约束 process-chapter 全章 1 次"
    )
    assert "data_agent_timing.jsonl" in step5, (
        "Step 5 必须示范用 data_agent_timing.jsonl 自检防重复"
    )
