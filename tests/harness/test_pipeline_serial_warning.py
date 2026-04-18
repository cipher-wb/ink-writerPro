"""US-023 / US-002：PipelineManager parallel 模式行为回归。

v13 US-023（FIX-02B）：parallel>1 触发 RuntimeWarning（ChapterLockManager 未接入）。
v16 US-002：ChapterLockManager 已接入，不再触发 RuntimeWarning；任何 parallel 值都不应
向调用方泄露 RuntimeWarning。保留此测试作为「不回退」守卫——若未来再次出现对 parallel
模式的隐式诚实降级，需显式更新此测试。
"""
from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from ink_writer.parallel.pipeline_manager import PipelineConfig, PipelineManager


def test_parallel_gt_1_no_longer_warns(tmp_path: Path) -> None:
    """v16 US-002：parallel>1 不再触发 RuntimeWarning（锁已接入）。"""
    cfg = PipelineConfig(project_root=tmp_path, plugin_root=tmp_path, parallel=4)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        # 不应触发 RuntimeWarning；若触发 pytest 会 raise。
        PipelineManager(cfg)


def test_parallel_eq_1_no_warning(tmp_path: Path) -> None:
    cfg = PipelineConfig(project_root=tmp_path, plugin_root=tmp_path, parallel=1)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        PipelineManager(cfg)


def test_chapter_lock_manager_instantiated(tmp_path: Path) -> None:
    """v16 US-002：PipelineManager 必须持有 ChapterLockManager 实例。"""
    cfg = PipelineConfig(project_root=tmp_path, plugin_root=tmp_path, parallel=2)
    mgr = PipelineManager(cfg)
    assert mgr._lock is not None
    # TTL 应为 US-002 约定的 300s（覆盖单章写作 + 审查时长）。
    assert mgr._lock.ttl == 300
    # DB 应落在 project_root/.ink/parallel_locks.db。
    expected_db = tmp_path / ".ink" / "parallel_locks.db"
    assert mgr._lock._db_path == expected_db
