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
