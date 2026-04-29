"""Review report JSON / DB consistency helpers (US-024).

v16 Health Audit US-024 adds a single source of truth for
``.ink/reports/review_*.json`` files.  The canonical store is
``index.db.review_metrics``; JSON files are derived artefacts used by
legacy tooling (``scripts/verify_optimization_quality.py``,
``scripts/step3_harness_gate.py`` fallback path, etc.).

Each generated JSON file carries a top-level ``generated_from`` field so
downstream readers can detect stale/hand-edited files and trigger a
re-generation from the DB (see ``ensure_review_json_matches_db``).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

GENERATED_FROM_TAG = "index.db.review_metrics"
"""Sentinel value for JSON files auto-generated from the DB."""


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    data: Dict[str, Any] = dict(row)
    for key in ("dimension_scores", "severity_counts", "critical_issues", "review_payload_json"):
        raw = data.get(key)
        if isinstance(raw, str) and raw:
            try:
                data[key] = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("review_metrics: failed to parse %s JSON for %s", key, data.get("end_chapter"))
    return data


def load_db_rows(db_path: Path) -> List[Dict[str, Any]]:
    """Return every row from ``review_metrics`` as a list of dicts.

    If the DB (or the table) does not exist yet, returns an empty list so
    callers can treat it as "no source of truth yet".
    """
    if not db_path.exists():
        return []
    try:
        with closing(sqlite3.connect(str(db_path))) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='review_metrics'"
            )
            if cursor.fetchone() is None:
                return []
            cursor.execute(
                """
                SELECT start_chapter, end_chapter, overall_score, dimension_scores,
                       severity_counts, critical_issues, report_file, notes,
                       review_payload_json
                FROM review_metrics
                ORDER BY end_chapter ASC, start_chapter ASC
                """
            )
            return [_row_to_dict(row) for row in cursor.fetchall()]
    except sqlite3.DatabaseError as exc:
        logger.warning("review_metrics: DB read failed (%s); treating as empty", exc)
        return []


def build_report_payload(db_row: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a DB row into the JSON payload written to ``.ink/reports/``.

    The top-level ``generated_from`` field is the US-024 invariant: any
    review JSON that lacks it (or carries a different value) must be
    treated as drift and regenerated.
    """
    payload: Dict[str, Any] = {
        "generated_from": GENERATED_FROM_TAG,
        "start_chapter": db_row.get("start_chapter"),
        "end_chapter": db_row.get("end_chapter"),
        "overall_score": db_row.get("overall_score", 0),
        "dimension_scores": db_row.get("dimension_scores") or {},
        "severity_counts": db_row.get("severity_counts") or {},
        "critical_issues": db_row.get("critical_issues") or [],
        "report_file": db_row.get("report_file", ""),
        "notes": db_row.get("notes", ""),
    }
    # Optional extended payload (checker_results, entity_count, ...).
    extra = db_row.get("review_payload_json") or {}
    if isinstance(extra, dict):
        for key, value in extra.items():
            payload.setdefault(key, value)
    return payload


def _json_report_path(reports_dir: Path, row: Dict[str, Any]) -> Path:
    end_ch = int(row.get("end_chapter") or 0)
    return reports_dir / f"review_ch{end_ch:04d}.json"


def write_report_json(reports_dir: Path, row: Dict[str, Any]) -> Path:
    """Render a single DB row into its ``review_ch{N}.json`` artefact."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = _json_report_path(reports_dir, row)
    payload = build_report_payload(row)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _payloads_match(db_payload: Dict[str, Any], json_payload: Dict[str, Any]) -> bool:
    """Compare the DB-derived payload against an on-disk JSON file.

    Only the invariants written by :func:`build_report_payload` are
    compared; extra keys present in the JSON (e.g. human annotations) are
    tolerated **as long as** ``generated_from`` matches.
    """
    if json_payload.get("generated_from") != GENERATED_FROM_TAG:
        return False
    for key, value in db_payload.items():
        if json_payload.get(key) != value:
            return False
    return True


def ensure_review_json_matches_db(
    project_root: Path, *, reports_subdir: str = ".ink/reports"
) -> Dict[str, List[str]]:
    """Regenerate any ``review_*.json`` whose content drifts from the DB.

    Returns a dict summarising the work:

    * ``rewritten`` – files overwritten because their payload differed
      from the DB (or lacked the ``generated_from`` marker).
    * ``created`` – files freshly written for DB rows that had no JSON.
    * ``unchanged`` – files that already matched the DB snapshot.

    ``DB is authoritative``: if the DB has no matching row for a JSON
    file on disk, the JSON is left untouched (it may be a historical
    artefact from before the migration).
    """
    db_path = project_root / ".ink" / "index.db"
    reports_dir = project_root / reports_subdir

    summary: Dict[str, List[str]] = {"rewritten": [], "created": [], "unchanged": []}

    rows = load_db_rows(db_path)
    if not rows:
        return summary

    for row in rows:
        path = _json_report_path(reports_dir, row)
        db_payload = build_report_payload(row)
        existing = _read_json(path) if path.exists() else None
        if existing is None:
            write_report_json(reports_dir, row)
            summary["created"].append(str(path))
            logger.info("review json created from DB: %s", path.name)
            continue
        if _payloads_match(db_payload, existing):
            summary["unchanged"].append(str(path))
            continue
        write_report_json(reports_dir, row)
        summary["rewritten"].append(str(path))
        logger.warning(
            "review json drift detected for %s; regenerated from index.db.review_metrics",
            path.name,
        )
    return summary


__all__ = [
    "GENERATED_FROM_TAG",
    "build_report_payload",
    "ensure_review_json_matches_db",
    "load_db_rows",
    "write_report_json",
]
