"""tests/core/test_safe_symlink.py — US-006 safe_symlink 降级兜底验证。

覆盖 CLAUDE.md "Windows 兼容守则" 对 C5 的约束：

1. **有权限路径（POSIX 始终 True）**：``safe_symlink(src, dst)`` 等价于
   ``os.symlink(src, dst)``——Mac 字节级一致性的根基。
2. **无权限路径（Mac mock 模拟 Windows 无特权）**：降级为 ``shutil.copyfile``
   并发 WARNING 日志，调用方脚本不中断。
3. **幂等/safety**：``dst`` 已存在且未指定 ``overwrite`` 时抛 FileExistsError；
   ``overwrite=True`` 时清空后创建。
4. **仓库红线**：非 tests、非 primitive 实现的 .py 文件里不得出现裸
   ``os.symlink`` / ``x.symlink_to``——守护后续 PR 不再回退。
"""

from __future__ import annotations

import ast
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts"
INK_WRITER_SCRIPTS = REPO_ROOT / "ink-writer" / "scripts"
for _p in (SCRIPT_DIR, INK_WRITER_SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import runtime_compat  # noqa: E402
from runtime_compat import safe_symlink  # noqa: E402

from audit_cross_platform import (  # noqa: E402
    EXCLUDE_DIR_NAMES,
    iter_files,
    safe_read_text,
)


# ---------------------------------------------------------------------------
# 基础行为：有权限 → 真实 symlink
# ---------------------------------------------------------------------------


def test_safe_symlink_creates_real_symlink_when_privileged(tmp_path: Path) -> None:
    src = tmp_path / "target.txt"
    src.write_text("payload", encoding="utf-8")
    dst = tmp_path / "link.txt"

    created = safe_symlink(src, dst)

    assert created is True
    assert dst.is_symlink()
    assert dst.read_text(encoding="utf-8") == "payload"
    # 解析后指向 src
    assert dst.resolve() == src.resolve()


def test_safe_symlink_accepts_str_and_path(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")
    dst = tmp_path / "b.txt"
    created = safe_symlink(str(src), str(dst))
    assert created is True
    assert dst.is_symlink()


def test_safe_symlink_refuses_existing_dst_without_overwrite(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    src.write_text("x", encoding="utf-8")
    dst = tmp_path / "dst.txt"
    dst.write_text("already here", encoding="utf-8")

    with pytest.raises(FileExistsError):
        safe_symlink(src, dst)


def test_safe_symlink_overwrites_when_requested(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    src.write_text("new", encoding="utf-8")
    dst = tmp_path / "dst.txt"
    dst.write_text("old", encoding="utf-8")

    created = safe_symlink(src, dst, overwrite=True)

    assert created is True
    assert dst.is_symlink()
    assert dst.read_text(encoding="utf-8") == "new"


def test_safe_symlink_overwrites_directory(tmp_path: Path) -> None:
    src = tmp_path / "src_dir"
    src.mkdir()
    (src / "inner.txt").write_text("hello", encoding="utf-8")
    dst = tmp_path / "dst_dir"
    dst.mkdir()
    (dst / "stale.txt").write_text("gone", encoding="utf-8")

    created = safe_symlink(src, dst, target_is_directory=True, overwrite=True)

    assert created is True
    assert dst.is_symlink()
    # symlink resolves into the new source
    assert (dst / "inner.txt").read_text(encoding="utf-8") == "hello"
    assert not (dst / "stale.txt").exists()


# ---------------------------------------------------------------------------
# 降级路径：mock _has_symlink_privilege=False → shutil.copyfile
# ---------------------------------------------------------------------------


def test_safe_symlink_falls_back_to_copy_when_no_privilege(tmp_path: Path) -> None:
    src = tmp_path / "file.txt"
    src.write_text("payload-copy", encoding="utf-8")
    dst = tmp_path / "copy.txt"

    with patch.object(runtime_compat, "_has_symlink_privilege", return_value=False):
        created = safe_symlink(src, dst)

    assert created is False
    assert dst.exists()
    assert not dst.is_symlink()
    assert dst.read_text(encoding="utf-8") == "payload-copy"


def test_safe_symlink_falls_back_to_copytree_for_directory(tmp_path: Path) -> None:
    src = tmp_path / "srcdir"
    src.mkdir()
    (src / "a.txt").write_text("aa", encoding="utf-8")
    (src / "nested").mkdir()
    (src / "nested" / "b.txt").write_text("bb", encoding="utf-8")
    dst = tmp_path / "dstdir"

    with patch.object(runtime_compat, "_has_symlink_privilege", return_value=False):
        created = safe_symlink(src, dst)

    assert created is False
    assert dst.is_dir()
    assert not dst.is_symlink()
    assert (dst / "a.txt").read_text(encoding="utf-8") == "aa"
    assert (dst / "nested" / "b.txt").read_text(encoding="utf-8") == "bb"


def test_safe_symlink_copy_fallback_emits_warning(tmp_path: Path, caplog) -> None:
    src = tmp_path / "file.txt"
    src.write_text("x", encoding="utf-8")
    dst = tmp_path / "out.txt"
    caplog.set_level("WARNING", logger="runtime_compat")
    with patch.object(runtime_compat, "_has_symlink_privilege", return_value=False):
        safe_symlink(src, dst)
    joined = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "no symlink privilege" in joined
    assert str(src) in joined or str(dst) in joined


# ---------------------------------------------------------------------------
# Mac 无特权下也能调（Path(src).resolve() 非必要）
# ---------------------------------------------------------------------------


def test_safe_symlink_overwrite_plus_copy_fallback(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    src.write_text("new", encoding="utf-8")
    dst = tmp_path / "dst.txt"
    dst.write_text("old", encoding="utf-8")

    with patch.object(runtime_compat, "_has_symlink_privilege", return_value=False):
        created = safe_symlink(src, dst, overwrite=True)

    assert created is False
    assert dst.exists()
    assert not dst.is_symlink()
    assert dst.read_text(encoding="utf-8") == "new"


# ---------------------------------------------------------------------------
# 仓库红线：非 primitive / 非测试文件不得出现裸 symlink
# ---------------------------------------------------------------------------


_C5_PRIMITIVE_FUNCS = {"_has_symlink_privilege", "safe_symlink"}


def _file_has_raw_symlink(path: Path) -> list[int]:
    """Return lineno list of bare symlink calls (excluding primitive funcs &
    # noqa: c5 pragmas)."""
    src = safe_read_text(path)
    if not src:
        return []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []
    lines = src.splitlines()

    hits: list[int] = []
    stack: list[str] = []

    def _is_raw(call: ast.Call) -> bool:
        fn = call.func
        if not isinstance(fn, ast.Attribute):
            return False
        if fn.attr == "symlink_to":
            return True
        if fn.attr == "symlink":
            rcv = fn.value
            if isinstance(rcv, ast.Name) and rcv.id == "os":
                return True
            if isinstance(rcv, ast.Attribute) and rcv.attr == "os":
                return True
        return False

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore

        def visit_Call(self, node):
            self.generic_visit(node)
            if not _is_raw(node):
                return
            if any(fn in _C5_PRIMITIVE_FUNCS for fn in stack):
                return
            line = lines[node.lineno - 1] if 1 <= node.lineno <= len(lines) else ""
            if "noqa: c5" in line.lower() or "c5-ok" in line.lower():
                return
            hits.append(node.lineno)

    V().visit(tree)
    return hits


def test_repo_has_no_bare_symlink_calls_outside_primitives() -> None:
    """仓库红线：除 runtime_compat._has_symlink_privilege / safe_symlink 自身和
    明确打了 ``# noqa: c5`` 的测试 SUT 处，其它 .py 文件禁止直接调
    ``os.symlink`` 或 ``Path.symlink_to``——必须走 ``safe_symlink`` 才能保证
    Windows 非管理员场景下脚本不中断。
    """
    offenders: list[str] = []
    for py in iter_files(REPO_ROOT, (".py",)):
        # 统一跳过 tests/audit 下的 fixture 字符串本身就包含 os.symlink，但 AST
        # 不会进入字符串内容，所以这里不做特殊 skip——扫到才需修
        hits = _file_has_raw_symlink(py)
        if hits:
            try:
                rel = py.relative_to(REPO_ROOT)
            except ValueError:
                rel = py
            for ln in hits:
                offenders.append(f"{rel}:{ln}")
    assert not offenders, (
        "Found bare symlink calls that must use runtime_compat.safe_symlink:\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# helper 对 POSIX 的 _has_symlink_privilege 总返回 True
# ---------------------------------------------------------------------------


def test_has_symlink_privilege_is_true_on_posix() -> None:
    """Mac/Linux 上 POSIX symlink 不要求 elevation —— helper 必须 True。"""
    if sys.platform == "win32":  # pragma: no cover
        pytest.skip("Windows-only ground truth is environment-dependent")
    assert runtime_compat._has_symlink_privilege() is True


# ---------------------------------------------------------------------------
# 防回归：POSIX 上 safe_symlink 与 os.symlink 产生结构等价 link（字节级一致承诺）
# ---------------------------------------------------------------------------


def test_safe_symlink_matches_os_symlink_bytes_on_posix(tmp_path: Path) -> None:
    if sys.platform == "win32":  # pragma: no cover
        pytest.skip("POSIX byte-parity check")
    src = tmp_path / "truth.txt"
    src.write_text("abc", encoding="utf-8")

    via_helper = tmp_path / "via_helper.txt"
    safe_symlink(src, via_helper)

    via_raw = tmp_path / "via_raw.txt"
    os.symlink(src, via_raw)  # noqa: c5 — parity reference for byte-level identity claim

    assert via_helper.is_symlink() and via_raw.is_symlink()
    assert os.readlink(via_helper) == os.readlink(via_raw)
    assert via_helper.read_bytes() == via_raw.read_bytes()
