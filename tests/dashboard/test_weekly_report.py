"""Tests for ink_writer.dashboard.weekly_report (US-006)."""
from __future__ import annotations

from pathlib import Path

from ink_writer.dashboard.weekly_report import (
    _week_range,
    generate_weekly_report,
)
from tests.dashboard.conftest import (
    write_chapter_evidence,
    write_counter,
    write_meta_rule_proposal,
)


def test_week_range_w17() -> None:
    """ISO week 17 of 2026 spans 2026-04-20 (Mon) → 2026-04-26 (Sun)."""
    assert _week_range(17, 2026) == ("2026-04-20", "2026-04-26")


def test_generate_creates_report_file(tmp_path: Path) -> None:
    """Default output goes to reports/weekly/<Y>-W<NN>.md and contains all 5 H2 sections."""
    base_dir = tmp_path / "data"
    base_dir.mkdir(parents=True, exist_ok=True)
    # Build an empty case_library so CaseStore loads cleanly.
    (base_dir / "case_library").mkdir(parents=True, exist_ok=True)

    out_path = tmp_path / "reports" / "weekly" / "2026-W17.md"
    written = generate_weekly_report(
        week_num=17,
        year=2026,
        base_dir=base_dir,
        out_path=out_path,
    )
    assert written == out_path
    assert out_path.is_file()
    content = out_path.read_text(encoding="utf-8")
    # 5 H2 sections (PRD AC).
    assert "## 4 大指标" in content
    assert "## Layer 4 复发追踪" in content
    assert "## Layer 5 元规则浮现" in content
    assert "## Dry-run 状态" in content
    assert "## 行动项" in content
    # Header carries the ISO range.
    assert "2026-04-20" in content
    assert "2026-04-26" in content


def test_report_includes_action_items(tmp_path: Path) -> None:
    """counter=10 + 100% pass rate → action item '评估 M3 dry-run 切真';
    pending meta-rule → '审批 1 条 pending 元规则'."""
    base_dir = tmp_path / "data"
    (base_dir / "case_library").mkdir(parents=True, exist_ok=True)

    write_counter(base_dir=base_dir, filename=".dry_run_counter", value=10)
    # 4 chapter evidences, all delivered → 100% pass rate, with counter=10
    # this satisfies the recommend_dry_run_switch threshold.
    for idx in range(4):
        write_chapter_evidence(
            base_dir=base_dir,
            book="bookA",
            chapter=f"ch{idx:03d}",
            outcome="delivered",
        )

    write_meta_rule_proposal(
        meta_rules_dir=base_dir / "case_library" / "meta_rules",
        proposal_id="MR-0001",
        status="pending",
        covered_cases=["CASE-0001"],
    )

    out_path = tmp_path / "report.md"
    generate_weekly_report(
        week_num=17,
        year=2026,
        base_dir=base_dir,
        out_path=out_path,
    )

    content = out_path.read_text(encoding="utf-8")
    assert "## 行动项" in content
    assert "评估 M3 dry-run 切真" in content
    assert "审批 1 条 pending 元规则" in content
    # Dry-run section reflects counter=10 + 100% pass.
    assert "M3 章节" in content
    assert "100.0%" in content
