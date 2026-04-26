"""US-LR-002: live_review case ID 分配 — prefix 隔离 + 并发安全。"""
from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

from ink_writer.case_library._id_alloc import allocate_case_id
from ink_writer.live_review.case_id import allocate_live_review_id


def _alloc_worker(cases_dir_str: str, year: int) -> str:
    return allocate_live_review_id(Path(cases_dir_str), year=year)


def test_basic_allocate_format(tmp_path):
    cid = allocate_live_review_id(tmp_path, year=2026)
    assert cid == "CASE-LR-2026-0001"


def test_sequential_allocate_increment(tmp_path):
    ids = [allocate_live_review_id(tmp_path, year=2026) for _ in range(3)]
    assert ids == ["CASE-LR-2026-0001", "CASE-LR-2026-0002", "CASE-LR-2026-0003"]


def test_concurrent_allocate_no_gap(tmp_path):
    """4 worker spawn 同时分配，序列严格 0001..0004 无空洞。"""
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=4) as pool:
        ids = pool.starmap(_alloc_worker, [(str(tmp_path), 2026)] * 4)
    assert sorted(ids) == [
        "CASE-LR-2026-0001",
        "CASE-LR-2026-0002",
        "CASE-LR-2026-0003",
        "CASE-LR-2026-0004",
    ]


def test_prefix_isolation_with_legacy_case_alloc(tmp_path):
    """同进程交替分配 CASE-LR- 与 CASE- 不串号；counter file 各自隔离。"""
    lr1 = allocate_live_review_id(tmp_path, year=2026)
    case1 = allocate_case_id(tmp_path, prefix="CASE-2026-")
    lr2 = allocate_live_review_id(tmp_path, year=2026)
    case2 = allocate_case_id(tmp_path, prefix="CASE-2026-")
    assert lr1 == "CASE-LR-2026-0001"
    assert lr2 == "CASE-LR-2026-0002"
    assert case1 == "CASE-2026-0001"
    assert case2 == "CASE-2026-0002"
    assert (tmp_path / ".id_alloc_case_lr_2026.cnt").exists()
    assert (tmp_path / ".id_alloc_case_2026.cnt").exists()


def test_year_isolation(tmp_path):
    """不同年份 prefix 各自隔离 counter。"""
    a = allocate_live_review_id(tmp_path, year=2026)
    b = allocate_live_review_id(tmp_path, year=2027)
    assert a == "CASE-LR-2026-0001"
    assert b == "CASE-LR-2027-0001"
