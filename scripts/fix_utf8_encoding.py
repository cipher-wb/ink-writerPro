#!/usr/bin/env python3
"""fix_utf8_encoding.py — 批量补齐 ``open()`` / ``read_text()`` / ``write_text()``
的 ``encoding="utf-8"`` 参数（US-002）。

行为：
- 复用 ``audit_cross_platform.scan_c1_open_encoding`` 的判定逻辑，只改真正缺
  encoding 的文本模式调用。
- 基于 AST 的精确插入（``end_col_offset``）——不碰行内其他字符，不改格式。
- 多行调用、接收者为非文件 I/O（webbrowser.open 等）、二进制模式、已有 encoding 均跳过。
- **幂等**：第二次运行无 diff（因为首次修完后 ``_has_encoding_kw`` 全部返回 True）。

使用：

    python3 scripts/fix_utf8_encoding.py                 # 修当前仓库
    python3 scripts/fix_utf8_encoding.py --root <path>   # 指定根目录
    python3 scripts/fix_utf8_encoding.py --dry-run       # 只报告，不写回

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
    EXCLUDE_DIR_NAMES,
    _call_func_name,
    _has_encoding_kw,
    _is_binary_mode,
    _is_non_file_open_call,
    iter_files,
    safe_read_text,
)


TARGETS = {"open", "read_text", "write_text"}


def _needs_encoding(call: ast.Call) -> bool:
    name = _call_func_name(call)
    if name not in TARGETS:
        return False
    if name == "open" and _is_binary_mode(call):
        return False
    if name == "open" and _is_non_file_open_call(call):
        return False
    if _has_encoding_kw(call):
        return False
    return True


def fix_file(path: Path, dry_run: bool = False) -> list[int]:
    """返回本文件被修复的行号列表（按出现顺序）。"""
    src = safe_read_text(path)
    if not src:
        return []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []

    lines = src.splitlines(keepends=True)
    # 收集 (end_line_idx, end_col, has_args, lineno_for_report)
    edits: list[tuple[int, int, bool, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _needs_encoding(node):
            continue
        end_lineno = getattr(node, "end_lineno", None)
        end_col = getattr(node, "end_col_offset", None)
        if end_lineno is None or end_col is None:
            continue
        # 保守：仅处理单行调用；多行调用留给后续人工审查
        if node.lineno != end_lineno:
            continue
        line_idx = end_lineno - 1
        if line_idx >= len(lines):
            continue
        line = lines[line_idx]
        if end_col < 1 or line[end_col - 1] != ")":
            # 可能被注释/尾随字符干扰，跳过
            continue
        has_args = bool(node.args) or bool(node.keywords)
        edits.append((line_idx, end_col - 1, has_args, node.lineno))

    if not edits:
        return []

    # 从后向前应用，避免 offset 漂移
    report_lines = sorted({e[3] for e in edits})
    if dry_run:
        return report_lines
    edits.sort(key=lambda x: (-x[0], -x[1]))
    for line_idx, col, has_args, _ in edits:
        line = lines[line_idx]
        insertion = ', encoding="utf-8"' if has_args else 'encoding="utf-8"'
        lines[line_idx] = line[:col] + insertion + line[col:]
    path.write_text("".join(lines), encoding="utf-8")
    return report_lines


def iter_py_files(root: Path) -> Iterable[Path]:
    yield from iter_files(root, (".py",))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="幂等补齐 open/read_text/write_text 的 encoding=utf-8 (US-002)",
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
        print(f"[fix_utf8_encoding] root 不存在或不是目录: {root}", file=_sys_win_stdio.stderr)
        return 2

    touched: list[tuple[Path, list[int]]] = []
    for py in iter_py_files(root):
        # 跳过本脚本自身
        if py.resolve() == Path(__file__).resolve():
            continue
        lines = fix_file(py, dry_run=args.dry_run)
        if lines:
            touched.append((py, lines))

    action = "would fix" if args.dry_run else "fixed"
    total = sum(len(lines) for _, lines in touched)
    print(
        f"[fix_utf8_encoding] {action} {total} call(s) in {len(touched)} file(s)",
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
