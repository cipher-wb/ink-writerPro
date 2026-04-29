"""ink-auto.sh v27 状态分发回归测试（针对历史 R1/R3 bug）

历史 bug 描述：
  - R1: ink-auto.sh 调用 `auto_plan_volume` 但全脚本没定义此函数
        → bash 报 `auto_plan_volume: command not found` → set -e exit 1
        → v27 路径（空目录+蓝本.md → /ink-auto N）100% 触发；S1 路径同样命中
  - R3: 顶层 if 块内使用 `local` 变量声明（line 931 的 `local _vol`、
        line 522 的 `local _plan_vol _plan_vols _last_plan_vol`）
        → bash 报 `local: can only be used in a function` → set -e exit

本测试守护两条不变量：
  1. `auto_plan_volume` 函数必须在脚本中有定义
  2. 所有调用 auto_plan_volume / run_cli_process 的代码必须在
     函数体内部，而不是顶层内联代码（顶层内联代码在脚本逐行执行时
     可能引用到尚未定义的后置函数）

实现策略：源码级静态扫描 + AST-like 函数边界追踪。本测试无需真实
跑 ink-auto.sh，避免依赖 .ink/state.json 脚手架。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INK_AUTO_SH = REPO_ROOT / "ink-writer" / "scripts" / "ink-auto.sh"


def _list_functions(source: str) -> list[tuple[str, int, int]]:
    """返回 [(fname, start_line, end_line), ...]。

    依赖 ink-auto.sh 的格式约定：
      - 函数定义起始于行首 `name() {`
      - 函数体结尾 `}` 独占一行（行首无缩进）

    与 tests/scripts/test_ink_auto_smoke.py:_extract_bash_function 同构。
    """
    lines = source.splitlines()
    funcs: list[tuple[str, int, int]] = []
    i = 0
    while i < len(lines):
        m = re.match(r"^([a-zA-Z_][a-zA-Z_0-9]*)\s*\(\s*\)\s*\{\s*$", lines[i])
        if m:
            fname = m.group(1)
            start = i + 1  # 1-based
            # 寻找配对的右大括号（必须独占一行、无缩进）
            j = i + 1
            while j < len(lines):
                if lines[j].rstrip() == "}":
                    funcs.append((fname, start, j + 1))
                    i = j + 1
                    break
                j += 1
            else:
                # 没找到收尾，跳过
                i += 1
        else:
            i += 1
    return funcs


def _line_in_any_function(funcs: list[tuple[str, int, int]], lineno: int) -> str | None:
    """返回包含 lineno 的函数名；不在任何函数内则返回 None。"""
    for fname, start, end in funcs:
        if start <= lineno <= end:
            return fname
    return None


def test_auto_plan_volume_is_defined():
    """auto_plan_volume 必须有函数定义体；否则 v27 / S1 路径调用时 bash 报 command not found。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    funcs = _list_functions(src)
    fnames = {f[0] for f in funcs}
    assert "auto_plan_volume" in fnames, (
        "ink-auto.sh 必须定义 auto_plan_volume 函数。\n"
        "历史 bug：调用点 line 535/933 引用了从未定义的函数，导致空目录 /ink-auto 必挂。\n"
        f"当前发现的函数（前 30 个）：{sorted(fnames)[:30]}"
    )


def test_v27_init_function_defined():
    """v27 自动 init 逻辑必须在函数体内（_v27_init_if_needed），不能是顶层内联代码。

    顶层内联代码会在 bash 逐行执行时引用尚未定义的 auto_plan_volume / run_cli_process。
    """
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    funcs = _list_functions(src)
    fnames = {f[0] for f in funcs}
    assert "_v27_init_if_needed" in fnames, (
        "ink-auto.sh 必须用 _v27_init_if_needed() 函数包裹 v27 自动 init 逻辑，\n"
        "并在所有函数定义后调用，确保 auto_plan_volume / run_cli_process 已就位。\n"
        "历史 bug：顶层内联代码 (line 826-945) 引用未定义函数。"
    )


