"""v16 US-002：并发 state.json / index.db 写入下 ChapterLockManager 的保护验证。

场景：模拟 4 个 asyncio 任务同时执行「读-改-写」式 state / index 更新
（对应 Step 5 data-agent 的实体入库流程）。

- 无锁 baseline：预期出现 lost update（最终计数 < 4）。
- 有 ``async_state_update_lock`` 包裹：预期所有更新都持久化（计数恰好 = 4）。
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from ink_writer.parallel.chapter_lock import ChapterLockManager


def _init_state(project_root: Path) -> tuple[Path, Path]:
    ink = project_root / ".ink"
    ink.mkdir(parents=True, exist_ok=True)
    state_file = ink / "state.json"
    state_file.write_text(json.dumps({"counter": 0, "history": []}), encoding="utf-8")

    db_path = ink / "index.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS entity_log (id INTEGER PRIMARY KEY AUTOINCREMENT, who TEXT, counter_after INTEGER)"
        )
        conn.commit()
    finally:
        conn.close()
    return state_file, db_path


async def _rmw_without_lock(state_file: Path, db_path: Path, who: str) -> None:
    """模拟 data-agent 的读-改-写：读 state → 停顿 → 写回；同时 append index.db。

    无锁情况下，多任务交错会导致后写者覆盖前写者的 counter（lost update）。
    """
    data = json.loads(state_file.read_text(encoding="utf-8"))
    # 人为放大窗口，放大竞态（模拟真实 data-agent 的 IO/CPU 耗时）。
    await asyncio.sleep(0.05)
    data["counter"] += 1
    data["history"].append(who)
    state_file.write_text(json.dumps(data), encoding="utf-8")

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO entity_log (who, counter_after) VALUES (?, ?)",
            (who, data["counter"]),
        )
        conn.commit()
    finally:
        conn.close()


async def _rmw_with_lock(
    lock: ChapterLockManager, state_file: Path, db_path: Path, who: str
) -> None:
    async with lock.async_state_update_lock(owner=who, timeout=30):
        await _rmw_without_lock(state_file, db_path, who)


class TestConcurrentStateWrite:
    @pytest.mark.asyncio
    async def test_without_lock_may_lose_updates(self, tmp_path: Path) -> None:
        """文档性测试：确认无锁场景下确实可能丢失更新（证明锁必要）。

        由于调度时序不可完全确定，偶尔无锁 4 任务也能串行完成。这里断言
        "最终 counter ≤ 4 且 DB 记录恰好 4 条"，允许 counter < 4 的丢失。
        """
        state_file, db_path = _init_state(tmp_path)
        await asyncio.gather(*[
            _rmw_without_lock(state_file, db_path, f"w{i}") for i in range(4)
        ])
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["counter"] <= 4

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT who, counter_after FROM entity_log").fetchall()
        conn.close()
        # DB 插入是独立连接，4 条都会写入；但 counter_after 可能重复（证明漂移）。
        assert len(rows) == 4

    @pytest.mark.asyncio
    async def test_with_async_state_lock_preserves_all_updates(
        self, tmp_path: Path
    ) -> None:
        state_file, db_path = _init_state(tmp_path)
        lock = ChapterLockManager(tmp_path, ttl=30)

        await asyncio.gather(*[
            _rmw_with_lock(lock, state_file, db_path, f"w{i}") for i in range(4)
        ])

        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["counter"] == 4, f"期待 counter=4，实际 {data['counter']} — lost update！"
        assert sorted(data["history"]) == ["w0", "w1", "w2", "w3"]

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT who, counter_after FROM entity_log ORDER BY id"
        ).fetchall()
        conn.close()
        assert len(rows) == 4
        # counter_after 应为 1,2,3,4 全不重复，证明严格串行化。
        counters = [r[1] for r in rows]
        assert sorted(counters) == [1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_chapter_lock_serializes_same_chapter(
        self, tmp_path: Path
    ) -> None:
        """同章 chapter_lock 下，两个 asyncio 任务必须严格串行，不得交错。"""
        lock = ChapterLockManager(tmp_path, ttl=30)
        events: list[str] = []

        async def work(name: str) -> None:
            async with lock.async_chapter_lock(1, owner=name, timeout=10):
                events.append(f"{name}:enter")
                await asyncio.sleep(0.05)
                events.append(f"{name}:exit")

        await asyncio.gather(work("a"), work("b"))

        # 要求不出现 enter(a)→enter(b) 或 enter(b)→enter(a) 前两项，
        # 必须是 enter→exit→enter→exit 的严格交替。
        assert len(events) == 4
        pairs = [events[0:2], events[2:4]]
        for pair in pairs:
            assert pair[0].endswith(":enter")
            assert pair[1].endswith(":exit")
            assert pair[0].split(":")[0] == pair[1].split(":")[0]

    @pytest.mark.asyncio
    async def test_different_chapters_can_run_concurrently(
        self, tmp_path: Path
    ) -> None:
        """不同章 chapter_lock 之间互不阻塞，确保并发吞吐不被误杀。

        设计：两个任务各自锁住不同章节后 ``asyncio.sleep(0.3)``。若锁错误地
        将两章串行化，总耗时 ≥ 0.6s；正常并发应 ≈ 0.3s。
        """
        lock = ChapterLockManager(tmp_path, ttl=30)

        async def work(ch: int, name: str) -> None:
            async with lock.async_chapter_lock(ch, owner=name, timeout=5):
                await asyncio.sleep(0.3)

        loop = asyncio.get_event_loop()
        t0 = loop.time()
        await asyncio.gather(work(1, "w1"), work(2, "w2"))
        elapsed = loop.time() - t0
        assert elapsed < 0.55, f"两章被错误串行化（elapsed={elapsed:.2f}s）"
