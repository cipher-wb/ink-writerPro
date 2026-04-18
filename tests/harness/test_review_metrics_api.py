"""US-004: IndexManager.read_review_metrics API 测试。"""
from __future__ import annotations

import pytest


def test_read_review_metrics_returns_none_on_empty(tmp_path, monkeypatch):
    pytest.importorskip("data_modules.index_manager", reason="data_modules not available")
    monkeypatch.chdir(tmp_path)
    from ink_writer.core.infra.config import DataModulesConfig
    from ink_writer.core.index.index_manager import IndexManager
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    idx = IndexManager(cfg)
    assert idx.read_review_metrics(chapter_id=5) is None


def test_read_review_metrics_roundtrip(tmp_path, monkeypatch):
    pytest.importorskip("data_modules.index_manager", reason="data_modules not available")
    monkeypatch.chdir(tmp_path)
    from ink_writer.core.infra.config import DataModulesConfig
    from ink_writer.core.index.index_manager import IndexManager, ReviewMetrics
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    idx = IndexManager(cfg)

    metrics = ReviewMetrics(
        start_chapter=1, end_chapter=5, overall_score=85.0,
        dimension_scores={"content": 90, "quality": 80},
        severity_counts={"critical": 0, "high": 2},
        critical_issues=[], report_file="test.md",
        notes="sample", review_payload_json={"checker_results": {}},
    )
    idx.save_review_metrics(metrics)

    # 命中章节范围
    result = idx.read_review_metrics(chapter_id=3)
    assert result is not None
    assert result["overall_score"] == 85.0
    assert result["dimension_scores"]["content"] == 90

    # 超出范围
    assert idx.read_review_metrics(chapter_id=10) is None
