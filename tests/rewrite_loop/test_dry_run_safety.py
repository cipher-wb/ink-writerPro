"""tests for ink_writer.rewrite_loop.dry_run 的并发安全 + 质量关卡 (P0 修复)。

补充原 test_dry_run.py 的盲点：
1. ``increment_dry_run_counter`` 的并发安全（fcntl/msvcrt 文件锁）。
2. ``is_dry_run`` 在 success_criteria.delivered_rate_threshold 配置下，5 章观察期
   内 delivered_rate 不达标时，不切真阻断。
"""

from __future__ import annotations

import json
import multiprocessing as mp
from pathlib import Path

from ink_writer.rewrite_loop.dry_run import (
    increment_dry_run_counter,
    is_dry_run,
    read_dry_run_counter,
)


def _bump_once(path_str: str) -> int:
    return increment_dry_run_counter(base_dir=Path(path_str))


def test_increment_dry_run_counter_concurrent_no_lost_updates(tmp_path: Path) -> None:
    """多进程并发调用 increment 100 次，最终值必须是 100（无丢更新）。"""
    workers = 8
    rounds_per_worker = 25  # 总 200 次
    args = [str(tmp_path)] * (workers * rounds_per_worker)

    ctx = mp.get_context("spawn")  # 跨平台一致行为
    with ctx.Pool(workers) as pool:
        pool.map(_bump_once, args)

    final = read_dry_run_counter(base_dir=tmp_path)
    assert final == workers * rounds_per_worker, (
        f"expected {workers * rounds_per_worker} got {final} — race lost updates"
    )


def _cfg(*, threshold: float | None) -> dict:
    cfg = {
        "dry_run": {
            "enabled": True,
            "observation_chapters": 5,
            "switch_to_block_after": True,
        }
    }
    if threshold is not None:
        cfg["dry_run"]["success_criteria"] = {
            "delivered_rate_threshold": threshold,
        }
    return cfg


def _seed_evidence(
    *,
    project_root: Path,
    book: str,
    delivered: int,
    not_delivered: int,
) -> None:
    """写 ``project_root/data/<book>/chapters/Chxxx.evidence.json``，按 outcome 计数。"""
    chapters = project_root / "data" / book / "chapters"
    chapters.mkdir(parents=True, exist_ok=True)
    idx = 1
    for _ in range(delivered):
        path = chapters / f"Ch{idx:03d}.evidence.json"
        path.write_text(json.dumps({"outcome": "delivered"}), encoding="utf-8")
        idx += 1
    for _ in range(not_delivered):
        path = chapters / f"Ch{idx:03d}.evidence.json"
        path.write_text(
            json.dumps({"outcome": "needs_human_review"}), encoding="utf-8"
        )
        idx += 1


def test_is_dry_run_quality_gate_blocks_switch_when_below_threshold(
    tmp_path: Path,
) -> None:
    """5 章里只有 3 章 delivered（rate=0.6 < 0.8 阈值）→ 保持 dry-run。"""
    project_root = tmp_path
    base = project_root / "data"
    base.mkdir()
    book = "test_book"

    # counter 推到 5（达到 observation_chapters）
    for _ in range(5):
        increment_dry_run_counter(base_dir=base)

    # 3 delivered + 2 needs_human_review
    _seed_evidence(project_root=project_root, book=book, delivered=3, not_delivered=2)

    cfg = _cfg(threshold=0.8)
    assert is_dry_run(cfg, base_dir=base, book=book) is True


def test_is_dry_run_quality_gate_allows_switch_when_above_threshold(
    tmp_path: Path,
) -> None:
    """5 章里 4 章 delivered（rate=0.8 ≥ 0.8 阈值）→ 切真阻断。"""
    project_root = tmp_path
    base = project_root / "data"
    base.mkdir()
    book = "test_book"

    for _ in range(5):
        increment_dry_run_counter(base_dir=base)

    _seed_evidence(project_root=project_root, book=book, delivered=4, not_delivered=1)

    cfg = _cfg(threshold=0.8)
    assert is_dry_run(cfg, base_dir=base, book=book) is False


def test_is_dry_run_no_quality_gate_when_book_missing(tmp_path: Path) -> None:
    """配置了 success_criteria 但未传 book → 关卡 skip，按旧逻辑直接切。"""
    base = tmp_path / "data"
    base.mkdir()

    for _ in range(5):
        increment_dry_run_counter(base_dir=base)

    cfg = _cfg(threshold=0.8)
    assert is_dry_run(cfg, base_dir=base, book=None) is False


def test_is_dry_run_quality_gate_with_no_evidence_stays_dry(tmp_path: Path) -> None:
    """启用关卡但没 evidence 可读 → 保守保持 dry-run（避免空数据触发误切）。"""
    project_root = tmp_path
    base = project_root / "data"
    base.mkdir()

    for _ in range(5):
        increment_dry_run_counter(base_dir=base)

    cfg = _cfg(threshold=0.8)
    assert is_dry_run(cfg, base_dir=base, book="empty_book") is True
