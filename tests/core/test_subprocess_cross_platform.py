"""tests/core/test_subprocess_cross_platform.py — US-004 跨平台 subprocess 验证。

覆盖 CLAUDE.md "Windows 兼容守则" 中关于 subprocess 调用的约束：

1. **文本模式必须显式 encoding="utf-8"**：Windows 默认 cp936 解码会乱码。
2. **中文参数 / 中文 cwd 路径透传**：subprocess 必须能正确传中文参数到子进程，
   并把子进程 stdout 的中文按 UTF-8 解码回来。
3. **args 列表传递（避免 shell=True）**：带空格路径用 args 列表不会被 shell 拆词。
4. **仓库自身正向断言**：扫描仓库内所有 subprocess 文本模式调用，确保 100% 带
   encoding="utf-8"——这是 US-004 修完之后的不可回退红线。

所有测试在 Mac / Windows 都能跑（Windows-only 行为用 sys.platform 守卫）。
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_cross_platform import (  # noqa: E402
    EXCLUDE_DIR_NAMES,
    _is_text_mode_subprocess,
    _kw_value,
    _resolve_call_target,
    iter_files,
    safe_read_text,
)


SUBPROCESS_TARGETS = {
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.check_output",
    "subprocess.check_call",
    "subprocess.call",
}


# ---------------------------------------------------------------------------
# 1. 中文参数透传 + UTF-8 解码
# ---------------------------------------------------------------------------


def test_subprocess_run_passes_chinese_arg_via_args_list() -> None:
    """中文参数走 args 列表，子进程能原样接收，stdout UTF-8 解码无乱码。"""
    chinese = "你好世界_测试"
    code = (
        "import sys; sys.stdout.reconfigure(encoding='utf-8'); "
        f"print({chinese!r})"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0
    assert chinese in result.stdout


def test_subprocess_run_chinese_cwd(tmp_path: Path) -> None:
    """cwd 是中文目录时 subprocess 能正常启动。"""
    cwd = tmp_path / "中文工作目录"
    cwd.mkdir()
    result = subprocess.run(
        [sys.executable, "-c", "import os; print(os.getcwd())"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0
    assert "中文工作目录" in result.stdout


# ---------------------------------------------------------------------------
# 2. 带空格路径必须走 args 列表（防 shell=True 拆词）
# ---------------------------------------------------------------------------


def test_subprocess_args_list_preserves_spaces_in_path(tmp_path: Path) -> None:
    """args 列表传带空格的脚本路径不被拆开（shell=True 字符串会拆）。"""
    spaced_dir = tmp_path / "Application Support" / "ink writer"
    spaced_dir.mkdir(parents=True)
    script = spaced_dir / "echo arg.py"
    script.write_text(
        "import sys; sys.stdout.reconfigure(encoding='utf-8'); print('OK', sys.argv[1])",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(script), "带空格 参数"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
    assert "带空格 参数" in result.stdout


# ---------------------------------------------------------------------------
# 3. encoding="utf-8" 显式参数防止 Windows cp936 误解码
# ---------------------------------------------------------------------------


def test_subprocess_decodes_utf8_stdout_on_any_platform() -> None:
    """子进程输出 UTF-8 字节，主进程指定 encoding='utf-8' 必能正确解码。
    这是 Windows cp936 默认 locale 下唯一不乱码的写法。"""
    payload = "中文_𝒂𝒃𝒄_emoji🎯"
    code = (
        "import sys, io; "
        "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8'); "
        f"print({payload!r})"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0
    assert payload in result.stdout


def test_subprocess_check_output_with_explicit_encoding() -> None:
    """check_output 的文本模式同样需要显式 encoding。"""
    payload = "你好"
    code = (
        "import sys, io; "
        "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8'); "
        f"print({payload!r})"
    )
    out = subprocess.check_output(
        [sys.executable, "-c", code],
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert payload in out


# ---------------------------------------------------------------------------
# 4. 仓库自身正向断言（红线测试）
# ---------------------------------------------------------------------------


def _collect_text_mode_subprocess_calls_missing_encoding() -> list[tuple[Path, int]]:
    offenders: list[tuple[Path, int]] = []
    # 排除 audit/fix 脚本自身（其 fixture/示例代码故意演示反例）
    skip_files = {
        REPO_ROOT / "tests" / "audit" / "test_audit_cross_platform.py",
        REPO_ROOT / "tests" / "audit" / "test_fix_subprocess_encoding.py",
        REPO_ROOT / "tests" / "core" / "test_subprocess_cross_platform.py",
    }
    for path in iter_files(REPO_ROOT, (".py",)):
        if path.resolve() in {p.resolve() for p in skip_files}:
            continue
        src = safe_read_text(path)
        if not src:
            continue
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _resolve_call_target(node) not in SUBPROCESS_TARGETS:
                continue
            if not _is_text_mode_subprocess(node):
                continue
            if _kw_value(node, "encoding") is None:
                offenders.append((path, node.lineno))
    return offenders


def test_repo_has_no_text_mode_subprocess_without_encoding() -> None:
    """红线：US-004 修完之后，仓库内所有 subprocess.run/Popen/... 文本模式
    调用必须显式带 encoding=（不是只在 fix 后扫描，而是后续 PR 引入新违规
    会在 CI 直接挂掉）。"""
    offenders = _collect_text_mode_subprocess_calls_missing_encoding()
    if offenders:
        msg_lines = [f"  {path.relative_to(REPO_ROOT)}:{lineno}" for path, lineno in offenders]
        pytest.fail(
            "仓库内仍有 subprocess 文本模式调用未带 encoding=\n"
            + "\n".join(msg_lines)
        )


def test_repo_has_no_subprocess_shell_true() -> None:
    """红线：禁用 shell=True（Windows 引号/中文地狱）。当前仓库已无该用法，
    本测试守住后续不再引入。"""
    offenders: list[tuple[Path, int]] = []
    skip_files = {
        REPO_ROOT / "scripts" / "audit_cross_platform.py",  # scanner 自我检测代码
        REPO_ROOT / "tests" / "audit" / "test_audit_cross_platform.py",  # fixture
        REPO_ROOT / "tests" / "core" / "test_subprocess_cross_platform.py",  # 本文件
        REPO_ROOT / "tests" / "core" / "test_path_cross_platform.py",  # docstring 提及
    }
    for path in iter_files(REPO_ROOT, (".py",)):
        if path.resolve() in {p.resolve() for p in skip_files}:
            continue
        src = safe_read_text(path)
        if not src:
            continue
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _resolve_call_target(node) not in SUBPROCESS_TARGETS:
                continue
            shell_kw = _kw_value(node, "shell")
            if isinstance(shell_kw, ast.Constant) and shell_kw.value is True:
                offenders.append((path, node.lineno))
    if offenders:
        lines = [f"  {p.relative_to(REPO_ROOT)}:{ln}" for p, ln in offenders]
        pytest.fail("仓库内禁止 shell=True，请改为 args 列表：\n" + "\n".join(lines))
