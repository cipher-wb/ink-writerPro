from __future__ import annotations

import json
from pathlib import Path

import pytest

from ink_writer.core.auto.blueprint_scanner import find_blueprint
from ink_writer.core.auto.blueprint_to_quick_draft import (
    BlueprintValidationError,
    parse_blueprint,
    to_quick_draft,
    validate,
)
from ink_writer.core.auto.state_detector import ProjectState, detect_project_state
from ink_writer.core.cli.checkpoint_utils import (
    count_issues_by_severity,
    determine_checkpoint,
    disambiguation_urgency,
    get_disambiguation_backlog,
    report_has_issues,
    review_range,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "phase3"


def test_parse_blueprint_normalizes_headers_comments_and_aliases() -> None:
    parsed = parse_blueprint(FIXTURES / "quick_blueprint.md")

    assert parsed["平台"] == "番茄小说"
    assert parsed["题材方向"] == "都市悬疑+轻异能"
    assert parsed["女主姓名"] == "林秋白"
    assert parsed["钩子1"].startswith("事故记录显示")
    assert "阶段 3" not in parsed["题材方向"]


def test_validate_accepts_complete_blueprint_and_rejects_missing_required(tmp_path: Path) -> None:
    parsed = parse_blueprint(FIXTURES / "quick_blueprint.md")
    validate(parsed)

    missing = dict(parsed)
    missing["核心冲突"] = ""
    with pytest.raises(BlueprintValidationError, match="核心冲突"):
        validate(missing)

    empty_section = tmp_path / "empty.md"
    empty_section.write_text("### 题材方向\n\n### 核心冲突\n雨夜追凶\n", encoding="utf-8")
    parsed_empty = parse_blueprint(empty_section)
    assert parsed_empty["题材方向"] is None


def test_validate_rejects_blacklisted_golden_finger() -> None:
    parsed = parse_blueprint(FIXTURES / "quick_blueprint.md")
    parsed["能力一句话"] = "系统签到后获得全部线索"

    with pytest.raises(BlueprintValidationError, match="系统签到"):
        validate(parsed)


def test_to_quick_draft_maps_fanqie_defaults_and_missing_optional_fields() -> None:
    parsed = parse_blueprint(FIXTURES / "quick_blueprint.md")
    draft = to_quick_draft(parsed)

    assert draft["platform"] == "fanqie"
    assert draft["aggression_level"] == 3
    assert draft["chapter_words"] == 1500
    assert draft["target_chapters"] == 80
    assert draft["主角姓名"] == "许照"
    assert "女主人设" not in draft["__missing__"]
    assert "书名" in draft["__missing__"]


def test_to_quick_draft_falls_back_on_bad_numbers_and_auto_values() -> None:
    parsed = parse_blueprint(FIXTURES / "quick_blueprint.md")
    parsed.update({
        "平台": "未知平台",
        "激进度档位": "5",
        "目标章数": "八十",
        "目标字数": "很多",
        "主角姓名": "AUTO",
    })
    draft = to_quick_draft(parsed)

    assert draft["platform"] == "qidian"
    assert draft["aggression_level"] == 2
    assert draft["target_chapters"] == 600
    assert draft["target_words"] == 1_800_000
    assert "主角姓名" in draft["__missing__"]


def test_find_blueprint_chooses_largest_non_blacklisted_markdown(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("说明", encoding="utf-8")
    (tmp_path / "outline.draft.md").write_text("草稿", encoding="utf-8")
    small = tmp_path / "短蓝本.md"
    large = tmp_path / "雨夜事故蓝本.md"
    small.write_text("### 题材方向\n都市\n", encoding="utf-8")
    large.write_text("### 题材方向\n都市悬疑\n" + "事故倒计时\n" * 20, encoding="utf-8")

    assert find_blueprint(tmp_path) == large


def test_find_blueprint_returns_none_for_non_dir_or_only_blacklisted(tmp_path: Path) -> None:
    only_blacklist = tmp_path / "only"
    only_blacklist.mkdir()
    (only_blacklist / "AGENTS.md").write_text("规则", encoding="utf-8")
    (only_blacklist / "notes.draft.md").write_text("草稿", encoding="utf-8")

    assert find_blueprint(tmp_path / "missing") is None
    assert find_blueprint(only_blacklist) is None


def test_detect_project_state_covers_uninit_no_outline_writing_completed_and_bad_json(tmp_path: Path) -> None:
    assert detect_project_state(tmp_path / "missing") == ProjectState.S0_UNINIT

    project = tmp_path / "雾港问心录"
    ink = project / ".ink"
    ink.mkdir(parents=True)
    (ink / "state.json").write_text('{"progress": {"is_completed": false}}', encoding="utf-8")
    assert detect_project_state(project) == ProjectState.S1_NO_OUTLINE

    outline_dir = project / "大纲"
    outline_dir.mkdir()
    (outline_dir / "总纲.md").write_text("总纲不算章纲", encoding="utf-8")
    assert detect_project_state(project) == ProjectState.S1_NO_OUTLINE

    (outline_dir / "第1章-雨棚下的回响.md").write_text("章纲", encoding="utf-8")
    assert detect_project_state(project) == ProjectState.S2_WRITING

    (ink / "state.json").write_text('{"progress": {"is_completed": true}}', encoding="utf-8")
    assert detect_project_state(project) == ProjectState.S3_COMPLETED

    (ink / "state.json").write_text("{bad json", encoding="utf-8")
    assert detect_project_state(project) == ProjectState.S0_UNINIT


def test_checkpoint_level_review_range_and_disambiguation_urgency() -> None:
    assert determine_checkpoint(4)._asdict() == {
        "review": False,
        "audit": None,
        "macro": None,
        "disambig": False,
    }
    assert determine_checkpoint(5).review is True
    assert determine_checkpoint(10).audit == "quick"
    assert determine_checkpoint(20).macro == "Tier2"
    assert determine_checkpoint(200).macro == "Tier3"
    assert review_range(3) == (1, 3)
    assert review_range(20) == (16, 20)
    assert disambiguation_urgency(20) == "normal"
    assert disambiguation_urgency(21) == "warning"
    assert disambiguation_urgency(101) == "critical"


def test_report_issue_scanning_counts_missing_and_encoding_errors(tmp_path: Path) -> None:
    report = tmp_path / "审查报告.md"
    report.write_text(
        "\n".join([
            "- 🔴 critical: 主角动机断裂",
            "- 🟠 high: 伏笔逾期",
            "- 🟡 medium: 情绪曲线偏平",
            "- 🔵 low: 标点格式问题",
        ]),
        encoding="utf-8",
    )
    broken = tmp_path / "broken.md"
    broken.write_bytes(b"\xff\xfe\x00")

    assert report_has_issues(report) is True
    assert count_issues_by_severity(report) == {
        "critical": 1,
        "high": 1,
        "medium": 1,
        "low": 1,
    }
    assert report_has_issues(tmp_path / "missing.md") is False
    assert report_has_issues(broken) is False
    assert count_issues_by_severity(broken) == {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
    }


def test_get_disambiguation_backlog_handles_valid_missing_and_malformed_state(tmp_path: Path) -> None:
    project = tmp_path / "project"
    ink = project / ".ink"
    ink.mkdir(parents=True)
    (ink / "state.json").write_text(
        json.dumps({"disambiguation_pending": [{"id": 1}, {"id": 2}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert get_disambiguation_backlog(project) == 2

    (ink / "state.json").write_text("{bad", encoding="utf-8")
    assert get_disambiguation_backlog(project) == 0
    assert get_disambiguation_backlog(tmp_path / "missing") == 0