def test_s1_outline_precheck_function_defined():
    """S1 大纲预检逻辑必须在函数体内（_s1_outline_precheck_if_root）。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    funcs = _list_functions(src)
    fnames = {f[0] for f in funcs}
    assert "_s1_outline_precheck_if_root" in fnames, (
        "ink-auto.sh 必须用 _s1_outline_precheck_if_root() 函数包裹 S1 大纲预检逻辑。"
    )


def test_no_top_level_call_to_auto_plan_volume():
    """auto_plan_volume 的所有调用必须在函数体内（不能在顶层内联代码）。

    顶层调用是历史 R1 bug 的根源（bash 在执行时函数尚未定义）。
    """
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    funcs = _list_functions(src)

    offenders: list[tuple[int, str]] = []
    for lineno, line in enumerate(src.splitlines(), start=1):
        # 跳过定义行本身和注释行
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if re.match(r"^\s*auto_plan_volume\s*\(\s*\)\s*\{", line):
            continue
        # 检查是否真的调用（前缀允许 `if`、`&&`、空白等）
        if re.search(r"(?<![a-zA-Z_])auto_plan_volume\b", line):
            container = _line_in_any_function(funcs, lineno)
            if container is None:
                offenders.append((lineno, line.rstrip()))

    assert not offenders, (
        "auto_plan_volume 不能在顶层内联代码处调用（bash 执行时函数尚未定义）。\n"
        "请把调用点包到一个函数体里，并在所有函数定义后再调用该函数。\n"
        "顶层调用位置：\n"
        + "\n".join(f"  line {ln}: {text}" for ln, text in offenders)
    )


def test_no_top_level_local_keyword():
    """`local` 关键字必须在函数体内使用，否则 bash 报 'can only be used in a function'。

    历史 R3 bug：line 522 / 931 在顶层 if 块内用了 local，set -e 触发 exit。
    """
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    funcs = _list_functions(src)

    offenders: list[tuple[int, str]] = []
    for lineno, line in enumerate(src.splitlines(), start=1):
        # 跳过注释、字符串内文档（粗匹配）
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if not re.match(r"^\s*local\s+", line):
            continue
        container = _line_in_any_function(funcs, lineno)
        if container is None:
            offenders.append((lineno, line.rstrip()))

    assert not offenders, (
        "`local` 关键字只能在函数体内使用。\n"
        "顶层使用位置：\n"
        + "\n".join(f"  line {ln}: {text}" for ln, text in offenders)
    )


def test_main_dispatch_calls_in_correct_order():
    """主流程必须先调 _v27_init_if_needed，再调 _s1_outline_precheck_if_root。

    顺序约束：v27 可能创建项目（改变 PROJECT_ROOT），之后 S1 才能基于新状态做大纲预检。
    且这两个调用必须在所有函数定义之后（在主循环 / 并发分发之前）。
    """
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    funcs = _list_functions(src)

    v27_calls: list[int] = []
    s1_calls: list[int] = []
    for lineno, line in enumerate(src.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # 排除函数定义本身
        if re.match(r"^_v27_init_if_needed\s*\(\s*\)", stripped):
            continue
        if re.match(r"^_s1_outline_precheck_if_root\s*\(\s*\)", stripped):
            continue
        # 真正的顶层调用（不在任何函数体内 + 行首即函数名）
        if stripped == "_v27_init_if_needed" and _line_in_any_function(funcs, lineno) is None:
            v27_calls.append(lineno)
        elif stripped == "_s1_outline_precheck_if_root" and _line_in_any_function(funcs, lineno) is None:
            s1_calls.append(lineno)

    assert v27_calls, "主流程必须有 _v27_init_if_needed 调用"
    assert s1_calls, "主流程必须有 _s1_outline_precheck_if_root 调用"
    assert v27_calls[0] < s1_calls[0], (
        f"_v27_init_if_needed (line {v27_calls[0]}) 必须在 "
        f"_s1_outline_precheck_if_root (line {s1_calls[0]}) 之前调用"
    )

    # 这两个调用必须在所有函数定义之后
    last_func_end = max(f[2] for f in funcs)
    assert v27_calls[0] > last_func_end, (
        f"_v27_init_if_needed 调用 (line {v27_calls[0]}) 必须在所有函数定义之后 "
        f"(最后函数结尾 line {last_func_end})。否则 auto_plan_volume / run_cli_process "
        f"等被引用的函数尚未就位。"
    )


def test_run_cli_process_accepts_per_call_timeout():
    """run_cli_process 必须接受第 3 个参数作为 per-call timeout，否则 plan/init/write 三种
    操作只能共用一个 INK_AUTO_CHAPTER_TIMEOUT，ink-plan 整卷大纲必然超时。

    历史 bug：用户实测 2026-04-29，ink-plan 跑 30+ 章纲耗时 > 1200s 默认值，
              watchdog 杀进程导致"自动化"中断。
    """
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    # 必须有 ${3:-...} 模式表明接受第 3 个参数
    assert re.search(r'timeout_s="\$\{3:-', src), (
        "run_cli_process 必须支持第 3 个参数覆盖默认 timeout，"
        "否则 plan/init/write 不能各用各的超时档。"
    )


def test_plan_caller_passes_explicit_plan_timeout():
    """auto_plan_volume / auto_generate_outline 调用 run_cli_process 时必须显式传 plan 档超时。

    plan 操作的内在耗时上限远超普通 chapter（30+ 章纲 vs 1 章），
    复用 INK_AUTO_CHAPTER_TIMEOUT 必然撞南墙。
    """
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    # 必须出现 INK_AUTO_PLAN_TIMEOUT
    assert "INK_AUTO_PLAN_TIMEOUT" in src, (
        "ink-auto.sh 必须定义/使用 INK_AUTO_PLAN_TIMEOUT 给 ink-plan 调用更长超时"
    )
    # plan 调用点至少 1 处把 plan 超时作为 run_cli_process 第 3 个参数传入
    assert re.search(
        r'run_cli_process\s+"[^"]*"\s+"[^"]*"\s+"\$\{INK_AUTO_PLAN_TIMEOUT:-\d+\}"',
        src,
    ), "plan 类调用 run_cli_process 时必须显式传 INK_AUTO_PLAN_TIMEOUT 作为第 3 个参数"


def test_init_caller_passes_explicit_init_timeout():
    """v27 init 调用必须显式传 INK_AUTO_INIT_TIMEOUT。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    assert "INK_AUTO_INIT_TIMEOUT" in src, (
        "ink-auto.sh 必须定义/使用 INK_AUTO_INIT_TIMEOUT 给 ink-init 调用合理超时"
    )


