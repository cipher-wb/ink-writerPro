"""tests for ``read_dry_run_counter`` 并发读安全 (US-003 — review §三 #5)。

旧实现 ``read_dry_run_counter`` 不加锁；当另一进程在 ``increment_dry_run_counter``
的 ``r+/seek/truncate/write`` 三连中途时，read 会拿到空字符串 → fallthrough 到 0，
``is_dry_run`` 误判 counter=0、永远停在 dry-run。

本测试用 multiprocessing 同时 8 worker increment + 1 worker 反复 read，断言：
1. read 返回值序列单调非递减（除首次 0 是空文件 fallthrough）。
2. read 至少观察到 200 次 increment 的最终值 == 200。
"""

from __future__ import annotations

import multiprocessing as mp
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

from ink_writer._compat.locking import shared_locked_file
from ink_writer.rewrite_loop.dry_run import (
    increment_dry_run_counter,
    read_dry_run_counter,
)


def _bump(path_str: str) -> int:
    return increment_dry_run_counter(base_dir=Path(path_str))


def _read_loop(path_str: str, samples: int, out_q) -> None:
    """循环 read 共 ``samples`` 次，把读到的序列塞 queue。"""
    base = Path(path_str)
    seq: list[int] = []
    for _ in range(samples):
        seq.append(read_dry_run_counter(base_dir=base))
        # 微小让步，给 writer 机会插入
        time.sleep(0.0005)
    out_q.put(seq)


@pytest.mark.mac
def test_read_dry_run_counter_no_zero_during_writer_truncate_window(
    tmp_path: Path,
) -> None:
    """8 writer 并发 increment + 1 reader 循环 read，read 序列必须单调非递减。

    若 ``read_dry_run_counter`` 没加共享锁，会在 writer ``truncate→write`` 之间
    读到空文件 → 返 0 → 序列出现回退（如 ``[..., 87, 0, 90, ...]``）。
    """
    base = tmp_path
    workers = 8
    rounds_per_worker = 25  # 总 200 次 increment
    total = workers * rounds_per_worker

    ctx = mp.get_context("spawn")
    out_q: mp.Queue = ctx.Queue()

    # 1 个 reader 子进程持续读 ~200 个采样点
    reader = ctx.Process(target=_read_loop, args=(str(base), 200, out_q))
    reader.start()

    args = [str(base)] * total
    with ctx.Pool(workers) as pool:
        pool.map(_bump, args)

    reader.join(timeout=30)
    seq = out_q.get(timeout=5)

    # 跳过开头的 0（counter 文件还不存在或 increment 未发生）
    seen_nonzero = False
    prev = -1
    for v in seq:
        if not seen_nonzero:
            if v == 0:
                continue
            seen_nonzero = True
        # 一旦读到非 0，后续读到的都应 >= 上一次读到的值
        assert v >= prev, (
            f"read counter went backwards: {prev} -> {v}; full seq tail: {seq[-20:]}"
        )
        prev = v

    # 全部 increment 完成后，最终值必须等于 total
    final = read_dry_run_counter(base_dir=base)
    assert final == total, f"expected {total} got {final}"


def test_read_dry_run_counter_handles_truncate_window_with_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """模拟 ``read`` 第一次拿到空字符串但 ``st_size > 0``（writer truncate 后未 write）：
    应触发 1 次重读拿到稳定值，而不是 fallthrough 返 0。

    通过 monkeypatch ``shared_locked_file`` 让首次返一个 mock fh （read=''），
    第二次返真实 fh。这是 retry 路径的隔离单元测试。
    """
    base = tmp_path
    counter = base / ".dry_run_counter"
    counter.write_text("42", encoding="utf-8")

    real_shared = shared_locked_file
    call_count = {"n": 0}

    from contextlib import contextmanager

    @contextmanager
    def fake_shared(path: Path, mode: str = "r"):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # 第一次：模拟 reader 命中 truncate→write 中途窗口（read=''）
            class _EmptyFH:
                def read(self) -> str:
                    return ""

            yield _EmptyFH()
        else:
            with real_shared(path, mode) as fh:
                yield fh

    import ink_writer.rewrite_loop.dry_run as dr

    monkeypatch.setattr(dr, "shared_locked_file", fake_shared)

    # 此时 path.stat().st_size = 2 (字符串"42")，触发重试
    assert read_dry_run_counter(base_dir=base) == 42
    assert call_count["n"] == 2, "should have triggered exactly one retry"


def test_read_dry_run_counter_no_infinite_retry_on_persistent_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """如果 reader 重试两次都拿到空 raw（极端 race 或 truncate 后未恢复），
    仍应 fallthrough 返 0 而不是无限重试。
    """
    base = tmp_path
    counter = base / ".dry_run_counter"
    # st_size > 0 但 read 总返空（模拟 mock 持续撞窗口）
    counter.write_text("xxx", encoding="utf-8")

    call_count = {"n": 0}

    from contextlib import contextmanager

    @contextmanager
    def fake_shared(path: Path, mode: str = "r"):
        call_count["n"] += 1

        class _EmptyFH:
            def read(self) -> str:
                return ""

        yield _EmptyFH()

    import ink_writer.rewrite_loop.dry_run as dr

    monkeypatch.setattr(dr, "shared_locked_file", fake_shared)

    assert read_dry_run_counter(base_dir=base) == 0
    assert call_count["n"] == 2, "must retry exactly once, not loop"


def test_shared_locked_file_windows_lock_failure_is_fail_loud(tmp_path: Path) -> None:
    """共享锁路径同样保留 fail-loud 语义（与 ``locked_file`` 一致）。"""
    counter = tmp_path / "counter.txt"
    counter.write_text("0", encoding="utf-8")

    fake_msvcrt = mock.MagicMock()
    fake_msvcrt.LK_LOCK = 1
    fake_msvcrt.LK_UNLCK = 0
    fake_msvcrt.locking.side_effect = OSError("simulated shared lock failure")

    with mock.patch.object(sys, "platform", "win32"), \
            mock.patch.dict(sys.modules, {"msvcrt": fake_msvcrt}):
        with pytest.raises(OSError, match="simulated shared lock failure"):
            with shared_locked_file(counter, "r") as fh:
                fh.read()  # pragma: no cover

    assert counter.read_text(encoding="utf-8") == "0"
