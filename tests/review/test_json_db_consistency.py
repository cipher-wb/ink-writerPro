"""US-024: ``.ink/reports/review_*.json`` ↔ ``index.db.review_metrics`` parity.

Invariants:

* Every auto-generated JSON carries ``generated_from ==
  "index.db.review_metrics"`` at the top level.
* When the JSON drifts (missing file, wrong scores, missing marker), the
  sync helper regenerates it from the DB.
* When JSON already matches the DB, the sync helper leaves the file
  alone and reports it as ``unchanged``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ink_writer.core.index.review_report_sync import (
    GENERATED_FROM_TAG,
    build_report_payload,
    ensure_review_json_matches_db,
)


def _seed_db(db_path: Path, rows: list[dict]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE review_metrics (
                start_chapter INTEGER,
                end_chapter INTEGER,
                overall_score REAL,
                dimension_scores TEXT,
                severity_counts TEXT,
                critical_issues TEXT,
                report_file TEXT,
                notes TEXT,
                review_payload_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (start_chapter, end_chapter)
            )
            """
        )
        for row in rows:
            conn.execute(
                """
                INSERT INTO review_metrics
                (start_chapter, end_chapter, overall_score,
                 dimension_scores, severity_counts, critical_issues,
                 report_file, notes, review_payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["start_chapter"],
                    row["end_chapter"],
                    row["overall_score"],
                    json.dumps(row.get("dimension_scores", {}), ensure_ascii=False),
                    json.dumps(row.get("severity_counts", {}), ensure_ascii=False),
                    json.dumps(row.get("critical_issues", []), ensure_ascii=False),
                    row.get("report_file", ""),
                    row.get("notes", ""),
                    json.dumps(row.get("review_payload_json", {}), ensure_ascii=False),
                ),
            )
        conn.commit()


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / ".ink").mkdir()
    return tmp_path


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_report_payload_has_generated_from() -> None:
    db_row = {
        "start_chapter": 1,
        "end_chapter": 5,
        "overall_score": 87.5,
        "dimension_scores": {"plot": 90.0},
        "severity_counts": {"critical": 0},
        "critical_issues": [],
        "report_file": "reports/review_1_5.md",
        "notes": "ok",
        "review_payload_json": {"checker_results": {"x": {"overall_score": 90}}},
    }
    payload = build_report_payload(db_row)
    assert payload["generated_from"] == GENERATED_FROM_TAG
    # Extra payload keys must be merged in.
    assert "checker_results" in payload
    assert payload["overall_score"] == 87.5


def test_ensure_creates_missing_json(project_root: Path) -> None:
    _seed_db(
        project_root / ".ink" / "index.db",
        [
            {
                "start_chapter": 1,
                "end_chapter": 5,
                "overall_score": 88.0,
                "dimension_scores": {"plot": 90.0},
                "severity_counts": {"critical": 0},
            }
        ],
    )

    summary = ensure_review_json_matches_db(project_root)

    json_path = project_root / ".ink" / "reports" / "review_ch0005.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["generated_from"] == GENERATED_FROM_TAG
    assert data["overall_score"] == 88.0
    assert str(json_path) in summary["created"]
    assert summary["rewritten"] == []


def test_ensure_regenerates_drifted_json(project_root: Path) -> None:
    _seed_db(
        project_root / ".ink" / "index.db",
        [
            {
                "start_chapter": 1,
                "end_chapter": 5,
                "overall_score": 92.0,
                "dimension_scores": {"plot": 95.0},
                "severity_counts": {"critical": 0},
            }
        ],
    )
    drifted_path = project_root / ".ink" / "reports" / "review_ch0005.json"
    _write(
        drifted_path,
        {
            # Missing generated_from marker + wrong score → counts as drift.
            "start_chapter": 1,
            "end_chapter": 5,
            "overall_score": 50.0,
        },
    )

    summary = ensure_review_json_matches_db(project_root)

    data = json.loads(drifted_path.read_text(encoding="utf-8"))
    assert data["generated_from"] == GENERATED_FROM_TAG
    assert data["overall_score"] == 92.0  # DB wins
    assert str(drifted_path) in summary["rewritten"]


def test_ensure_is_idempotent(project_root: Path) -> None:
    _seed_db(
        project_root / ".ink" / "index.db",
        [
            {
                "start_chapter": 6,
                "end_chapter": 10,
                "overall_score": 75.0,
                "dimension_scores": {"hook": 80.0},
                "severity_counts": {"critical": 1},
                "critical_issues": ["foo"],
            }
        ],
    )

    first = ensure_review_json_matches_db(project_root)
    second = ensure_review_json_matches_db(project_root)

    assert len(first["created"]) == 1
    assert second["created"] == []
    assert second["rewritten"] == []
    assert len(second["unchanged"]) == 1


def test_ensure_noop_when_db_missing(project_root: Path) -> None:
    # No DB file at all – helper must return empty summary rather than crash.
    summary = ensure_review_json_matches_db(project_root)
    assert summary == {"rewritten": [], "created": [], "unchanged": []}
    assert not (project_root / ".ink" / "reports").exists()


def test_ensure_detects_marker_mismatch_only(project_root: Path) -> None:
    """Missing generated_from marker alone is enough to force a rewrite."""
    _seed_db(
        project_root / ".ink" / "index.db",
        [
            {
                "start_chapter": 1,
                "end_chapter": 3,
                "overall_score": 80.0,
            }
        ],
    )
    drifted_path = project_root / ".ink" / "reports" / "review_ch0003.json"
    # Same numeric payload but no generated_from → still must regen.
    _write(
        drifted_path,
        {
            "start_chapter": 1,
            "end_chapter": 3,
            "overall_score": 80.0,
            "dimension_scores": {},
            "severity_counts": {},
            "critical_issues": [],
            "report_file": "",
            "notes": "",
        },
    )

    summary = ensure_review_json_matches_db(project_root)
    assert str(drifted_path) in summary["rewritten"]
    data = json.loads(drifted_path.read_text(encoding="utf-8"))
    assert data["generated_from"] == GENERATED_FROM_TAG
