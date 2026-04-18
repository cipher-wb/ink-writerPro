"""US-015 (FIX-17 P4b): canon-drift-detector 识别跨章矛盾。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ink_writer.propagation import detect_drifts
from ink_writer.propagation.drift_detector import _drifts_from_data


def _mk_review_data(*, critical_issues=None, checker_results=None) -> dict:
    return {
        "critical_issues": critical_issues or [],
        "checker_results": checker_results or {},
    }


# ---------- unit: _drifts_from_data ----------

def test_critical_issue_with_backward_target_detected():
    data = _mk_review_data(critical_issues=[
        {
            "type": "cross_chapter_conflict",
            "target_chapter": 32,
            "rule": "character.power_level 回溯矛盾",
            "severity": "high",
            "suggested_fix": "在第 32 章补充突破伏笔",
        }
    ])
    drifts = _drifts_from_data(50, data)
    assert len(drifts) == 1
    d = drifts[0]
    assert d.chapter_detected == 50
    assert d.target_chapter == 32
    assert d.severity == "high"
    assert "32" in d.suggested_fix
    assert d.status == "open"


def test_consistency_checker_violation_detected():
    data = _mk_review_data(checker_results={
        "consistency-checker": {
            "violations": [
                {
                    "rule": "location.shrine_state",
                    "target_chapter": 20,
                    "severity": "medium",
                    "message": "神殿被毁状态在 ch20 之前未铺垫",
                }
            ]
        }
    })
    drifts = _drifts_from_data(45, data)
    assert len(drifts) == 1
    assert drifts[0].target_chapter == 20
    assert drifts[0].rule_violation.startswith("consistency-checker:")


def test_continuity_checker_violation_detected():
    data = _mk_review_data(checker_results={
        "continuity-checker": {
            "issues": [
                {
                    "type": "timeline_mismatch",
                    "ref_chapter": 10,
                    "severity": "critical",
                }
            ]
        }
    })
    drifts = _drifts_from_data(30, data)
    assert len(drifts) == 1
    assert drifts[0].target_chapter == 10
    assert drifts[0].severity == "critical"


def test_forward_reference_is_not_drift():
    # target_chapter >= current → 不属于反向矛盾
    data = _mk_review_data(critical_issues=[
        {"type": "generic", "target_chapter": 60, "severity": "low"}
    ])
    drifts = _drifts_from_data(50, data)
    assert drifts == []


def test_unrelated_issue_is_ignored():
    data = _mk_review_data(critical_issues=[
        {"type": "stylistic", "severity": "low", "message": "文笔问题"}
    ])
    drifts = _drifts_from_data(50, data)
    assert drifts == []


def test_multiple_drifts_get_unique_ids():
    data = _mk_review_data(
        critical_issues=[
            {"type": "cross_chapter_conflict", "target_chapter": 10, "severity": "high"},
            {"type": "cross_chapter_conflict", "target_chapter": 20, "severity": "medium"},
        ],
        checker_results={
            "consistency-checker": {
                "violations": [
                    {"rule": "x", "target_chapter": 15, "severity": "high"}
                ]
            }
        },
    )
    drifts = _drifts_from_data(40, data)
    ids = [d.debt_id for d in drifts]
    assert len(drifts) == 3
    assert len(set(ids)) == 3


def test_json_string_critical_issues_are_parsed():
    data = {
        "critical_issues": json.dumps([
            {"type": "cross_chapter_conflict", "target_chapter": 5, "severity": "critical"}
        ]),
        "checker_results": {},
    }
    drifts = _drifts_from_data(20, data)
    assert len(drifts) == 1
    assert drifts[0].target_chapter == 5


# ---------- detect_drifts: range + records 注入 ----------

def test_detect_drifts_with_records_mock(tmp_path: Path):
    records = {
        50: _mk_review_data(critical_issues=[
            {"type": "cross_chapter_conflict", "target_chapter": 32, "severity": "high"}
        ]),
        51: _mk_review_data(checker_results={
            "continuity-checker": {"violations": [
                {"type": "timeline_mismatch", "target_chapter": 10, "severity": "medium"}
            ]}
        }),
        52: _mk_review_data(),  # 无违规
    }
    drifts = detect_drifts(tmp_path, (50, 52), records=records)
    assert len(drifts) == 2
    by_ch = {d.chapter_detected: d for d in drifts}
    assert by_ch[50].target_chapter == 32
    assert by_ch[51].target_chapter == 10


def test_detect_drifts_empty_when_no_db(tmp_path: Path):
    # 无 index.db 且无 records → 空列表，不抛异常
    drifts = detect_drifts(tmp_path, range(1, 5))
    assert drifts == []


def test_detect_drifts_reads_index_db(tmp_path: Path):
    ink_dir = tmp_path / ".ink"
    ink_dir.mkdir()
    db_path = ink_dir / "index.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE review_metrics (
            start_chapter INTEGER NOT NULL,
            end_chapter INTEGER NOT NULL,
            overall_score REAL DEFAULT 0,
            dimension_scores TEXT,
            severity_counts TEXT,
            critical_issues TEXT,
            report_file TEXT,
            notes TEXT,
            review_payload_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (start_chapter, end_chapter)
        )
        """
    )
    critical = json.dumps([
        {"type": "cross_chapter_conflict", "target_chapter": 12, "severity": "high",
         "rule": "power.level", "suggested_fix": "补伏笔"}
    ])
    conn.execute(
        "INSERT INTO review_metrics(start_chapter, end_chapter, critical_issues) VALUES (?, ?, ?)",
        (50, 50, critical),
    )
    conn.commit()
    conn.close()

    drifts = detect_drifts(tmp_path, (50, 50))
    assert len(drifts) == 1
    assert drifts[0].target_chapter == 12
    assert drifts[0].chapter_detected == 50
    assert drifts[0].severity == "high"


def test_detect_drifts_accepts_iterable_range(tmp_path: Path):
    records = {
        3: _mk_review_data(critical_issues=[
            {"type": "cross_chapter_conflict", "target_chapter": 1, "severity": "low"}
        ])
    }
    drifts = detect_drifts(tmp_path, [3, 4, 5], records=records)
    assert len(drifts) == 1
    assert drifts[0].chapter_detected == 3
