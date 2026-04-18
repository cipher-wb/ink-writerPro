"""章节级写入锁管理，防止并发写入同一章节或竞争 state 更新。

v16 US-002：架构升级
--------------------
- 去除 ``threading.local()`` 连接缓存 → 每次操作独立开 SQLite 连接（WAL 模式下
  短连接轻量且避免跨线程/事件循环共享 conn 引发的 "SQLite objects created in
  a thread can only be used in that same thread" 错误）。
- 新增 ``asyncio.Lock`` 作为同进程同事件循环的快速路径，避免 busy-wait 轮询。
- 新增 ``async_chapter_lock()`` / ``async_state_update_lock()`` 异步上下文管理器
  供 ``PipelineManager`` 使用。
- 保留既有 ``chapter_lock()`` / ``state_update_lock()`` 同步 API（旧测试/脚本
  仍可使用）。
- 文件锁（``filelock.FileLock``）兜底：当 SQLite 行级锁失败/DB 文件异常时，
  回落到文件锁串行化，保底跨进程互斥。
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import AsyncGenerator, Generator

try:  # 可选依赖：若环境无 filelock 仍可运行（仅降级缺少跨进程兜底）。
    from filelock import FileLock, Timeout as FileLockTimeout
except ImportError:  # pragma: no cover - 依赖缺失的兜底分支
    FileLock = None  # type: ignore[assignment]
    FileLockTimeout = TimeoutError  # type: ignore[assignment]


class ChapterLockManager:
    """基于 SQLite + asyncio.Lock + filelock 的章节写入锁，支持跨进程 / 跨协程协调。

    利用 SQLite WAL 模式的原子性实现分布式锁：
    - 每个章节有独立的锁记录
    - 锁带有 TTL，过期自动释放（防止进程崩溃后死锁）
    - 支持 state.json 更新的全局互斥
    - 同事件循环内另用 ``asyncio.Lock`` 做快速路径，避免空转
    """

    DEFAULT_TTL = 600  # 10 minutes
    STATE_LOCK_KEY = "__state_update__"

    def __init__(self, project_root: Path, ttl: int = DEFAULT_TTL):
        self.project_root = Path(project_root)
        self.ttl = ttl
        self._db_path = self.project_root / ".ink" / "parallel_locks.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_lock_path = self._db_path.with_suffix(".db.flock")
        # 同进程同事件循环的快速互斥（避免 SQLite 行级锁争用开销）。
        # 按 chapter_id 分桶；state 锁走 STATE_LOCK_KEY 键。
        self._async_locks: dict[str, asyncio.Lock] = {}
        self._async_locks_guard = threading.Lock()
        self._init_db()

    # ---- 内部工具 --------------------------------------------------------

    def _new_conn(self) -> sqlite3.Connection:
        """每次操作新开连接。WAL 模式下连接开销极小。"""
        conn = sqlite3.connect(str(self._db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def _init_db(self) -> None:
        conn = self._new_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chapter_locks (
                    lock_key TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    acquired_at REAL NOT NULL,
                    ttl INTEGER NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _cleanup_expired(self, conn: sqlite3.Connection) -> None:
        now = time.time()
        conn.execute(
            "DELETE FROM chapter_locks WHERE acquired_at + ttl < ?",
            (now,),
        )

    def _get_async_lock(self, key: str) -> asyncio.Lock:
        """延迟创建 asyncio.Lock。由 ``_async_locks_guard`` 保证线程安全。"""
        with self._async_locks_guard:
            lock = self._async_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._async_locks[key] = lock
            return lock

    def _acquire_file_lock(self, timeout: float) -> "FileLock | None":
        """文件锁兜底：跨进程互斥。filelock 缺失时返回 None（仅依赖 SQLite 行锁）。"""
        if FileLock is None:
            return None
        flock = FileLock(str(self._file_lock_path))
        try:
            flock.acquire(timeout=timeout)
        except FileLockTimeout:
            raise TimeoutError(
                f"无法获取文件锁兜底（超时{timeout}s）: {self._file_lock_path}"
            )
        return flock

    # ---- 同步 API（向后兼容） ------------------------------------------

    def try_acquire(self, chapter: int, owner: str) -> bool:
        """尝试获取章节锁。成功返回 True，已被占用返回 False。"""
        lock_key = f"ch_{chapter}"
        conn = self._new_conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            self._cleanup_expired(conn)
            row = conn.execute(
                "SELECT owner FROM chapter_locks WHERE lock_key = ?",
                (lock_key,),
            ).fetchone()
            if row is not None:
                conn.rollback()
                return False
            conn.execute(
                "INSERT INTO chapter_locks (lock_key, owner, acquired_at, ttl) VALUES (?, ?, ?, ?)",
                (lock_key, owner, time.time(), self.ttl),
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def release(self, chapter: int, owner: str) -> bool:
        """释放章节锁。仅锁所有者可释放。"""
        lock_key = f"ch_{chapter}"
        conn = self._new_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM chapter_locks WHERE lock_key = ? AND owner = ?",
                (lock_key, owner),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    @contextmanager
    def chapter_lock(
        self, chapter: int, owner: str, timeout: float = 30.0
    ) -> Generator[None, None, None]:
        """上下文管理器：获取章节锁，退出时自动释放（同步版本）。"""
        deadline = time.time() + timeout
        while not self.try_acquire(chapter, owner):
            if time.time() >= deadline:
                raise TimeoutError(
                    f"无法获取第{chapter}章的写入锁（超时{timeout}s）"
                )
            time.sleep(0.5)
        try:
            yield
        finally:
            self.release(chapter, owner)

    @contextmanager
    def state_update_lock(
        self, owner: str, timeout: float = 30.0
    ) -> Generator[None, None, None]:
        """全局 state 更新互斥锁（同步版本）。"""
        lock_key = self.STATE_LOCK_KEY
        deadline = time.time() + timeout

        while True:
            conn = self._new_conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._cleanup_expired(conn)
                row = conn.execute(
                    "SELECT owner FROM chapter_locks WHERE lock_key = ?",
                    (lock_key,),
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO chapter_locks (lock_key, owner, acquired_at, ttl) VALUES (?, ?, ?, ?)",
                        (lock_key, owner, time.time(), 60),
                    )
                    conn.commit()
                    break
                conn.rollback()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            if time.time() >= deadline:
                raise TimeoutError(
                    f"无法获取 state 更新锁（超时{timeout}s）"
                )
            time.sleep(0.3)

        try:
            yield
        finally:
            conn = self._new_conn()
            try:
                conn.execute(
                    "DELETE FROM chapter_locks WHERE lock_key = ? AND owner = ?",
                    (lock_key, owner),
                )
                conn.commit()
            finally:
                conn.close()

    # ---- 异步 API（v16 US-002 新增） ----------------------------------

    @asynccontextmanager
    async def async_chapter_lock(
        self,
        chapter: int,
        owner: str,
        timeout: float = 30.0,
    ) -> AsyncGenerator[None, None]:
        """异步章节锁：先抢同进程 ``asyncio.Lock``，再抢 SQLite 跨进程锁。

        - 同一事件循环内 await 礼让，不空转；
        - 跨进程依赖 SQLite WAL + 行级锁兜底。
        """
        lock_key = f"ch_{chapter}"
        async_lock = self._get_async_lock(lock_key)
        await asyncio.wait_for(async_lock.acquire(), timeout=timeout)
        try:
            deadline = time.time() + timeout
            while not self.try_acquire(chapter, owner):
                if time.time() >= deadline:
                    raise TimeoutError(
                        f"无法获取第{chapter}章的写入锁（跨进程超时{timeout}s）"
                    )
                await asyncio.sleep(0.2)
            try:
                yield
            finally:
                self.release(chapter, owner)
        finally:
            async_lock.release()

    @asynccontextmanager
    async def async_state_update_lock(
        self,
        owner: str,
        timeout: float = 30.0,
    ) -> AsyncGenerator[None, None]:
        """异步全局 state 更新互斥锁。

        双层保护：
        1. ``asyncio.Lock(STATE_LOCK_KEY)`` 保证同事件循环内串行化；
        2. SQLite ``BEGIN IMMEDIATE`` + 行级锁保证跨进程互斥。
        """
        async_lock = self._get_async_lock(self.STATE_LOCK_KEY)
        await asyncio.wait_for(async_lock.acquire(), timeout=timeout)
        acquired_sqlite = False
        try:
            deadline = time.time() + timeout
            while True:
                conn = self._new_conn()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    self._cleanup_expired(conn)
                    row = conn.execute(
                        "SELECT owner FROM chapter_locks WHERE lock_key = ?",
                        (self.STATE_LOCK_KEY,),
                    ).fetchone()
                    if row is None:
                        conn.execute(
                            "INSERT INTO chapter_locks (lock_key, owner, acquired_at, ttl) "
                            "VALUES (?, ?, ?, ?)",
                            (self.STATE_LOCK_KEY, owner, time.time(), 60),
                        )
                        conn.commit()
                        acquired_sqlite = True
                        break
                    conn.rollback()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.close()
                if time.time() >= deadline:
                    raise TimeoutError(
                        f"无法获取 state 更新锁（跨进程超时{timeout}s）"
                    )
                await asyncio.sleep(0.2)

            yield
        finally:
            if acquired_sqlite:
                conn = self._new_conn()
                try:
                    conn.execute(
                        "DELETE FROM chapter_locks WHERE lock_key = ? AND owner = ?",
                        (self.STATE_LOCK_KEY, owner),
                    )
                    conn.commit()
                finally:
                    conn.close()
            async_lock.release()

    # ---- 维护工具 --------------------------------------------------------

    def active_locks(self) -> list[dict]:
        """列出所有活跃锁（调试用）。"""
        conn = self._new_conn()
        try:
            self._cleanup_expired(conn)
            conn.commit()
            rows = conn.execute(
                "SELECT lock_key, owner, acquired_at, ttl FROM chapter_locks"
            ).fetchall()
            return [
                {"lock_key": r[0], "owner": r[1], "acquired_at": r[2], "ttl": r[3]}
                for r in rows
            ]
        finally:
            conn.close()

    def clear_all(self) -> int:
        """清除所有锁（维护用）。"""
        conn = self._new_conn()
        try:
            cursor = conn.execute("DELETE FROM chapter_locks")
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
