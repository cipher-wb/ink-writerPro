"""v18 US-006: 异步章节锁端到端测试。

验证 ``ChapterLockManager.async_chapter_lock`` / ``async_state_update_lock``
在同事件循环内的串行化、跨章节并行度、超时语义，以及 10 个 asyncio task
并发持锁时的正确性（无丢失更新、严格先来后到）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ink_writer.parallel.chapter_lock import ChapterLockManager


@pytest.fixture
def lock_mgr(tmp_path: Path) -> ChapterLockManager:
    (tmp_path / ".ink").mkdir()
    return ChapterLockManager(tmp_path, ttl=30)


class TestAsyncChapterLock:
    async def test_basic_acquire_release(self, lock_mgr: ChapterLockManager) -> None:
        """async_chapter_lock 正常进入/退出：退出后同 chapter 可重新获取。"""
        async with lock_mgr.async_chapter_lock(1, "w1"):
            # 同一 chapter 在锁内：try_acquire 走 SQLite 必返回 False（已插入行）。
            assert lock_mgr.try_acquire(1, "w2") is False
        # 锁释放后 sync try_acquire 应成功
        assert lock_mgr.try_acquire(1, "w3") is True
        lock_mgr.release(1, "w3")

    async def test_ten_tasks_hold_same_chapter_serialize(
        self, lock_mgr: ChapterLockManager
    ) -> None:
        """10 个 asyncio task 并发持同一 chapter 锁，必须严格串行化。

        每个 task 在锁内 RMW 共享 counter；若任一 task 在锁内看到
        in_critical == True 即算失败（说明两 task 同时处于临界区）。
        """
        shared = {"counter": 0, "in_critical": False}
        observed_counters: list[int] = []
        errors: list[str] = []

        async def worker(idx: int) -> None:
            async with lock_mgr.async_chapter_lock(1, f"w{idx}", timeout=20.0):
                if shared["in_critical"]:
                    errors.append(f"w{idx}: 并发进入临界区")
                shared["in_critical"] = True
                # 异步让出调度，放大潜在竞态
                await asyncio.sleep(0.02)
                current = shared["counter"]
                await asyncio.sleep(0.01)
                shared["counter"] = current + 1
                observed_counters.append(shared["counter"])
                shared["in_critical"] = False

        await asyncio.gather(*(worker(i) for i in range(10)))

        assert errors == [], f"存在并发进入临界区：{errors}"
        assert shared["counter"] == 10, (
            f"丢失更新：期望 counter=10，实际 {shared['counter']}"
        )
        # 严格串行化 → 每次出临界区观察到的 counter 必为 1..10 无重复
        assert sorted(observed_counters) == list(range(1, 11)), (
            f"counter 观测值重复/缺失：{observed_counters}"
        )

    async def test_ten_tasks_different_chapters_parallel(
        self, lock_mgr: ChapterLockManager
    ) -> None:
        """10 个 asyncio task 对 10 个不同 chapter 并发持锁，应几乎同时完成。

        若 async 锁粒度不是按 chapter_id 分桶，不同 chapter 也会串行化。
        通过 barrier 验证：10 个 task 在锁内能同时进入临界区至少 2 个。
        """
        entered = asyncio.Event()
        active_count = {"n": 0, "max_n": 0}
        lock_inside = asyncio.Lock()

        async def worker(ch: int) -> None:
            async with lock_mgr.async_chapter_lock(ch, f"w{ch}", timeout=10.0):
                async with lock_inside:
                    active_count["n"] += 1
                    active_count["max_n"] = max(
                        active_count["max_n"], active_count["n"]
                    )
                # 制造重叠窗口
                await asyncio.sleep(0.05)
                async with lock_inside:
                    active_count["n"] -= 1
                entered.set()

        await asyncio.wait_for(
            asyncio.gather(*(worker(i) for i in range(10, 20))),
            timeout=10.0,
        )
        # 10 个不同 chapter 必然有 >1 个同时在临界区（真正并行）
        assert active_count["max_n"] >= 2, (
            f"不同 chapter 被错误串行化：max_concurrent={active_count['max_n']}"
        )

    async def test_timeout_when_held_by_sync_path(
        self, lock_mgr: ChapterLockManager
    ) -> None:
        """同步路径抢到 SQLite 行后，async 路径 timeout 必须 raise。

        验证 async_chapter_lock 的跨路径（同步/异步）互斥语义。
        """
        # 同步抢占
        assert lock_mgr.try_acquire(1, "sync_owner") is True
        try:
            with pytest.raises(TimeoutError):
                async with lock_mgr.async_chapter_lock(1, "async_owner", timeout=0.8):
                    pass
        finally:
            lock_mgr.release(1, "sync_owner")

    async def test_exception_in_critical_releases_lock(
        self, lock_mgr: ChapterLockManager
    ) -> None:
        """临界区异常必须释放 async + SQLite 两层锁，下次 acquire 成功。"""

        class Boom(Exception):
            pass

        with pytest.raises(Boom):
            async with lock_mgr.async_chapter_lock(1, "w1", timeout=5.0):
                raise Boom()

        # 锁应已全部释放
        assert lock_mgr.try_acquire(1, "w2") is True
        lock_mgr.release(1, "w2")

    async def test_same_key_reuses_asyncio_lock(
        self, lock_mgr: ChapterLockManager
    ) -> None:
        """同 chapter 多次获取应复用同一 asyncio.Lock 实例（避免内存泄漏）。"""
        async with lock_mgr.async_chapter_lock(42, "w1"):
            pass
        first = lock_mgr._async_locks.get("ch_42")
        async with lock_mgr.async_chapter_lock(42, "w2"):
            pass
        second = lock_mgr._async_locks.get("ch_42")
        assert first is not None
        assert first is second


class TestAsyncStateUpdateLock:
    async def test_ten_tasks_serialize_state_update(
        self, lock_mgr: ChapterLockManager
    ) -> None:
        """10 个 asyncio task 并发 async_state_update_lock：
        RMW 共享 counter 必须无丢失更新，且 counter_after 无重复。
        """
        shared = {"counter": 0}
        counters_observed: list[int] = []
        in_critical = {"flag": False}
        errors: list[str] = []

        async def worker(idx: int) -> None:
            async with lock_mgr.async_state_update_lock(f"w{idx}", timeout=20.0):
                if in_critical["flag"]:
                    errors.append(f"w{idx}: 并发进入 state 临界区")
                in_critical["flag"] = True
                v = shared["counter"]
                await asyncio.sleep(0.01)
                shared["counter"] = v + 1
                counters_observed.append(shared["counter"])
                in_critical["flag"] = False

        await asyncio.gather(*(worker(i) for i in range(10)))

        assert errors == [], f"state 锁串行化失败：{errors}"
        assert shared["counter"] == 10
        assert sorted(counters_observed) == list(range(1, 11))

    async def test_state_lock_and_chapter_lock_independent(
        self, lock_mgr: ChapterLockManager
    ) -> None:
        """持有 state 锁时，chapter 锁仍可独立获取（两套桶互不干扰）。"""
        async with lock_mgr.async_state_update_lock("state_owner", timeout=5.0):
            async with lock_mgr.async_chapter_lock(99, "ch_owner", timeout=5.0):
                pass  # 能进入即证明独立
