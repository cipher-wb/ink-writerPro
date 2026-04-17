"""US-023: PipelineManager 诚实降级测试。

验证 parallel>1 触发 RuntimeWarning；parallel=1 不触发。
"""
from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from ink_writer.parallel.pipeline_manager import PipelineConfig, PipelineManager


def test_parallel_gt_1_triggers_warning(tmp_path):
    cfg = PipelineConfig(project_root=tmp_path, plugin_root=tmp_path, parallel=2)
    with pytest.warns(RuntimeWarning, match="parallel=2.*experimental"):
        PipelineManager(cfg)


def test_parallel_eq_1_no_warning(tmp_path):
    cfg = PipelineConfig(project_root=tmp_path, plugin_root=tmp_path, parallel=1)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        # 不应触发 RuntimeWarning；如触发 pytest 会 raise
        PipelineManager(cfg)
