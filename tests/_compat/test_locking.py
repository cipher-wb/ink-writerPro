"""tests for ink_writer._compat.locking (US-001 — review §三 #8 抽公共)。

覆盖：
1. Unix 多进程互斥（spawn-context；与 test_id_alloc_concurrency 同模式）。
2. Windows 路径在 ``msvcrt.locking`` 抛 OSError 时上抛（不 silent pass）。
"""

from __future__ import annotations

import multiprocessing as mp
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

from ink_writer._compat.locking import locked_file


def _bump_counter(path_str: str) -> int:
    """读 path_str 文本里的整数 +1 写回，返回新值；用 ``locked_file`` 串行化。"""
    p = Path(path_str)
    with locked_file(p, "r+") as fh:
        raw = fh.read().strip()
        cur = int(raw) if raw else 0
        new = cur + 1
        fh.seek(0)
        fh.truncate()
        fh.write(str(new))
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    return new


@pytest.mark.mac
def test_locked_file_unix_mutex_no_lost_updates(tmp_path: Path) -> None:
    """8 worker × 25 round 共享同一 counter file，最终精确 200（无丢更新）。

    若 ``locked_file`` 没真正串行化 read-modify-write，至少有一对 worker 会读到
    同样旧值并写回相同新值，最终值会 < 200。
    """
    counter = tmp_path / "counter.txt"
    counter.write_text("0", encoding="utf-8")

    workers = 8
    rounds_per_worker = 25
    total = workers * rounds_per_worker
    args = [str(counter)] * total

    ctx = mp.get_context("spawn")
    with ctx.Pool(workers) as pool:
        pool.map(_bump_counter, args)

    final = int(counter.read_text(encoding="utf-8").strip())
    assert final == total, f"expected {total} got {final} — race lost updates"


def test_locked_file_windows_lock_failure_is_fail_loud(tmp_path: Path) -> None:
    """mock sys.platform='win32' + msvcrt.locking 抛 OSError → locked_file 上抛而非 silent pass。

    这是 review §三 #2 fail-loud 语义的回归门：旧实现把 OSError 静默吞掉继续
    yield，等于无锁串行化、并发安全被悄悄解除。
    """
    counter = tmp_path / "counter.txt"
    counter.write_text("0", encoding="utf-8")

    fake_msvcrt = mock.MagicMock()
    fake_msvcrt.LK_LOCK = 1
    fake_msvcrt.LK_UNLCK = 0
    fake_msvcrt.locking.side_effect = OSError("simulated lock contention timeout")

    with mock.patch.object(sys, "platform", "win32"), \
            mock.patch.dict(sys.modules, {"msvcrt": fake_msvcrt}):
        with pytest.raises(OSError, match="simulated lock contention timeout"):
            with locked_file(counter, "r+") as fh:
                # 不应进入此块——锁失败应在 yield 之前抛出
                fh.write("never reached")  # pragma: no cover

    # 文件未被污染
    assert counter.read_text(encoding="utf-8") == "0"
