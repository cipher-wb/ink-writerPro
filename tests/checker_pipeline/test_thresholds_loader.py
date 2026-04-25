"""M3 US-001：tests for checker_pipeline.thresholds_loader"""

from __future__ import annotations

from pathlib import Path

import pytest
from ink_writer.checker_pipeline.thresholds_loader import (
    DEFAULT_CONFIG_PATH,
    ThresholdsConfigError,
    load_thresholds,
)


def test_load_thresholds_default_path(tmp_path: Path) -> None:
    """yaml 文件存在时返回 dict，且包含 M3 关键字段。"""
    cfg = tmp_path / "checker-thresholds.yaml"
    cfg.write_text(
        """
writer_self_check:
  rule_compliance_threshold: 0.70
rewrite_loop:
  max_rounds: 3
dry_run:
  enabled: true
  observation_chapters: 5
""",
        encoding="utf-8",
    )

    result = load_thresholds(cfg)

    assert isinstance(result, dict)
    assert result["writer_self_check"]["rule_compliance_threshold"] == 0.70
    assert result["rewrite_loop"]["max_rounds"] == 3
    assert result["dry_run"]["enabled"] is True


def test_load_thresholds_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.yaml"

    with pytest.raises(ThresholdsConfigError, match="not found"):
        load_thresholds(missing)


def test_load_thresholds_invalid_yaml_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "bad.yaml"
    cfg.write_text("writer_self_check:\n  rule_compliance_threshold: [unclosed", encoding="utf-8")

    with pytest.raises(ThresholdsConfigError, match="parse"):
        load_thresholds(cfg)


def test_load_thresholds_real_default_yaml_exists() -> None:
    """仓库默认 config/checker-thresholds.yaml 必须可加载且 8 段齐全。"""
    assert DEFAULT_CONFIG_PATH.exists(), f"missing {DEFAULT_CONFIG_PATH}"

    result = load_thresholds()

    expected_sections = {
        "writer_self_check",
        "reader_pull",
        "sensory_immersion",
        "high_point",
        "conflict_skeleton",
        "protagonist_agency",
        "rewrite_loop",
        "dry_run",
    }
    assert expected_sections.issubset(result.keys())
    assert result["writer_self_check"]["rule_compliance_threshold"] == 0.70
    assert result["rewrite_loop"]["max_rounds"] == 3
    assert result["dry_run"]["enabled"] is True
    assert result["dry_run"]["observation_chapters"] == 5
