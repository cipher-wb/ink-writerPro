#!/usr/bin/env python3
"""fix_subprocess_encoding.py — 批量补齐 ``subprocess.run/Popen/...`` 的
``encoding="utf-8"`` 参数（US-004）。

行为：
- 复用 ``audit_cross_platform`` 的 ``_resolve_call_target`` / ``_kw_value`` /
  ``_is_text_mode_subprocess`` 判定，只改"文本模式但缺 encoding"的真实 finding。
- 基于 AST 的精确插入：在最后一个 positional arg 或 keyword 之后追加
  ``, encoding="utf-8"``，无论调用是单行还是多行均可处理（不动关闭括号）。
- 不动二进制模式（无 text/universal_newlines/encoding 关键字时不视为文本模式）。
- 不动已有 ``encoding=`` 的调用 → **幂等**：第二次运行无 diff。
- ``shell=True`` 的修复策略不在本 fixer 范围（需人工把字符串拆成 args 列表）。

使用：

    python3 scripts/fix_subprocess_encoding.py                 # 修当前仓库
    python3 scripts/fix_subprocess_encoding.py --root <path>   # 指定根目录
    python3 scripts/fix_subprocess_encoding.py --dry-run       # 只报告，不写回

只用 stdlib。
"""

from __future__ import annotations

# Windows UTF-8 stdio：Mac no-op
import os as _os_win_stdio
import sys as _sys_win_stdio

_INK_SCRIPTS = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    "..",
    "ink-writer",
    "scripts",
)
if _os_win_stdio.path.isdir(_INK_SCRIPTS) and _INK_SCRIPTS not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _INK_SCRIPTS)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass

import argparse
import ast
from pathlib import Path
from typing import Iterable, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, str(SCRIPT_DIR))

from audit_cross_platform import (  # noqa: E402
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


def _needs_encoding(call: ast.Call) -> bool:
    target = _resolve_call_target(call)
    if target not in SUBPROCESS_TARGETS:
        return False
    if not _is_text_mode_subprocess(call):
        return False
    if _kw_value(call, "encoding") is not None:
        return False
    return True


def _last_arg_position(call: ast.Call) -> Optional[tuple[int, int]]:
    """返回 (end_lineno, end_col_offset)，定位最后一个 positional arg 或 keyword
    value 的末尾。无任何 args/keywords 时返回 None（理论上 _is_text_mode_subprocess
    要求至少一个 keyword，但保险起见保留判空）。"""
    candidates: list[tuple[int, int]] = []
    for arg in call.args:
        end_lineno = getattr(arg, "end_lineno", None)
        end_col = getattr(arg, "end_col_offset", None)
        if end_lineno is not None and end_col is not None:
            candidates.append((end_lineno, end_col))
    for kw in call.keywords:
        value = kw.value
        end_lineno = getattr(value, "end_lineno", None)
        end_col = getattr(value, "end_col_offset", None)
        if end_lineno is not None and end_col is not None:
            candidates.append((end_lineno, end_col))
    if not candidates:
        return None
    return max(candidates)


def fix_file(path: Path, dry_run: bool = False) -> list[int]:
    """返回本文件被修复的行号列表（按 call 起始行排序）。"""
    src = safe_read_text(path)
    if not src:
        return []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []

    lines = src.splitlines(keepends=True)
    edits: list[tuple[int, int, int]] = []  # (line_idx, col, lineno_for_report)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _needs_encoding(node):
            continue
        pos = _last_arg_position(node)
        if pos is None:
            continue
        end_lineno, end_col = pos
        line_idx = end_lineno - 1
        if line_idx < 0 or line_idx >= len(lines):
            continue
        edits.append((line_idx, end_col, node.lineno))

    if not edits:
        return []

    report_lines = sorted({lineno for _, _, lineno in edits})
    if dry_run:
        return report_lines

    # 从后向前应用，避免 offset 漂移
    edits.sort(key=lambda x: (-x[0], -x[1]))
    for line_idx, col, _ in edits:
        line = lines[line_idx]
        if col > len(line.rstrip("\r\n")):
            # 异常 offset，跳过保守
            continue
        lines[line_idx] = line[:col] + ', encoding="utf-8"' + line[col:]
    path.write_text("".join(lines), encoding="utf-8")
    return report_lines


def iter_py_files(root: Path) -> Iterable[Path]:
    yield from iter_files(root, (".py",))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description='幂等补齐 subprocess.run/Popen/... 的 encoding="utf-8" (US-004)',
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="仓库根目录（默认自动推导）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只报告会修复的位置，不写回",
    )
    args = parser.parse_args(argv)

    root: Path = args.root.resolve()
    if not root.is_dir():
        print(
            f"[fix_subprocess_encoding] root 不存在或不是目录: {root}",
            file=_sys_win_stdio.stderr,
        )
        return 2

    touched: list[tuple[Path, list[int]]] = []
    for py in iter_py_files(root):
        if py.resolve() == Path(__file__).resolve():
            continue
        lines = fix_file(py, dry_run=args.dry_run)
        if lines:
            touched.append((py, lines))

    action = "would fix" if args.dry_run else "fixed"
    total = sum(len(lines) for _, lines in touched)
    print(
        f"[fix_subprocess_encoding] {action} {total} call(s) in {len(touched)} file(s)",
    )
    for py, lines in touched:
        try:
            rel = py.resolve().relative_to(root)
        except ValueError:
            rel = py
        for ln in lines:
            print(f"  {rel}:{ln}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
