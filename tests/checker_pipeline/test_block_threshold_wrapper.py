"""M3 US-006：tests for checker_pipeline.block_threshold_wrapper"""

from __future__ import annotations

from pathlib import Path

import pytest
from ink_writer.checker_pipeline.block_threshold_wrapper import (
    CheckerOutcome,
    apply_block_threshold,
)


@pytest.fixture
def thresholds_cfg(tmp_path: Path) -> dict:
    cfg_path = tmp_path / "thresholds.yaml"
    cfg_path.write_text(
        """
reader_pull:
  block_threshold: 60
  warn_threshold: 75
  bound_cases:
    - tag: reader_immersion
sensory_immersion:
  block_threshold: 65
  warn_threshold: 78
  bound_cases:
    - tag: sensory_grounding
high_point:
  block_threshold: 70
  warn_threshold: 80
  bound_cases:
    - tag: payoff_pacing
""",
        encoding="utf-8",
    )
    from ink_writer.checker_pipeline.thresholds_loader import load_thresholds

    return load_thresholds(cfg_path)


def test_apply_block_threshold_passes(thresholds_cfg: dict) -> None:
    outcome = apply_block_threshold(
        checker_id="reader_pull",
        score=78,
        cfg=thresholds_cfg,
        is_dry_run=False,
        case_store=None,
    )
    assert isinstance(outcome, CheckerOutcome)
    assert outcome.score == 78
    assert outcome.block_threshold == 60
    assert outcome.blocked is False
    assert outcome.would_have_blocked is False


def test_apply_block_threshold_blocks(thresholds_cfg: dict) -> None:
    outcome = apply_block_threshold(
        checker_id="high_point",
        score=65,
        cfg=thresholds_cfg,
        is_dry_run=False,
        case_store=None,
    )
    assert outcome.blocked is True
    assert outcome.would_have_blocked is True


def test_apply_block_threshold_dry_run_does_not_block(thresholds_cfg: dict) -> None:
    """dry-run 期间 blocked 字段标记 False (不真阻断), would_have_blocked 留痕。"""
    outcome = apply_block_threshold(
        checker_id="high_point",
        score=65,
        cfg=thresholds_cfg,
        is_dry_run=True,
        case_store=None,
    )
    assert outcome.blocked is False
    assert outcome.would_have_blocked is True


def test_apply_block_threshold_unknown_checker_uses_defaults(thresholds_cfg: dict) -> None:
    """未在 yaml 配置的 checker → blocked=False (永不 blocked) + notes 含名字提示."""
    outcome = apply_block_threshold(
        checker_id="non_configured",
        score=50,
        cfg=thresholds_cfg,
        is_dry_run=False,
        case_store=None,
    )
    assert outcome.blocked is False
    assert "non_configured" in outcome.notes
    assert "not in thresholds yaml" in outcome.notes
