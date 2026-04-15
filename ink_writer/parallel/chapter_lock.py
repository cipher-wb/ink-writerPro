"""章节级写入锁管理，防止并发写入同一章节或竞争 state 更新。"""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


class ChapterLockManager:
    """基于 SQLite 的章节写入锁，支持跨进程协调。

    利用 SQLite WAL 模式的原子性实现分布式锁：
    - 每个章节有独立的锁记录
    - 锁带有 TTL，过期自动释放（防止进程崩溃后死锁）
    - 支持 state.json 更新的全局互斥
    """

    DEFAULT_TTL = 600  # 10 minutes
    STATE_LOCK_KEY = "__state_update__"

    def __init__(self, project_root: Path, ttl: int = DEFAULT_TTL):
        self.project_root = project_root
        self.ttl = ttl
        self._db_path = project_root / ".ink" / "parallel_locks.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 10000")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chapter_locks (
                lock_key TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                acquired_at REAL NOT NULL,
                ttl INTEGER NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 10000")
            self._local.conn = conn
        return self._local.conn

    def _cleanup_expired(self, conn: sqlite3.Connection) -> None:
        now = time.time()
        conn.execute(
            "DELETE FROM chapter_locks WHERE acquired_at + ttl < ?",
            (now,),
        )

    def try_acquire(self, chapter: int, owner: str) -> bool:
        """尝试获取章节锁。成功返回 True，已被占用返回 False。"""
        lock_key = f"ch_{chapter}"
        conn = self._get_conn()
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

    def release(self, chapter: int, owner: str) -> bool:
        """释放章节锁。仅锁所有者可释放。"""
        lock_key = f"ch_{chapter}"
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM chapter_locks WHERE lock_key = ? AND owner = ?",
            (lock_key, owner),
        )
        conn.commit()
        return cursor.rowcount > 0

    @contextmanager
    def chapter_lock(
        self, chapter: int, owner: str, timeout: float = 30.0
    ) -> Generator[None, None, None]:
        """上下文管理器：获取章节锁，退出时自动释放。"""
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
        """全局 state 更新互斥锁。"""
        lock_key = self.STATE_LOCK_KEY
        conn = self._get_conn()
        deadline = time.time() + timeout

        while True:
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
            if time.time() >= deadline:
                raise TimeoutError(
                    f"无法获取 state 更新锁（超时{timeout}s）"
                )
            time.sleep(0.3)

        try:
            yield
        finally:
            conn.execute(
                "DELETE FROM chapter_locks WHERE lock_key = ? AND owner = ?",
                (lock_key, owner),
            )
            conn.commit()

    def active_locks(self) -> list[dict]:
        """列出所有活跃锁（调试用）。"""
        conn = self._get_conn()
        self._cleanup_expired(conn)
        conn.commit()
        rows = conn.execute(
            "SELECT lock_key, owner, acquired_at, ttl FROM chapter_locks"
        ).fetchall()
        return [
            {"lock_key": r[0], "owner": r[1], "acquired_at": r[2], "ttl": r[3]}
            for r in rows
        ]

    def clear_all(self) -> int:
        """清除所有锁（维护用）。"""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM chapter_locks")
        conn.commit()
        return cursor.rowcount
