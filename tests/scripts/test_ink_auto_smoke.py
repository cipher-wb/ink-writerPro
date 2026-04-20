"""US-012 Windows 端 `ink-auto` 异常专项修复回归。

PRD `cross-platform-audit` US-012 走"扫描 + 加 defensive 日志"退化路径：
  - 在 `ink-auto.sh:run_cli_process` + `ink-auto.ps1:Invoke-CliProcess` 里
    当 CLI 子进程非零退出时打一行 `[ink-auto] llm_exit=<code> tool=<p> log=<path>`
    到 stderr，成功时静默，避免污染正常批量写作的进度流
  - `run_auto_fix` 里 Python 检测 stderr 从 `2>/dev/null` 改为
    `2>>"$LOG_DIR/checkpoint-utils-debug.log"`，Windows 下 Python 崩/import 错可追
  - 源码级红线守护未来 PR 不回退

测试策略：
  - 抠 `run_cli_process` 函数体 + `parse_progress_output` stub（避免依赖完整 ink-auto.sh
    的 .ink/state.json 脚手架）
  - 注入 bash 子 shell 调 `run_cli_process "prompt" "$tmplog"`，fake claude on PATH
    决定退出码，断言 stderr 行为
  - 源码级 grep 断言守护 LLM_EXIT 日志块和 checkpoint-utils-debug.log 重定向不被悄悄改回

与 US-011 `tests/scripts/test_ralph_sh_smoke.py` 的 fake-claude + PATH prepend
模式同构；复用 `_write_fake_claude` 的技巧（cat > /dev/null 吞 stdin、heredoc 多行输出）。
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INK_AUTO_SH = REPO_ROOT / "ink-writer" / "scripts" / "ink-auto.sh"
INK_AUTO_PS1 = REPO_ROOT / "ink-writer" / "scripts" / "ink-auto.ps1"

pytestmark = [
    pytest.mark.skipif(sys.platform == "win32", reason="bash 子 shell 注入测 Unix only"),
    pytest.mark.skipif(shutil.which("bash") is None, reason="需要 bash 可执行"),
]


# ═══════════════════════════════════════════
# bash 函数体抠取：正则匹配整个 function_name() { ... \n} 块
# ═══════════════════════════════════════════
# 与 US-009 test_python_launcher.py:_BASH_FUNC_RE 同构。


def _extract_bash_function(source: str, fn_name: str) -> str:
    """从 source 中抠出形如 `fn_name() { ... \\n}\\n` 的函数体（greedy-until-dedented-brace）。

    匹配约束（依赖 ink-auto.sh 的风格）：
      - 函数定义起始于行首 `fn_name() {`（忽略尾随空格）
      - 结尾 `}` 必须独占一行（行首无缩进）—— ink-auto.sh 所有函数都遵守此风格
    """
    pattern = re.compile(
        r"^" + re.escape(fn_name) + r"\s*\(\s*\)\s*\{\s*\n(?P<body>.*?)\n\}\s*\n",
        re.DOTALL | re.MULTILINE,
    )
    m = pattern.search(source)
    if not m:
        raise AssertionError(f"未能从 ink-auto.sh 抠到 {fn_name} 函数体")
    return f"{fn_name}() {{\n{m.group('body')}\n}}\n"


def _write_fake_claude(dir_: Path, *, stdout: str, exit_code: int = 0) -> Path:
    fake = dir_ / "claude"
    script = (
        "#!/bin/bash\n"
        "# fake claude for ink-auto run_cli_process smoke test\n"
        "# 吞 stdin 防 SIGPIPE（ink-auto 里 claude 不读 stdin，但留保险）\n"
        "cat > /dev/null 2>&1 || true\n"
        f"cat <<'FAKE_CLAUDE_EOF'\n{stdout}\nFAKE_CLAUDE_EOF\n"
        f"exit {int(exit_code)}\n"
    )
    fake.write_text(script, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return fake


def _run_cli_process_in_subshell(
    tmp_path: Path,
    *,
    platform: str = "claude",
    fake_stdout: str = "doing work...\n",
    fake_exit: int = 0,
) -> subprocess.CompletedProcess:
    """构造最小子 shell：注入 run_cli_process + parse_progress_output stub，
    fake CLI on PATH，调 `run_cli_process "prompt" "$tmplog"` 并返回 completed process。
    """
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    run_cli_body = _extract_bash_function(src, "run_cli_process")

    fake_dir = tmp_path / "fake_bin"
    fake_dir.mkdir()
    _write_fake_claude(fake_dir, stdout=fake_stdout, exit_code=fake_exit)

    log_file = tmp_path / "run.log"
    script = (
        "#!/bin/bash\n"
        "set -uo pipefail\n"  # 故意不开 -e，避免测试场景下子 shell 因 LLM 非零退出中途崩
        "CHILD_PID=\"\"\n"
        f"PLATFORM={platform}\n"
        # parse_progress_output stub：读 stdin 原样 append 到 log file（真实实现的简化）
        "parse_progress_output() {\n"
        "    local log_file=\"$1\"\n"
        "    cat >> \"$log_file\"\n"
        "}\n"
        f"{run_cli_body}\n"
        f'run_cli_process "dummy prompt" "{log_file}"\n'
        'echo "[rc=$?]"\n'
    )
    script_file = tmp_path / "harness.sh"
    script_file.write_text(script, encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = f"{fake_dir}{os.pathsep}{env.get('PATH', '')}"

    return subprocess.run(
        ["bash", str(script_file)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        env=env,
        check=False,
    )


# ───────────────────────────────────────────────────────────────
# 场景 A: fake claude exit 0 → 无 LLM_EXIT 日志（静默成功）
# ───────────────────────────────────────────────────────────────


def test_run_cli_process_silent_on_success(tmp_path):
    """CLI 子进程 exit 0 时，run_cli_process 不应打 `[ink-auto] llm_exit=` 到 stderr。

    防止"成功时也打日志"污染正常批量写作的进度输出。
    """
    result = _run_cli_process_in_subshell(tmp_path, fake_exit=0)

    combined = result.stdout + result.stderr
    # rc 应为 0（子 shell 里 run_cli_process 透传 exit_code）
    assert "[rc=0]" in result.stdout, f"期望 rc=0，实际 output:\n{combined}"
    assert "[ink-auto] llm_exit=" not in combined, (
        "CLI 成功时不应打 llm_exit 日志。\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ───────────────────────────────────────────────────────────────
# 场景 B: fake claude exit 非 0 → stderr 有 LLM_EXIT 日志
# ───────────────────────────────────────────────────────────────


def test_run_cli_process_logs_exit_code_on_failure(tmp_path):
    """CLI 子进程 exit 17 时，run_cli_process 必须打
    `[ink-auto] llm_exit=17 tool=claude log=<path>` 到 stderr。

    US-012 核心验收：Windows 端 ink-auto 崩溃时不再静默。
    """
    result = _run_cli_process_in_subshell(tmp_path, fake_exit=17)

    # run_cli_process 应透传 17 作为 return
    assert "[rc=17]" in result.stdout, f"期望 rc=17，实际 output:\n{result.stdout}"
    # stderr 必须出现格式化的 llm_exit 日志
    assert "[ink-auto] llm_exit=17 tool=claude" in result.stderr, (
        "run_cli_process 非零退出时必须打 LLM_EXIT 日志到 stderr。\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # log= 字段应指向 harness 传入的 log file（证明上下文完整）
    assert "log=" in result.stderr
    assert "run.log" in result.stderr


# ───────────────────────────────────────────────────────────────
# 场景 C: 多个 PLATFORM 值（gemini/codex）的日志对等
# ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("platform", ["claude", "gemini", "codex"])
def test_run_cli_process_logs_for_all_platforms(tmp_path, platform):
    """gemini / codex 分支也必须走同一条 defensive 日志（case 结束后统一打）。

    守护未来新增 CLI 平台时如果在分支内 return 提前退出会漏掉日志。
    """
    # gemini 分支用 `echo "$prompt" | gemini --yolo`，codex 用 `codex --approval-mode`
    # 三个都 fake 为同一 shim 命名
    fake_dir = tmp_path / "fake_bin"
    fake_dir.mkdir()
    fake = fake_dir / platform
    fake.write_text(
        "#!/bin/bash\n"
        "cat > /dev/null 2>&1 || true\n"
        "echo 'fake output'\n"
        "exit 23\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    src = INK_AUTO_SH.read_text(encoding="utf-8")
    run_cli_body = _extract_bash_function(src, "run_cli_process")
    log_file = tmp_path / "run.log"
    script = (
        "#!/bin/bash\n"
        "set -uo pipefail\n"
        "CHILD_PID=\"\"\n"
        f"PLATFORM={platform}\n"
        "parse_progress_output() { cat >> \"$1\"; }\n"
        f"{run_cli_body}\n"
        f'run_cli_process "dummy" "{log_file}"\n'
        'echo "[rc=$?]"\n'
    )
    script_file = tmp_path / "harness.sh"
    script_file.write_text(script, encoding="utf-8")
    env = os.environ.copy()
    env["PATH"] = f"{fake_dir}{os.pathsep}{env.get('PATH', '')}"

    result = subprocess.run(
        ["bash", str(script_file)],
        capture_output=True, text=True, encoding="utf-8",
        timeout=15, env=env, check=False,
    )

    assert "[rc=23]" in result.stdout
    assert f"[ink-auto] llm_exit=23 tool={platform}" in result.stderr, (
        f"{platform} 分支非零退出也必须打 LLM_EXIT 日志。\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ───────────────────────────────────────────────────────────────
# 源码级红线：守护 LLM_EXIT 块 + checkpoint-utils 重定向
# ───────────────────────────────────────────────────────────────


def test_ink_auto_sh_has_llm_exit_log_block():
    """ink-auto.sh `run_cli_process` 必须含 `[ink-auto] llm_exit=` 日志块 + `>&2` 重定向。

    守护未来 PR 把 defensive 日志改回 silent 模式。
    """
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    run_cli_body = _extract_bash_function(src, "run_cli_process")
    assert "[ink-auto] llm_exit=" in run_cli_body, (
        "run_cli_process 必须含 `[ink-auto] llm_exit=` defensive 日志"
    )
    assert ">&2" in run_cli_body, (
        "defensive 日志必须重定向到 stderr（`>&2`），避免污染 stdout"
    )
    # 必须 gate 在 exit_code != 0 条件下（不能每次都打）
    assert "exit_code != 0" in run_cli_body, (
        "defensive 日志必须 gate 在 `exit_code != 0`，成功时静默"
    )


def test_ink_auto_sh_checkpoint_utils_stderr_not_swallowed():
    """`run_auto_fix` 里的 Python 检测 stderr 必须重定向到 debug 日志，不再 `2>/dev/null`。

    Windows 下 Python 崩溃/import 错误/编码问题可追踪；是 US-012 的 Windows 关键诊断增强。
    """
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    # 关键句：必须包含 checkpoint-utils-debug.log 重定向片段
    assert 'checkpoint-utils-debug.log' in src, (
        "run_auto_fix 的 Python 检测 stderr 必须重定向到 "
        "`$LOG_DIR/checkpoint-utils-debug.log`，不能再 `2>/dev/null` 静默"
    )
    # 守护：report_has_issues 调用旁边不再出现裸 `2>/dev/null`
    # （采用窗口扫描：找每一处 report_has_issues 所在行及其前后 3 行的上下文）
    for m in re.finditer(r"report_has_issues", src):
        start = max(0, src.rfind("\n", 0, m.start() - 200))
        end = src.find("\n", m.end() + 200)
        ctx = src[start:end if end != -1 else len(src)]
        assert "2>/dev/null" not in ctx, (
            f"report_has_issues 附近不应再有 `2>/dev/null` 吞 stderr，实际上下文:\n{ctx}"
        )


def test_ink_auto_sh_has_set_euo_pipefail():
    """ink-auto.sh 顶部必须 `set -euo pipefail`——US-011 已确认是 long-running agent loop 必备。

    pipefail 让 `claude | parse_progress_output` 的 claude 非零退出在 `wait` 之前被捕获。
    """
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    assert "set -euo pipefail" in src, (
        "ink-auto.sh 必须开启 `set -euo pipefail`（long-running agent loop 的 stderr 吞吐约束）"
    )


# ───────────────────────────────────────────────────────────────
# .ps1 源码级对等守护
# ───────────────────────────────────────────────────────────────


def test_ink_auto_ps1_has_llm_exit_log_block():
    """ink-auto.ps1 `Invoke-CliProcess` 必须含 `[ink-auto] llm_exit=` 日志 + stderr 写入。

    与 ink-auto.sh 对等：exitCode != 0 时通过 `[Console]::Error.WriteLine` 打到 stderr。
    """
    ps1 = INK_AUTO_PS1.read_text(encoding="utf-8")
    assert "Invoke-CliProcess" in ps1
    assert "[ink-auto] llm_exit=" in ps1, (
        "ink-auto.ps1:Invoke-CliProcess 必须含 `[ink-auto] llm_exit=` defensive 日志"
    )
    assert "[Console]::Error" in ps1, (
        "PowerShell defensive 日志必须通过 `[Console]::Error.WriteLine` 写到 stderr"
    )
    assert "$exitCode -ne 0" in ps1, (
        "ps1 defensive 日志必须 gate 在 `$exitCode -ne 0`，成功时静默"
    )


def test_ink_auto_ps1_has_utf8_bom():
    """PS 5.1 默认 ANSI 解码 .ps1——UTF-8 BOM 必须保留（US-007 Codebase Pattern）。"""
    head = INK_AUTO_PS1.read_bytes()[:3]
    assert head == b"\xef\xbb\xbf", (
        f"ink-auto.ps1 必须以 UTF-8 BOM 开头，实际前 3 字节：{head!r}"
    )
