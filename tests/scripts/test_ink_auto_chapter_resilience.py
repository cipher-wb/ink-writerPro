"""ink-auto.sh 单章韧性回归（针对 2026-04-29 cipher 第 2 章 1480 字超时事件）

历史现象：
  第 2 章写作 30 分钟后被 watchdog 终止，留下 1480 字（< 2200 硬下限）半成品
  在 正文/ 下。下次 /ink-auto 看到该文件存在可能误判章节已写完。

修复方向（task #16）：
  1. 默认 chapter timeout 从 1800s 提到 3600s（60min）—— 给 LLM 极端情况留余量
  2. 半成品自动归档：< MIN_WORDS_HARD 的不完整章节移到
     .ink/recovery_backups/partial_chapters/，避免误判
  3. 卡住检测：心跳期间 INK_AUTO_STALL_THRESHOLD（默认 600s）内字数无增长
     且 workflow_state.json 当前 step 也无变化 → 提前 SIGTERM，进入重试

本测试守护以上 3 项不被未来 PR 回退。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INK_AUTO_SH = REPO_ROOT / "ink-writer" / "scripts" / "ink-auto.sh"


def _read() -> str:
    return INK_AUTO_SH.read_text(encoding="utf-8")


# ───────────────────────────────────────────────────────────────
# 1. 默认 chapter timeout ≥ 3600s
# ───────────────────────────────────────────────────────────────


def test_default_chapter_timeout_is_3600s_or_more():
    """INK_AUTO_CHAPTER_TIMEOUT 默认值不能低于 3600s。

    1800s 在 2026-04-29 用户实测撞墙；3600s 给极端 Hard Block Rewrite 留余量。
    """
    src = _read()
    # 所有 INK_AUTO_CHAPTER_TIMEOUT:-N 的兜底值都必须 ≥ 3600
    matches = re.findall(r"INK_AUTO_CHAPTER_TIMEOUT:-(\d+)", src)
    assert matches, "ink-auto.sh 必须有 INK_AUTO_CHAPTER_TIMEOUT 默认值"
    for default in matches:
        assert int(default) >= 3600, (
            f"INK_AUTO_CHAPTER_TIMEOUT 默认 {default}s 太短（< 3600）。"
            f"用户实测 1800s 已撞墙。"
        )


# ───────────────────────────────────────────────────────────────
# 2. 半成品自动归档
# ───────────────────────────────────────────────────────────────


def test_archive_partial_chapter_function_defined():
    """ink-auto.sh 必须定义 _archive_partial_chapter 函数清理半成品。"""
    src = _read()
    assert re.search(r"^_archive_partial_chapter\s*\(\s*\)\s*\{", src, re.MULTILINE), (
        "_archive_partial_chapter 函数必须定义，用于把 < MIN_WORDS_HARD "
        "的不完整章节归档到 recovery_backups/"
    )


def test_archive_partial_chapter_uses_min_words_hard():
    """归档判定阈值必须用 MIN_WORDS_HARD（与 verify_chapter 一致）。"""
    src = _read()
    # 抠出函数体
    m = re.search(
        r"^_archive_partial_chapter\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m, "_archive_partial_chapter 函数体不可解析"
    body = m.group(1)
    assert "MIN_WORDS_HARD" in body, (
        "_archive_partial_chapter 必须用 MIN_WORDS_HARD 作为归档判定阈值"
    )
    assert "recovery_backups" in body, (
        "_archive_partial_chapter 必须把半成品移到 recovery_backups/"
    )


def test_archive_partial_chapter_called_on_retry_and_final_fail():
    """主循环必须在 retry 之前 + 最终失败之前都调 _archive_partial_chapter。

    避免 retry_chapter 看到旧半成品文件错位拼接、避免最终失败时半成品残留误导用户。
    """
    src = _read()
    # 主循环至少出现 3 次调用：retry 前 1 次 + 每轮 retry 后 1 次 + 最终失败前 1 次
    count = src.count("_archive_partial_chapter")
    # 含函数定义自身 1 处 + 调用至少 3 处 = 总数 ≥ 4
    assert count >= 4, (
        f"_archive_partial_chapter 必须至少被调用 3 次（retry 前/每轮失败/最终失败），"
        f"当前在文件中出现 {count} 次（含定义自身 1 次）。"
    )


def test_user_facing_hint_on_final_failure():
    """最终失败时必须给用户明确指引：'再次运行 /ink-auto N 会从第 X 章重新开始'。

    不然小白用户不知道半成品归档了之后还能不能接着写。
    """
    src = _read()
    assert "再次运行" in src and "重新开始" in src, (
        "最终失败时必须打人类可读提示，告诉用户怎么继续"
    )
    assert "partial_chapters" in src, (
        "提示中必须告诉用户半成品归档位置"
    )


# ───────────────────────────────────────────────────────────────
# 3. 卡住检测（write op + 字数 + step 双信号）
# ───────────────────────────────────────────────────────────────


def test_stall_detection_uses_dual_signal():
    """卡住检测必须同时观察"字数无增长" + "workflow step 不变"两个信号。

    单一信号易误杀（LLM 在 Step 1 上下文构建期间不会写章节文件，但软件仍在工作）。
    """
    src = _read()
    assert "INK_AUTO_STALL_THRESHOLD" in src, (
        "必须有 INK_AUTO_STALL_THRESHOLD 环境变量控制卡住阈值"
    )
    assert "stall_since" in src, "必须用 stall_since 时间戳追踪停滞起点"
    assert "size_changed" in src and "step_changed" in src, (
        "必须同时观察字数变化(size_changed) 和 step 变化(step_changed) 两信号"
    )


def test_stall_default_threshold_reasonable():
    """卡住阈值默认值必须在 300-1200 秒之间（5-20 分钟）。

    太短易误杀正常 LLM 思考；太长起不到提前救援作用。
    """
    src = _read()
    m = re.search(r"INK_AUTO_STALL_THRESHOLD:-(\d+)", src)
    assert m, "INK_AUTO_STALL_THRESHOLD 必须有默认值"
    threshold = int(m.group(1))
    assert 300 <= threshold <= 1200, (
        f"卡住阈值 {threshold}s 不在合理范围 [300, 1200]"
    )


def test_stall_triggers_sigterm_via_parent_pid():
    """卡住命中阈值时必须 SIGTERM parent_pid（CHILD_PID）+ 杀同级 LLM 孤儿。"""
    src = _read()
    # parent_pid 必须是 _start_progress_heartbeat 的第 4 参数
    m = re.search(
        r"_start_progress_heartbeat\s*\(\s*\)\s*\{(.*?)^\}",
        src, re.MULTILINE | re.DOTALL,
    )
    assert m, "_start_progress_heartbeat 函数体应可解析"
    body = m.group(1)
    assert 'parent_pid="${4:-' in body, (
        "_start_progress_heartbeat 必须接受第 4 参数 parent_pid"
    )
    # 卡住触发时必须 SIGTERM
    assert 'kill -TERM "$parent_pid"' in body, (
        "卡住命中时必须 SIGTERM parent_pid"
    )


def test_run_cli_process_passes_child_pid_to_heartbeat():
    """run_cli_process 必须把 CHILD_PID 传给心跳作为 parent_pid（用于卡住时 kill）。"""
    src = _read()
    # 三个 platform case 都要传 $CHILD_PID
    pattern = r'_start_progress_heartbeat "\$op" "\$log_file" "\$watch_target" "\$CHILD_PID"'
    matches = re.findall(pattern, src)
    assert len(matches) >= 3, (
        f"_start_progress_heartbeat 必须在 claude/gemini/codex 三个分支都传入 "
        f"\\$CHILD_PID 作为 parent_pid。当前只有 {len(matches)} 处。"
    )


# ───────────────────────────────────────────────────────────────
# 4. 端到端：用 fake claude 模拟 1480 字半成品 + 验归档行为
# ───────────────────────────────────────────────────────────────


def _extract_bash_function(source: str, fn_name: str) -> str:
    pattern = re.compile(
        r"^" + re.escape(fn_name) + r"\s*\(\s*\)\s*\{\s*\n(?P<body>.*?)\n\}\s*\n",
        re.DOTALL | re.MULTILINE,
    )
    m = pattern.search(source)
    if not m:
        raise AssertionError(f"未能抠到 {fn_name} 函数体")
    return f"{fn_name}() {{\n{m.group('body')}\n}}\n"


@pytest.mark.skipif(shutil.which("bash") is None, reason="需要 bash")
def test_archive_partial_chapter_actually_moves_file(tmp_path):
    """端到端：用 1480 字假章节文件触发 _archive_partial_chapter，验证文件被移走。

    验证函数对真实 file system 的行为，不只是源码 grep。
    """
    proj_root = tmp_path / "novel-project"
    (proj_root / "正文").mkdir(parents=True)
    (proj_root / ".ink").mkdir()

    # 1480 字（低于 2200 硬下限）—— 用 1481 个中文字符填充，确保 wc -m ≥ 1481
    short_chap = proj_root / "正文" / "第0002章-一个月的赌约.md"
    short_chap.write_text("一" * 1481, encoding="utf-8")

    # 抠出函数体并运行
    src = _read()
    func_body = _extract_bash_function(src, "_archive_partial_chapter")

    harness = tmp_path / "harness.sh"
    harness.write_text(
        "#!/bin/bash\n"
        "set -uo pipefail\n"
        f'PROJECT_ROOT="{proj_root}"\n'
        "MIN_WORDS_HARD=2200\n"
        f"{func_body}\n"
        '_archive_partial_chapter 2\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", str(harness)],
        capture_output=True, text=True, encoding="utf-8", timeout=10, check=False,
    )

    assert result.returncode == 0, f"归档脚本失败:\nstdout={result.stdout}\nstderr={result.stderr}"
    # 原文件应消失
    assert not short_chap.exists(), "1480 字半成品应被归档移走"
    # recovery_backups 下应有归档文件
    archive_dir = proj_root / ".ink" / "recovery_backups" / "partial_chapters"
    assert archive_dir.is_dir(), f"应创建归档目录 {archive_dir}"
    archived = list(archive_dir.glob("*partial*.md"))
    assert len(archived) == 1, f"应有 1 个归档文件，找到 {len(archived)}"
    # 文件名应含字数提示
    assert "1481字" in archived[0].name, f"归档文件名应含字数标记: {archived[0].name}"


@pytest.mark.skipif(shutil.which("bash") is None, reason="需要 bash")
def test_archive_skips_complete_chapter(tmp_path):
    """完整章节（≥ MIN_WORDS_HARD）不应被归档。"""
    proj_root = tmp_path / "novel-project"
    (proj_root / "正文").mkdir(parents=True)
    (proj_root / ".ink").mkdir()

    # 2500 字—— 完整章节
    full_chap = proj_root / "正文" / "第0001章-完整章节.md"
    full_chap.write_text("一" * 2500, encoding="utf-8")

    src = _read()
    func_body = _extract_bash_function(src, "_archive_partial_chapter")

    harness = tmp_path / "harness.sh"
    harness.write_text(
        "#!/bin/bash\n"
        "set -uo pipefail\n"
        f'PROJECT_ROOT="{proj_root}"\n'
        "MIN_WORDS_HARD=2200\n"
        f"{func_body}\n"
        '_archive_partial_chapter 1\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", str(harness)],
        capture_output=True, text=True, encoding="utf-8", timeout=10, check=False,
    )

    assert result.returncode == 0
    # 完整章节应保留
    assert full_chap.exists(), "完整章节（≥ 2200 字）不应被归档"


def test_bash_syntax_check():
    if shutil.which("bash") is None:
        pytest.skip("需要 bash")
    result = subprocess.run(
        ["bash", "-n", str(INK_AUTO_SH)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode == 0, f"ink-auto.sh 语法失败:\n{result.stderr}"
