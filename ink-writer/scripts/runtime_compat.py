#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Runtime compatibility helpers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Union

_PROACTOR_POLICY_SET = False
_SYMLINK_PRIVILEGE_CACHE: Optional[bool] = None
_PYTHON_LAUNCHER_CACHE: Optional[str] = None

_logger = logging.getLogger(__name__)


def enable_windows_utf8_stdio(*, skip_in_pytest: bool = False) -> bool:
    """Enable UTF-8 stdio wrappers on Windows.

    Returns:
        True if wrapping was applied, False otherwise.
    """
    if sys.platform != "win32":
        return False
    if skip_in_pytest and os.environ.get("PYTEST_CURRENT_TEST"):  # pragma: no cover
        return False

    stdout_encoding = str(getattr(sys.stdout, "encoding", "") or "").lower()  # pragma: no cover
    stderr_encoding = str(getattr(sys.stderr, "encoding", "") or "").lower()  # pragma: no cover
    if stdout_encoding == "utf-8" and stderr_encoding == "utf-8":  # pragma: no cover
        return False

    try:  # pragma: no cover
        import io

        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
        return True
    except Exception:
        return False


_WIN_POSIX_DRIVE_RE = re.compile(r"^/(?P<drive>[a-zA-Z])/(?P<rest>.*)$")
_WIN_WSL_MNT_DRIVE_RE = re.compile(r"^/mnt/(?P<drive>[a-zA-Z])/(?P<rest>.*)$")


def normalize_windows_path(value: Union[str, Path]) -> Path:
    """
    将 Windows 上常见的 POSIX 风格路径规范化为 Windows 盘符路径。

    典型来源：
    - Git Bash / MSYS:  /d/desktop/...  => D:/desktop/...
    - WSL:             /mnt/d/desktop/... => D:/desktop/...

    非 Windows 平台直接返回 Path(value)（透传，不改语义）。
    既接受 str 也接受 Path 输入。

    使用场景（US-003 / 跨平台审计）：

    1. 接收用户在 Git Bash / WSL 终端粘贴的项目路径：

        >>> from runtime_compat import normalize_windows_path
        >>> p = normalize_windows_path("/d/projects/我的小说")
        >>> # Mac/Linux:  Path('/d/projects/我的小说')
        >>> # Windows:    Path('D:/projects/我的小说')

    2. 配合 ``ink_writer/cli`` 解析 ``--project`` 参数：

        >>> args.project_dir = normalize_windows_path(args.project_dir)
        >>> # 之后 args.project_dir / ".ink" / "state.json" 在两个平台都正确

    3. 处理跨工具传递的混合分隔符路径（用户 / config / env var）：

        >>> normalize_windows_path("/mnt/c/Users/me/project")
        >>> # Windows: Path('C:/Users/me/project')

    幂等性：对已经是盘符形态（``D:/...``）或非 POSIX 风格的路径，
    返回 ``Path(value)`` 不变。
    """
    if sys.platform != "win32":
        return Path(value)

    raw = str(value).strip()  # pragma: no cover
    if not raw:  # pragma: no cover
        return Path(raw)

    m = _WIN_WSL_MNT_DRIVE_RE.match(raw)  # pragma: no cover
    if m:  # pragma: no cover
        drive = m.group("drive").upper()
        rest = m.group("rest")
        return Path(f"{drive}:/{rest}")

    m = _WIN_POSIX_DRIVE_RE.match(raw)  # pragma: no cover
    if m:  # pragma: no cover
        drive = m.group("drive").upper()
        rest = m.group("rest")
        return Path(f"{drive}:/{rest}")

    return Path(value)  # pragma: no cover


def set_windows_proactor_policy() -> bool:
    """Force WindowsProactorEventLoopPolicy on Windows so subprocess/socket
    behaviour matches macOS/Linux. No-op on other platforms. Idempotent.

    Returns:
        True if the policy was applied (or already applied) on Windows;
        False on non-Windows platforms.
    """
    global _PROACTOR_POLICY_SET
    if sys.platform != "win32":
        return False
    if _PROACTOR_POLICY_SET:  # pragma: no cover
        return True
    try:  # pragma: no cover
        policy_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
        if policy_cls is None:
            return False
        asyncio.set_event_loop_policy(policy_cls())
        _PROACTOR_POLICY_SET = True
        return True
    except Exception:
        return False


