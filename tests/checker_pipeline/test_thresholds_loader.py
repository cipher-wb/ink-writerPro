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


def test_load_thresholds_includes_m4_sections() -> None:
    """M4 P0：默认 yaml 必须含 7 个 checker 段 + planning_dry_run 段。"""
    result = load_thresholds()

    expected_m4_sections = {
        "genre_novelty",
        "golden_finger_spec",
        "naming_style",
        "protagonist_motive",
        "golden_finger_timing",
        "protagonist_agency_skeleton",
        "chapter_hook_density",
        "planning_dry_run",
    }
    assert expected_m4_sections.issubset(
        result.keys()
    ), f"missing M4 sections: {expected_m4_sections - set(result.keys())}"

    # 关键阈值校验
    assert result["genre_novelty"]["block_threshold"] == 0.40
    assert result["genre_novelty"]["warn_threshold"] == 0.55
    assert result["genre_novelty"]["case_ids"] == ["CASE-2026-M4-0001"]

    assert result["golden_finger_spec"]["block_threshold"] == 0.65
    assert result["golden_finger_spec"]["case_ids"] == ["CASE-2026-M4-0002"]

    assert result["naming_style"]["block_threshold"] == 0.70
    assert result["naming_style"]["case_ids"] == ["CASE-2026-M4-0003"]

    assert result["protagonist_motive"]["block_threshold"] == 0.65
    assert result["protagonist_motive"]["case_ids"] == ["CASE-2026-M4-0004"]

    assert result["golden_finger_timing"]["block_threshold"] == 1.0
    assert result["golden_finger_timing"]["case_ids"] == ["CASE-2026-M4-0005"]

    assert result["protagonist_agency_skeleton"]["block_threshold"] == 0.55
    assert result["protagonist_agency_skeleton"]["case_ids"] == ["CASE-2026-M4-0006"]

    assert result["chapter_hook_density"]["block_threshold"] == 0.70
    assert result["chapter_hook_density"]["case_ids"] == ["CASE-2026-M4-0007"]

    # planning_dry_run 独立计数器
    assert result["planning_dry_run"]["enabled"] is True
    assert result["planning_dry_run"]["observation_runs"] == 5
    assert result["planning_dry_run"]["switch_to_block_after"] is True
    assert result["planning_dry_run"]["counter_path"] == "data/.planning_dry_run_counter"

    # M3 已有 8 段保持不变（向后兼容）
    expected_m3_sections = {
        "writer_self_check",
        "reader_pull",
        "sensory_immersion",
        "high_point",
        "conflict_skeleton",
        "protagonist_agency",
        "rewrite_loop",
        "dry_run",
    }
    assert expected_m3_sections.issubset(result.keys())
    assert result["dry_run"]["observation_chapters"] == 5  # 仍然是 5 章而非 5 runs
