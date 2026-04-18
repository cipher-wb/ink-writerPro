"""Unit tests for ink_writer.quality_metrics collectors (US-018).

Every Q_n is exercised against a hand-crafted minimal SQLite schema so the
suite stays hermetic (no fixture DB file needed; we build it in tmp_path).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Tuple

import pytest

from ink_writer.quality_metrics import QualityReport, collect_quality_metrics
from ink_writer.quality_metrics.collectors import (
    q1_progression_conflicts,
    q2_foreshadow_ratio,
    q3_propagation_debt,
    q4_review_passed_ratio,
    q5_consistency_critical,
    q6_continuity_critical,
    q7_candidate_facts_unresolved,
    q8_state_index_drift,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".ink").mkdir(parents=True, exist_ok=True)
    return root


def _open_db(root: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(root / ".ink" / "index.db"))
    conn.row_factory = sqlite3.Row
    return conn


def _seed_character_progressions(
    conn: sqlite3.Connection, rows: Iterable[Tuple[str, int, str, str, str]]
) -> None:
    conn.execute(
        """
        CREATE TABLE character_progressions (
            character_id TEXT NOT NULL,
            chapter_no   INTEGER NOT NULL,
            dimension    TEXT NOT NULL,
            from_value   TEXT,
            to_value     TEXT,
            cause        TEXT,
            PRIMARY KEY (character_id, chapter_no, dimension)
        )
        """
    )
    conn.executemany(
        "INSERT INTO character_progressions(character_id, chapter_no, dimension, from_value, to_value) "
        "VALUES (?,?,?,?,?)",
        rows,
    )
    conn.commit()


def _seed_plot_threads(
    conn: sqlite3.Connection, rows: Iterable[Tuple[str, int, str, int]]
) -> None:
    conn.execute(
        """
        CREATE TABLE plot_thread_registry (
            thread_id TEXT PRIMARY KEY,
            status    TEXT,
            planted_chapter INTEGER,
            resolved_chapter INTEGER
        )
        """
    )
    conn.executemany(
        "INSERT INTO plot_thread_registry(thread_id, planted_chapter, status, resolved_chapter) "
        "VALUES (?,?,?,?)",
        rows,
    )
    conn.commit()


def _seed_review_metrics(
    conn: sqlite3.Connection,
    rows: Iterable[Tuple[int, int, float, str, str]],
) -> None:
    conn.execute(
        """
        CREATE TABLE review_metrics (
            start_chapter INTEGER NOT NULL,
            end_chapter   INTEGER NOT NULL,
            overall_score REAL,
            critical_issues TEXT,
            review_payload_json TEXT,
            PRIMARY KEY (start_chapter, end_chapter)
        )
        """
    )
    conn.executemany(
        "INSERT INTO review_metrics(start_chapter, end_chapter, overall_score, "
        "critical_issues, review_payload_json) VALUES (?,?,?,?,?)",
        rows,
    )
    conn.commit()


def _seed_candidate_facts(
    conn: sqlite3.Connection, rows: Iterable[Tuple[int, str, str]]
) -> None:
    conn.execute(
        """
        CREATE TABLE candidate_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter INTEGER NOT NULL,
            fact TEXT NOT NULL,
            status TEXT DEFAULT 'candidate'
        )
        """
    )
    conn.executemany(
        "INSERT INTO candidate_facts(chapter, fact, status) VALUES (?,?,?)", rows
    )
    conn.commit()


def _seed_state_kv(conn: sqlite3.Connection, kv: dict) -> None:
    conn.execute(
        "CREATE TABLE state_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.executemany(
        "INSERT INTO state_kv(key, value) VALUES (?,?)",
        [(k, json.dumps(v, ensure_ascii=False)) for k, v in kv.items()],
    )
    conn.commit()


def _seed_chapters(conn: sqlite3.Connection, chapters: Iterable[int]) -> None:
    conn.execute("CREATE TABLE chapters (chapter INTEGER PRIMARY KEY)")
    conn.executemany(
        "INSERT INTO chapters(chapter) VALUES (?)", [(c,) for c in chapters]
    )
    conn.commit()


def _seed_entities(conn: sqlite3.Connection, count: int) -> None:
    conn.execute("CREATE TABLE entities (id TEXT PRIMARY KEY)")
    conn.executemany(
        "INSERT INTO entities(id) VALUES (?)", [(f"e{i}",) for i in range(count)]
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Q1 — progression conflicts
# ---------------------------------------------------------------------------


def test_q1_detects_value_jump(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    _seed_character_progressions(
        conn,
        [
            # clean chain: 0→1→2 (no conflict)
            ("lin", 1, "cultivation", "0", "1"),
            ("lin", 2, "cultivation", "1", "2"),
            # jump: ch3 from_value '9' but prev to_value '2' ⇒ 1 conflict
            ("lin", 3, "cultivation", "9", "10"),
        ],
    )
    conn.close()
    conn = _open_db(root)
    assert q1_progression_conflicts(conn) == 1
    conn.close()


def test_q1_respects_chapter_range(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    _seed_character_progressions(
        conn,
        [
            ("lin", 1, "mood", "calm", "angry"),
            ("lin", 2, "mood", "angry", "calm"),
            ("lin", 5, "mood", "surprise", "calm"),  # conflict vs ch2
        ],
    )
    conn.close()
    conn = _open_db(root)
    # Restricting to [1,2] hides the ch5 jump
    assert q1_progression_conflicts(conn, (1, 2)) == 0
    # Full range catches the jump from ch2 (to=calm) → ch5 (from=surprise)
    assert q1_progression_conflicts(conn, (1, 5)) == 1
    conn.close()


def test_q1_missing_table_returns_none(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    # empty DB, no tables
    assert q1_progression_conflicts(conn) is None
    conn.close()


# ---------------------------------------------------------------------------
# Q2 — foreshadow ratio
# ---------------------------------------------------------------------------


def test_q2_ratio_half(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    _seed_plot_threads(
        conn,
        [
            ("t1", 1, "resolved", 5),
            ("t2", 2, "resolved", 8),
            ("t3", 3, "active", None),
            ("t4", 4, "active", None),
        ],
    )
    conn.close()
    conn = _open_db(root)
    assert q2_foreshadow_ratio(conn) == 0.5
    conn.close()


def test_q2_range_scoping(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    _seed_plot_threads(
        conn,
        [
            ("t1", 1, "resolved", 3),
            ("t2", 50, "active", None),  # outside tight range
        ],
    )
    conn.close()
    conn = _open_db(root)
    # range (1,10): planted=1, resolved=1 ⇒ 1.0
    assert q2_foreshadow_ratio(conn, (1, 10)) == 1.0
    conn.close()


def test_q2_missing_table(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    assert q2_foreshadow_ratio(conn) is None
    conn.close()


# ---------------------------------------------------------------------------
# Q3 — propagation debt
# ---------------------------------------------------------------------------


def test_q3_counts_open_items(tmp_path):
    root = _make_project(tmp_path)
    payload = {
        "items": [
            {"debt_id": "d1", "chapter_detected": 5, "status": "open"},
            {"debt_id": "d2", "chapter_detected": 6, "status": "resolved"},
            {"debt_id": "d3", "chapter_detected": 7, "status": "open"},
        ]
    }
    (root / ".ink" / "propagation_debt.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    assert q3_propagation_debt(root) == 2
    # range scoping
    assert q3_propagation_debt(root, (5, 5)) == 1


def test_q3_missing_file(tmp_path):
    root = _make_project(tmp_path)
    assert q3_propagation_debt(root) is None


def test_q3_empty_file(tmp_path):
    root = _make_project(tmp_path)
    (root / ".ink" / "propagation_debt.json").write_text("", encoding="utf-8")
    assert q3_propagation_debt(root) == 0


# ---------------------------------------------------------------------------
# Q4 — review metrics passed ratio
# ---------------------------------------------------------------------------


def test_q4_passed_ratio(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    _seed_review_metrics(
        conn,
        [
            (1, 10, 0.9, "[]", "{}"),  # pass
            (11, 20, 0.7, "[]", "{}"),  # score too low
            (21, 30, 0.95, json.dumps([{"severity": "critical"}]), "{}"),  # critical
            (31, 40, 0.85, "[]", "{}"),  # pass
        ],
    )
    conn.close()
    conn = _open_db(root)
    assert q4_review_passed_ratio(conn) == 0.5
    conn.close()


def test_q4_empty(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    _seed_review_metrics(conn, [])
    conn.close()
    conn = _open_db(root)
    assert q4_review_passed_ratio(conn) == 0.0
    conn.close()


def test_q4_missing_table(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    assert q4_review_passed_ratio(conn) is None
    conn.close()


# ---------------------------------------------------------------------------
# Q5 / Q6 — checker critical totals
# ---------------------------------------------------------------------------


def test_q5_q6_counts_from_critical_issues_and_payload(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    critical = json.dumps(
        [
            {"source": "consistency-checker", "severity": "critical"},
            {"source": "continuity-checker", "severity": "critical"},
            {"source": "consistency-checker", "severity": "high"},  # not critical
        ]
    )
    payload = json.dumps(
        {
            "checker_results": {
                "consistency-checker": {
                    "violations": [
                        {"severity": "critical"},
                        {"severity": "medium"},
                    ]
                },
                "continuity-checker": {"violations": []},
            }
        }
    )
    _seed_review_metrics(conn, [(1, 10, 0.8, critical, payload)])
    conn.close()
    conn = _open_db(root)
    assert q5_consistency_critical(conn) == 2  # 1 from critical_issues + 1 from payload
    assert q6_continuity_critical(conn) == 1
    conn.close()


def test_q5_q6_missing_table(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    assert q5_consistency_critical(conn) is None
    assert q6_continuity_critical(conn) is None
    conn.close()


# ---------------------------------------------------------------------------
# Q7 — candidate facts unresolved
# ---------------------------------------------------------------------------


def test_q7_counts_unresolved(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    _seed_candidate_facts(
        conn,
        [
            (1, "x", "candidate"),
            (2, "y", "resolved"),
            (3, "z", "candidate"),
            (50, "w", "candidate"),
        ],
    )
    conn.close()
    conn = _open_db(root)
    assert q7_candidate_facts_unresolved(conn) == 3
    assert q7_candidate_facts_unresolved(conn, (1, 10)) == 2
    conn.close()


def test_q7_missing_table(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    assert q7_candidate_facts_unresolved(conn) is None
    conn.close()


# ---------------------------------------------------------------------------
# Q8 — state_kv vs index.db drift
# ---------------------------------------------------------------------------


def test_q8_no_drift_when_consistent(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    _seed_chapters(conn, [1, 2, 3])
    _seed_entities(conn, 5)
    _seed_plot_threads(
        conn,
        [
            ("t1", 1, "active", None),
            ("t2", 2, "active", None),
        ],
    )
    _seed_state_kv(
        conn,
        {
            "project_progress": {"current_chapter": 3},
            "entity_count": 5,
            "foreshadow_active": 2,
        },
    )
    conn.close()
    conn = _open_db(root)
    assert q8_state_index_drift(conn) == 0
    conn.close()


def test_q8_detects_three_drifts(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    _seed_chapters(conn, [1, 2, 3])
    _seed_entities(conn, 5)
    _seed_plot_threads(conn, [("t1", 1, "active", None)])
    _seed_state_kv(
        conn,
        {
            "project_progress": {"current_chapter": 10},  # !=3
            "entity_count": 99,  # !=5
            "foreshadow_active": 7,  # !=1
        },
    )
    conn.close()
    conn = _open_db(root)
    assert q8_state_index_drift(conn) == 3
    conn.close()


def test_q8_missing_state_kv(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    assert q8_state_index_drift(conn) is None
    conn.close()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def test_collect_quality_metrics_end_to_end(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    _seed_character_progressions(
        conn, [("lin", 1, "mood", "a", "b"), ("lin", 2, "mood", "x", "y")]
    )
    _seed_plot_threads(
        conn,
        [("t1", 1, "resolved", 3), ("t2", 2, "active", None)],
    )
    _seed_review_metrics(conn, [(1, 10, 0.9, "[]", "{}")])
    _seed_candidate_facts(conn, [(1, "x", "candidate")])
    _seed_chapters(conn, [1, 2, 3])
    _seed_entities(conn, 2)
    _seed_state_kv(
        conn,
        {
            "project_progress": {"current_chapter": 3},
            "entity_count": 2,
            "foreshadow_active": 1,
        },
    )
    conn.close()
    (root / ".ink" / "propagation_debt.json").write_text(
        json.dumps({"items": [{"debt_id": "d1", "chapter_detected": 1, "status": "open"}]}),
        encoding="utf-8",
    )

    report = collect_quality_metrics(root)

    assert isinstance(report, QualityReport)
    assert report.q1_progression_conflicts == 1
    assert report.q2_foreshadow_plant_resolve_ratio == 0.5
    assert report.q3_propagation_debt_open == 1
    assert report.q4_review_passed_ratio == 1.0
    assert report.q5_consistency_critical_total == 0
    assert report.q6_continuity_critical_total == 0
    assert report.q7_candidate_facts_unresolved == 1
    assert report.q8_state_index_drift_count == 0
    data = report.to_dict()
    assert data["project_root"] == str(root)
    assert data["q4_review_passed_ratio"] == 1.0


def test_collect_quality_metrics_missing_db(tmp_path):
    root = _make_project(tmp_path)
    # no index.db; propagation_debt also absent
    report = collect_quality_metrics(root)
    assert report.q1_progression_conflicts is None
    assert report.q3_propagation_debt_open is None


def test_collect_quality_metrics_with_chapter_range(tmp_path):
    root = _make_project(tmp_path)
    conn = _open_db(root)
    _seed_candidate_facts(
        conn,
        [
            (1, "a", "candidate"),
            (100, "b", "candidate"),
        ],
    )
    conn.close()
    report = collect_quality_metrics(root, chapter_range=(1, 10))
    assert report.q7_candidate_facts_unresolved == 1
    assert report.chapter_range == (1, 10)
    assert report.to_dict()["chapter_range"] == [1, 10]