def _has_symlink_privilege() -> bool:
    """Probe whether the current process can create symlinks.

    On non-Windows: always True (POSIX symlinks never require elevation).
    On Windows: caches the result of a one-shot ``os.symlink`` attempt in a
    temp directory. Developer Mode or Administrator rights grant the
    privilege; otherwise ``OSError`` is raised and we return False.
    """
    global _SYMLINK_PRIVILEGE_CACHE
    if sys.platform != "win32":
        return True
    if _SYMLINK_PRIVILEGE_CACHE is not None:  # pragma: no cover
        return _SYMLINK_PRIVILEGE_CACHE
    try:  # pragma: no cover
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "target.txt"
            target.write_text("x", encoding="utf-8")
            link = Path(td) / "link.txt"
            os.symlink(target, link)
            _SYMLINK_PRIVILEGE_CACHE = True
    except (OSError, NotImplementedError, AttributeError):  # pragma: no cover
        _SYMLINK_PRIVILEGE_CACHE = False
    return bool(_SYMLINK_PRIVILEGE_CACHE)


def safe_symlink(
    src: Union[str, Path],
    dst: Union[str, Path],
    *,
    target_is_directory: bool = False,
    overwrite: bool = False,
) -> bool:
    """Create a symlink ``dst → src``; fall back to ``shutil.copy`` on
    Windows when the current process lacks symlink privilege.

    On POSIX (Mac/Linux), :func:`_has_symlink_privilege` always returns True,
    so this helper behaves exactly like ``os.symlink`` — byte-level
    compatible. On Windows without Developer Mode / Administrator rights,
    symlink creation raises ``OSError``; we catch that by probing permission
    first and gracefully degrading to a copy plus a ``WARNING`` log, so the
    calling script keeps running.

    Args:
        src: Target path the link should point at (must exist if falling
            back to copy).
        dst: Link path to create (must not exist unless ``overwrite=True``).
        target_is_directory: Hint passed to :func:`os.symlink` on Windows;
            also used to pick ``copytree`` vs ``copyfile`` when falling back.
        overwrite: If True, remove an existing ``dst`` first. A directory
            ``dst`` that is not itself a symlink is removed via
            ``shutil.rmtree``; anything else goes through ``unlink``.

    Returns:
        True if a real symlink was created (POSIX always, or Windows with
        privilege); False if a copy fallback was used.

    Raises:
        FileExistsError: If ``dst`` already exists and ``overwrite`` is
            False.
    """
    src_path = Path(src)
    dst_path = Path(dst)

    if dst_path.exists() or dst_path.is_symlink():
        if not overwrite:
            raise FileExistsError(f"dst already exists: {dst_path}")
        if dst_path.is_dir() and not dst_path.is_symlink():
            shutil.rmtree(dst_path)
        else:
            dst_path.unlink()

    if _has_symlink_privilege():
        os.symlink(src_path, dst_path, target_is_directory=target_is_directory)
        return True

    _logger.warning(  # pragma: no cover
        "safe_symlink: no symlink privilege on Windows; copying %s -> %s",
        src_path,
        dst_path,
    )
    if src_path.is_dir() or target_is_directory:  # pragma: no cover
        shutil.copytree(src_path, dst_path)
    else:  # pragma: no cover
        shutil.copyfile(src_path, dst_path)
    return False  # pragma: no cover


def _probe_launcher(cmd: list[str]) -> bool:
    """Return True if ``cmd --version`` exits 0."""
    try:
        result = subprocess.run(
            cmd + ["--version"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def find_python_launcher() -> str:
    """Return a command string that launches a Python 3 interpreter.

    - Non-Windows: always returns ``"python3"`` (unchanged behaviour).
    - Windows: tries ``py -3`` first, then ``python3``, then ``python``,
      returning whichever responds to ``--version``. Falls back to ``python``
      if none probe successfully (caller will get a clear error).

    The result is cached per-process.
    """
    global _PYTHON_LAUNCHER_CACHE
    if _PYTHON_LAUNCHER_CACHE is not None:
        return _PYTHON_LAUNCHER_CACHE

    if sys.platform != "win32":
        _PYTHON_LAUNCHER_CACHE = "python3"
        return _PYTHON_LAUNCHER_CACHE

    candidates: list[list[str]] = [  # pragma: no cover
        ["py", "-3"],
        ["python3"],
        ["python"],
    ]
    for cmd in candidates:  # pragma: no cover
        head = cmd[0]
        if shutil.which(head) is None:
            continue
        if _probe_launcher(cmd):
            _PYTHON_LAUNCHER_CACHE = " ".join(cmd)
            return _PYTHON_LAUNCHER_CACHE

    _PYTHON_LAUNCHER_CACHE = "python"  # pragma: no cover
    return _PYTHON_LAUNCHER_CACHE  # pragma: no cover

