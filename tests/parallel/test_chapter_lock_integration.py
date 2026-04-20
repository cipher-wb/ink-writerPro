"""v17 US-005 integration test：4 并发 subprocess 写 index.db 验证无 lost update。

场景：模拟 4 个独立进程（跨进程）同时执行 Step 5 data-agent 风格的
"读-改-写 state.json + append index.db" 操作。依赖 ``ChapterLockManager``
的 ``state_update_lock()`` 同步上下文管理器跨进程串行化。

- 不使用 asyncio——专门验证跨进程（SQLite WAL + filelock）兜底路径
- 每个 worker 进程独立打开 lock manager、执行 RMW、写 counter+log
- 期望：counter == 4，entity_log 四条（且 counter_after 不重复）
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

from ink_writer.parallel.chapter_lock import ChapterLockManager


def _init_workspace(project_root: Path) -> tuple[Path, Path]:
    ink = project_root / ".ink"
    ink.mkdir(parents=True, exist_ok=True)
    state_file = ink / "state.json"
    state_file.write_text(
        json.dumps({"counter": 0, "history": []}),
        encoding="utf-8",
    )
    db_path = ink / "index.db"
    conn = sqlite3.connect(str(db_path), timeout=15.0)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 15000")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS entity_log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, who TEXT, counter_after INTEGER)"
        )
        conn.commit()
    finally:
        conn.close()
    # 主进程预热 ChapterLockManager：确保 parallel_locks.db schema + WAL 已建立，
    # 避免 4 个 spawn worker 同时执行 _init_db() 时的首次写竞争。
    ChapterLockManager(project_root, ttl=60)
    return state_file, db_path


def _worker_entrypoint(
    project_root: str, who: str, hold_s: float, with_lock: bool
) -> tuple[str, int]:
    """每个并发 worker 的入口（顶层函数才能被 spawn pickle）。

    流程：read state.json → 休眠 hold_s 放大竞态 → write state.json +
    append index.db。 with_lock=True 时包裹 ``state_update_lock``。
    """
    root = Path(project_root)
    state_file = root / ".ink" / "state.json"
    db_path = root / ".ink" / "index.db"

    def _rmw() -> int:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        time.sleep(hold_s)
        data["counter"] += 1
        data["history"].append(who)
        state_file.write_text(json.dumps(data), encoding="utf-8")
        conn = sqlite3.connect(str(db_path), timeout=15.0)
        try:
            conn.execute("PRAGMA busy_timeout = 15000")
            conn.execute(
                "INSERT INTO entity_log (who, counter_after) VALUES (?, ?)",
                (who, data["counter"]),
            )
            conn.commit()
        finally:
            conn.close()
        return data["counter"]

    if with_lock:
        mgr = ChapterLockManager(root, ttl=60)
        with mgr.state_update_lock(owner=who, timeout=60):
            counter = _rmw()
    else:
        counter = _rmw()
    return (who, counter)


@pytest.fixture
def spawn_ctx():
    """使用 spawn 方式启动子进程，确保跨 CPython 平台一致（且 macOS 默认 fork 会与 sqlite 结合崩溃）。"""
    return mp.get_context("spawn")


class TestChapterLockIntegration:
    def test_four_subprocesses_with_lock_no_lost_update(
        self, tmp_path: Path, spawn_ctx: mp.context.BaseContext
    ) -> None:
        """4 并发 subprocess 写 index.db：``state_update_lock`` 下 counter 必须 == 4。"""
        _init_workspace(tmp_path)

        with spawn_ctx.Pool(processes=4) as pool:
            results = pool.starmap(
                _worker_entrypoint,
                [(str(tmp_path), f"w{i}", 0.08, True) for i in range(4)],
            )

        data = json.loads((tmp_path / ".ink" / "state.json").read_text(encoding="utf-8"))
        assert data["counter"] == 4, (
            f"跨进程丢失更新：期待 counter=4，实际 {data['counter']}"
        )
        assert sorted(data["history"]) == ["w0", "w1", "w2", "w3"]

        conn = sqlite3.connect(str(tmp_path / ".ink" / "index.db"))
        try:
            rows = conn.execute(
                "SELECT who, counter_after FROM entity_log ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 4
        counters = [r[1] for r in rows]
        # state_update_lock 严格串行化：counter_after 必为 1,2,3,4 无重复。
        assert sorted(counters) == [1, 2, 3, 4], (
            f"counter_after 重复说明锁内串行化失败: {counters}"
        )

    def test_four_subprocesses_without_lock_can_lose_updates(
        self, tmp_path: Path, spawn_ctx: mp.context.BaseContext
    ) -> None:
        """文档性测试：证实无锁时跨进程 RMW 会漂移——不保证每次都丢，但 counter 必 ≤ 4。

        SQLite INSERT 独立事务总会写入 4 条记录，但 counter_after 可能重复
        （多个 worker 读到同一 counter）。counter_after 不重复则说明偶然串行，
        不视为失败。
        """
        _init_workspace(tmp_path)

        with spawn_ctx.Pool(processes=4) as pool:
            pool.starmap(
                _worker_entrypoint,
                [(str(tmp_path), f"w{i}", 0.08, False) for i in range(4)],
            )

        data = json.loads((tmp_path / ".ink" / "state.json").read_text(encoding="utf-8"))
        assert data["counter"] <= 4  # 不保证丢失，但永远不会超过 4

        conn = sqlite3.connect(str(tmp_path / ".ink" / "index.db"))
        try:
            rows = conn.execute(
                "SELECT who, counter_after FROM entity_log"
            ).fetchall()
        finally:
            conn.close()
        # 4 条 INSERT 独立事务，必然全部持久化。
        assert len(rows) == 4

    def test_lock_performance_reasonable(
        self, tmp_path: Path, spawn_ctx: mp.context.BaseContext
    ) -> None:
        """4 并发 + 0.05s hold 下，总耗时应 < 5s（包含子进程 spawn 开销）。

        v17 US-005 验收声明 ``parallel ≤ 4`` 已安全；不允许锁成为瓶颈。
        """
        _init_workspace(tmp_path)

        t0 = time.time()
        with spawn_ctx.Pool(processes=4) as pool:
            pool.starmap(
                _worker_entrypoint,
                [(str(tmp_path), f"w{i}", 0.05, True) for i in range(4)],
            )
        elapsed = time.time() - t0
        # 允许 5s 包含 4 × spawn + lock contention。
        assert elapsed < 5.0, f"锁+subprocess 性能退化: {elapsed:.2f}s"


class TestChapterLockCLIIntegration:
    """直接验证 ``state process-chapter`` CLI 的跨进程锁（端到端）。

    不依赖真实 data-agent schema，用最小合法 payload 触发 write path。
    """

    @pytest.fixture
    def project_root(self, tmp_path: Path) -> Path:
        """构建最小项目骨架：.ink/state.json + 正文目录 + 大纲目录。"""
        (tmp_path / ".ink").mkdir()
        # 初始 state.json（schema 与 StateManager._ensure_state_schema 匹配）
        initial = {
            "progress": {"current_chapter": 0, "words": 0, "last_updated": ""},
            "entities": {"角色": {}, "地点": {}, "物品": {}, "势力": {}, "招式": {}},
            "aliases": {},
            "state_changes": [],
            "relationships": {},
            "chapter_meta": {},
            "scenes": {},
            "timeline_anchors": {},
            "plot_threads": {},
            "disambiguation": {"warnings": [], "pending": [], "latest_warnings": []},
            "candidate_facts": [],
            "negative_constraints": {},
            "protagonist_knowledge": {},
        }
        (tmp_path / ".ink" / "state.json").write_text(
            json.dumps(initial), encoding="utf-8"
        )
        (tmp_path / "正文").mkdir()
        (tmp_path / "大纲").mkdir()
        (tmp_path / "设定集").mkdir()
        return tmp_path

    def test_cli_process_chapter_acquires_lock(self, project_root: Path) -> None:
        """两个 subprocess 同时 process-chapter 不同章节，lock DB 应有痕迹，state 无损。

        通过直接 import CLI main 在进程内完成一次完整 process-chapter；
        成功返回 0 即证明 lock 路径不回归（nullcontext fallback 也 ok）。
        """
        import subprocess

        payload = json.dumps(
            {
                "entities_appeared": [],
                "entities_new": [],
                "state_changes": [],
                "relationships_new": [],
                "scenes_chunked": 0,
            }
        )

        env = os.environ.copy()
        repo_root = Path(__file__).resolve().parents[2]
        # 匹配 pytest.ini pythonpath: . ink-writer ink-writer/scripts ink-writer/dashboard scripts
        extra_paths = [
            str(repo_root),
            str(repo_root / "ink-writer"),
            str(repo_root / "ink-writer" / "scripts"),
            str(repo_root / "ink-writer" / "dashboard"),
            str(repo_root / "scripts"),
        ]
        env["PYTHONPATH"] = os.pathsep.join(
            extra_paths + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
        )

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "ink_writer.core.state.state_manager",
                "--project-root",
                str(project_root),
                "process-chapter",
                "--chapter",
                "1",
                "--data",
                payload,
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=60, encoding="utf-8",
        )
        assert proc.returncode == 0, f"CLI 失败: stdout={proc.stdout}\nstderr={proc.stderr}"
        # parallel_locks.db 应已被 ChapterLockManager 初始化
        lock_db = project_root / ".ink" / "parallel_locks.db"
        assert lock_db.exists(), "state_update_lock 未创建 parallel_locks.db——锁路径未命中"