def test_watchdog_kills_orphan_llm_subprocess():
    """watchdog 触发时必须同时清理孤儿 LLM CLI 子进程（claude/gemini/codex），
    不只是 pipeline 末端的 parse_progress_output。

    历史 bug：原 watchdog 只 kill 末端 PID，pipeline 头部的 LLM 进程继续作为孤儿
    跑，浪费 token 还可能阻塞下一章。
    """
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    # 必须用 pkill -P 杀 target_pid 的子进程（claude 是 parse_progress_output 的兄弟，
    # 不是子进程，所以还需要 INK_AUTO_PID 路径）
    assert "pkill -TERM -P" in src or "pkill -KILL -P" in src, (
        "watchdog 必须用 pkill -P 杀子进程，避免 LLM 进程变孤儿"
    )
    assert "INK_AUTO_PID" in src, (
        "ink-auto.sh 必须暴露 INK_AUTO_PID（脚本自身 PID）给 watchdog 用于"
        "清理跟 ink-auto.sh 同级的 LLM CLI 子代"
    )


def test_default_timeouts_are_sane():
    """默认超时值必须合理：write ≥ 1800s，plan ≥ 3600s，init ≥ 1800s。

    1200s 在真实场景已被验证过短（2026-04-29 用户实测）。
    """
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    # write 默认（INK_AUTO_CHAPTER_TIMEOUT or 兜底）
    write_match = re.search(r'INK_AUTO_CHAPTER_TIMEOUT:-(\d+)', src)
    assert write_match, "需要 INK_AUTO_CHAPTER_TIMEOUT 默认值"
    assert int(write_match.group(1)) >= 1800, (
        f"INK_AUTO_CHAPTER_TIMEOUT 默认 {write_match.group(1)}s 太短，至少 1800s。"
    )

    plan_match = re.search(r'INK_AUTO_PLAN_TIMEOUT:-(\d+)', src)
    assert plan_match, "需要 INK_AUTO_PLAN_TIMEOUT 默认值"
    assert int(plan_match.group(1)) >= 3600, (
        f"INK_AUTO_PLAN_TIMEOUT 默认 {plan_match.group(1)}s 太短，至少 3600s。"
    )

    init_match = re.search(r'INK_AUTO_INIT_TIMEOUT:-(\d+)', src)
    assert init_match, "需要 INK_AUTO_INIT_TIMEOUT 默认值"
    assert int(init_match.group(1)) >= 1800, (
        f"INK_AUTO_INIT_TIMEOUT 默认 {init_match.group(1)}s 太短，至少 1800s。"
    )


def test_bash_syntax_check():
    """整个 ink-auto.sh 必须通过 `bash -n` 语法检查。"""
    import shutil
    import subprocess

    if shutil.which("bash") is None:
        import pytest
        pytest.skip("需要 bash 可执行")

    result = subprocess.run(
        ["bash", "-n", str(INK_AUTO_SH)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, (
        f"ink-auto.sh 语法检查失败:\n{result.stderr}"
    )
