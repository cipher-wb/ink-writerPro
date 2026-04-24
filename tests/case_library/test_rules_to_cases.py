"""US-009 tests — rules_to_cases converter (severity split + idempotency)."""
from __future__ import annotations

import json
from pathlib import Path

from ink_writer.case_library.rules_to_cases import (
    convert_rules_to_cases,
    map_rule_to_case_kwargs,
)
from ink_writer.case_library.store import CaseStore


def _write_rules(tmp_path: Path, rules: list[dict]) -> Path:
    p = tmp_path / "rules.json"
    p.write_text(json.dumps(rules, ensure_ascii=False), encoding="utf-8")
    return p


def test_map_hard_rule_to_active_p1() -> None:
    rule = {
        "id": "EW-0001",
        "category": "opening",
        "rule": "开篇必须有冲突或悬念",
        "why": "钩住读者",
        "severity": "hard",
        "applies_to": ["opening_only"],
        "source_files": ["001.md"],
    }
    kw = map_rule_to_case_kwargs(rule, ingested_at="2026-04-25")
    assert kw["severity"] == "P1"
    assert kw["initial_status"] == "active"
    assert "opening" in kw["tags"]
    assert "from_editor_wisdom" in kw["tags"]
    assert kw["scope_chapter"] == ["opening_only"]
    assert kw["reviewer"] == "星河编辑"
    assert kw["ingested_from"] == "001.md"
    assert kw["domain"] == "writing_quality"
    assert kw["layer"] == ["downstream"]
    assert "钩住读者" in kw["failure_description"]


def test_map_soft_rule_to_pending_p2() -> None:
    rule = {
        "id": "EW-0002",
        "category": "pacing",
        "rule": "x",
        "why": "y",
        "severity": "soft",
        "applies_to": ["all_chapters"],
        "source_files": [],
    }
    kw = map_rule_to_case_kwargs(rule, ingested_at="2026-04-25")
    assert kw["severity"] == "P2"
    assert kw["initial_status"] == "pending"
    assert kw["ingested_from"] is None
    assert "info_only" not in kw["tags"]


def test_map_info_rule_to_pending_p3_with_info_only_tag() -> None:
    rule = {
        "id": "EW-0003",
        "category": "ops",
        "rule": "x",
        "why": "y",
        "severity": "info",
        "applies_to": ["all_chapters"],
        "source_files": [],
    }
    kw = map_rule_to_case_kwargs(rule, ingested_at="2026-04-25")
    assert kw["severity"] == "P3"
    assert kw["initial_status"] == "pending"
    assert "info_only" in kw["tags"]


def test_map_observable_uses_placeholder_with_rule_id() -> None:
    rule = {
        "id": "EW-0042",
        "category": "misc",
        "rule": "x",
        "why": "y",
        "severity": "hard",
        "applies_to": [],
        "source_files": [],
    }
    kw = map_rule_to_case_kwargs(rule, ingested_at="2026-04-25")
    assert any("EW-0042" in obs for obs in kw["observable"])
    # applies_to 为空 → scope_chapter 回退到 ["all"]
    assert kw["scope_chapter"] == ["all"]


def test_convert_creates_cases_idempotently(tmp_path: Path) -> None:
    rules = [
        {
            "id": "EW-0001",
            "category": "opening",
            "rule": "r1",
            "why": "w1",
            "severity": "hard",
            "applies_to": ["opening_only"],
            "source_files": ["a.md"],
        },
        {
            "id": "EW-0002",
            "category": "pacing",
            "rule": "r2",
            "why": "w2",
            "severity": "soft",
            "applies_to": ["all_chapters"],
            "source_files": [],
        },
    ]
    rp = _write_rules(tmp_path, rules)
    library = tmp_path / "case_library"
    (library / "cases").mkdir(parents=True)

    rep = convert_rules_to_cases(
        rules_path=rp, library_root=library, dry_run=False
    )
    assert rep.created == 2
    assert rep.skipped == 0
    assert rep.failed == 0
    assert rep.by_severity == {"hard": 1, "soft": 1}
    assert rep.by_category == {"opening": 1, "pacing": 1}

    # 第二次跑 → 全部 skipped（sha256 dedup）
    rep2 = convert_rules_to_cases(
        rules_path=rp, library_root=library, dry_run=False
    )
    assert rep2.created == 0
    assert rep2.skipped == 2
    # 仍按本次遍历统计 by_severity/by_category
    assert rep2.by_severity == {"hard": 1, "soft": 1}


def test_convert_dry_run_does_not_write(tmp_path: Path) -> None:
    rules = [
        {
            "id": "EW-0001",
            "category": "misc",
            "rule": "r",
            "why": "w",
            "severity": "hard",
            "applies_to": [],
            "source_files": [],
        }
    ]
    rp = _write_rules(tmp_path, rules)
    library = tmp_path / "case_library"
    (library / "cases").mkdir(parents=True)
    rep = convert_rules_to_cases(
        rules_path=rp, library_root=library, dry_run=True
    )
    assert rep.created == 1  # report counts what *would* be created
    store = CaseStore(library)
    assert store.list_ids() == []  # but nothing actually written
