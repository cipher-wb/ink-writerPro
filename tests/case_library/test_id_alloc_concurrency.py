"""tests for ink_writer.case_library._id_alloc 并发安全（review §二 P1#6）。"""

from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

from ink_writer.case_library._id_alloc import allocate_case_id


def _alloc_one(args: tuple[str, str]) -> str:
    cases_dir, prefix = args
    return allocate_case_id(Path(cases_dir), prefix)


def test_allocate_case_id_concurrent_no_collision(tmp_path: Path) -> None:
    """8 进程 × 25 次并发分配 CASE-LEARN-NNNN，必须 200 个 ID 全互不重复。"""
    workers = 8
    rounds_per_worker = 25
    total = workers * rounds_per_worker

    args = [(str(tmp_path), "CASE-LEARN-")] * total
    ctx = mp.get_context("spawn")
    with ctx.Pool(workers) as pool:
        ids = pool.map(_alloc_one, args)

    assert len(ids) == total
    assert len(set(ids)) == total, (
        f"collision detected: {total - len(set(ids))} duplicate IDs"
    )
    # 编号 1..total 全覆盖
    nums = sorted(int(i.removeprefix("CASE-LEARN-")) for i in ids)
    assert nums == list(range(1, total + 1))


def test_allocate_case_id_picks_up_external_yaml(tmp_path: Path) -> None:
    """外部手工添加 CASE-LEARN-0042.yaml，下次分配应跳过取 0043。"""
    (tmp_path / "CASE-LEARN-0042.yaml").write_text("# manual", encoding="utf-8")
    new_id = allocate_case_id(tmp_path, "CASE-LEARN-")
    assert new_id == "CASE-LEARN-0043"


def test_allocate_case_id_starts_from_one_in_empty_dir(tmp_path: Path) -> None:
    new_id = allocate_case_id(tmp_path, "CASE-PROMOTE-")
    assert new_id == "CASE-PROMOTE-0001"


def test_allocate_case_id_two_prefixes_independent(tmp_path: Path) -> None:
    """LEARN 与 PROMOTE 的 counter 互不干扰。"""
    a = allocate_case_id(tmp_path, "CASE-LEARN-")
    b = allocate_case_id(tmp_path, "CASE-PROMOTE-")
    c = allocate_case_id(tmp_path, "CASE-LEARN-")
    assert a == "CASE-LEARN-0001"
    assert b == "CASE-PROMOTE-0001"
    assert c == "CASE-LEARN-0002"


def _alloc_one_with_slow_scan(args: tuple[str, str]) -> str:
    """Worker：在子进程内 monkey-patch ``_scan_max`` 慢 50ms 后再分配。

    spawn-context 下每个 worker 是独立进程，patch 不会传染回父进程。设计意图：
    模拟"首次创建 counter 时 _scan_max 耗时长" → 验证多 worker 排队拿锁后 ID
    序列连续无空洞，证明初始化已挪进锁内串行（US-004）。
    """
    import time

    from ink_writer.case_library import _id_alloc as mod

    cases_dir, prefix = args
    original = mod._scan_max

    def slow_scan_max(cd, pf):
        time.sleep(0.05)
        return original(cd, pf)

    mod._scan_max = slow_scan_max
    return mod.allocate_case_id(Path(cases_dir), prefix)


def test_allocate_case_id_initial_state_atomic(tmp_path: Path) -> None:
    """US-004：counter 不存在时多进程同时首次分配，ID 必须连续 1..N（无空洞）。

    旧实现："先在锁外 ``write_text(scan_max)`` 创建文件，再上锁"中间窗口期，
    其他进程的 ``not counter_path.exists()`` 可能拍空再覆盖一次——靠锁内
    glob 兜底取 max 救场。新实现把"创建+读取+初始化"全挪进锁内 ('a+')，
    彻底消除窗口；本测试用 50ms slow ``_scan_max`` 拉长锁内停留时间（让 race
    窗口被严重放大），仍要求 ID 序列连续。
    """
    workers = 4
    args = [(str(tmp_path), "CASE-LEARN-")] * workers
    ctx = mp.get_context("spawn")
    with ctx.Pool(workers) as pool:
        ids = pool.map(_alloc_one_with_slow_scan, args)

    assert len(ids) == workers
    assert len(set(ids)) == workers, f"duplicate IDs: {ids}"
    nums = sorted(int(i.removeprefix("CASE-LEARN-")) for i in ids)
    assert nums == list(range(1, workers + 1)), f"non-contiguous IDs: {nums}"
