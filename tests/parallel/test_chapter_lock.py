"""Tests for ChapterLockManager: acquire, release, TTL, contention."""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

import pytest

from ink_writer.parallel.chapter_lock import ChapterLockManager


@pytest.fixture
def lock_mgr(tmp_path: Path) -> ChapterLockManager:
    ink_dir = tmp_path / ".ink"
    ink_dir.mkdir()
    return ChapterLockManager(tmp_path, ttl=5)


class TestBasicLocking:
    def test_acquire_and_release(self, lock_mgr: ChapterLockManager):
        assert lock_mgr.try_acquire(1, "worker-1")
        assert not lock_mgr.try_acquire(1, "worker-2")
        assert lock_mgr.release(1, "worker-1")
        assert lock_mgr.try_acquire(1, "worker-2")

    def test_different_chapters_independent(self, lock_mgr: ChapterLockManager):
        assert lock_mgr.try_acquire(1, "w1")
        assert lock_mgr.try_acquire(2, "w2")
        assert lock_mgr.try_acquire(3, "w3")

    def test_release_wrong_owner_fails(self, lock_mgr: ChapterLockManager):
        lock_mgr.try_acquire(1, "w1")
        assert not lock_mgr.release(1, "w2")

    def test_active_locks(self, lock_mgr: ChapterLockManager):
        lock_mgr.try_acquire(1, "w1")
        lock_mgr.try_acquire(2, "w2")
        locks = lock_mgr.active_locks()
        assert len(locks) == 2
        keys = {l["lock_key"] for l in locks}
        assert keys == {"ch_1", "ch_2"}

    def test_clear_all(self, lock_mgr: ChapterLockManager):
        lock_mgr.try_acquire(1, "w1")
        lock_mgr.try_acquire(2, "w2")
        count = lock_mgr.clear_all()
        assert count == 2
        assert len(lock_mgr.active_locks()) == 0


class TestTTL:
    def test_expired_lock_auto_released(self, tmp_path: Path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        mgr = ChapterLockManager(tmp_path, ttl=1)
        mgr.try_acquire(1, "w1")
        time.sleep(1.5)
        assert mgr.try_acquire(1, "w2")

    def test_non_expired_lock_still_held(self, lock_mgr: ChapterLockManager):
        lock_mgr.try_acquire(1, "w1")
        time.sleep(0.1)
        assert not lock_mgr.try_acquire(1, "w2")


class TestContextManager:
    def test_chapter_lock_context(self, lock_mgr: ChapterLockManager):
        with lock_mgr.chapter_lock(1, "w1"):
            assert not lock_mgr.try_acquire(1, "w2")
        assert lock_mgr.try_acquire(1, "w2")

    def test_chapter_lock_timeout(self, lock_mgr: ChapterLockManager):
        lock_mgr.try_acquire(1, "w1")
        with pytest.raises(TimeoutError, match="第1章"):
            with lock_mgr.chapter_lock(1, "w2", timeout=1.0):
                pass

    def test_state_update_lock(self, lock_mgr: ChapterLockManager):
        with lock_mgr.state_update_lock("w1"):
            locks = lock_mgr.active_locks()
            state_locks = [l for l in locks if l["lock_key"] == "__state_update__"]
            assert len(state_locks) == 1
        locks_after = lock_mgr.active_locks()
        state_locks = [l for l in locks_after if l["lock_key"] == "__state_update__"]
        assert len(state_locks) == 0


class TestConcurrency:
    def test_threaded_contention(self, lock_mgr: ChapterLockManager):
        results = {"w1": False, "w2": False}
        barrier = threading.Barrier(2)

        def worker(name: str):
            barrier.wait()
            results[name] = lock_mgr.try_acquire(1, name)

        t1 = threading.Thread(target=worker, args=("w1",))
        t2 = threading.Thread(target=worker, args=("w2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert sum(results.values()) == 1

    def test_parallel_different_chapters(self, lock_mgr: ChapterLockManager):
        results = {}
        barrier = threading.Barrier(4)

        def worker(ch: int, name: str):
            barrier.wait()
            results[name] = lock_mgr.try_acquire(ch, name)

        threads = [
            threading.Thread(target=worker, args=(i, f"w{i}"))
            for i in range(1, 5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(results.values())
