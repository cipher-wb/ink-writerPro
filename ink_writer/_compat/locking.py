"""跨平台文件锁原语 (US-001 — review §三 #8 抽公共)。

历史背景：
    ``ink_writer/case_library/_id_alloc.py`` 与 ``ink_writer/rewrite_loop/dry_run.py``
    各自持有一份字面相同的 ``_locked_file`` (Unix ``fcntl.flock`` / Windows
    ``msvcrt.locking``) 实现，违反 CLAUDE.md "Windows 兼容守则 — 优先复用
    runtime_compat 原语而非重写"。任何后续修改都要被迫双改，且日后再有第三个
    模块需要文件锁时复制三份的概率几乎为 1。本模块抽到统一的 ``_compat`` 目录。

Fail-loud 语义（review §三 #2 已在两处独立修过）：
    Windows 下 ``msvcrt.locking(LK_LOCK, 1)`` 内部会重试 10 次/s（共 ~10s），
    仍拿不到锁才 ``raise OSError``。旧实现把 OSError 静默吞掉继续 yield，等于
    无锁串行化、并发安全被悄悄解除——P1#6 修的 race lost-update 又会复活。
    本模块继续保持 fail-loud：锁失败直接向上抛，调用方明确感知。
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import IO


@contextmanager
def locked_file(path: Path, mode: str):
    """以 ``mode`` 打开 ``path`` 并立即取**独占**文件锁；with 退出时释放并 close。

    Args:
        path: 目标文件；父目录由调用方保证存在。
        mode: ``open()`` 标准模式（如 ``"r+"`` / ``"a+"``）；强制 ``encoding="utf-8"``。

    Raises:
        OSError: Windows 下 ``msvcrt.locking`` 多次重试仍拿不到锁；外层
            ``finally`` 会关闭 ``fh``，调用方应感知此失败而非吞掉。
    """
    fh: IO[str] = open(path, mode, encoding="utf-8")
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield fh
            finally:
                # unlock 失败可忽略：fh.close() 时 OS 自动释放
                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield fh
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


__all__ = ["locked_file"]
