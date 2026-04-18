"""Q1-Q8 quality metric collectors (US-018).

All metrics are computed by direct SQL queries against the project's
``.ink/index.db`` (SQLite). Zero LLM calls, zero external API.

Each Q_n function is independent — if a required table is missing (legacy
project or partial schema), the collector returns ``None`` and logs a warning,
so the overall report remains usable with ``null`` entries.

Public API
==========

- :class:`QualityReport`          dataclass with 8 metric fields + helpers.
- :func:`collect_quality_metrics` orchestrator; accepts ``project_root`` and
  an optional ``chapter_range = (start, end)`` to scope chapter-keyed tables.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

logger = logging.getLogger(__name__)

ChapterRange = Optional[Tuple[int, int]]


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class QualityReport:
    """8-metric quality snapshot for a chapter range.

    Any metric can be ``None`` when the underlying table is unavailable
    (legacy projects / partial migrations). Callers should treat ``None`` as
    "不可观测" rather than zero.
    """

    q1_progression_conflicts: Optional[int] = None
    q2_foreshadow_plant_resolve_ratio: Optional[float] = None
    q3_propagation_debt_open: Optional[int] = None
    q4_review_passed_ratio: Optional[float] = None
    q5_consistency_critical_total: Optional[int] = None
    q6_continuity_critical_total: Optional[int] = None
    q7_candidate_facts_unresolved: Optional[int] = None
    q8_state_index_drift_count: Optional[int] = None

    # metadata
    project_root: str = ""
    chapter_range: Optional[Tuple[int, int]] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # normalise tuple → list for JSON friendliness
        if self.chapter_range is not None:
            data["chapter_range"] = list(self.chapter_range)
        return data


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _db_path(project_root: Path) -> Path:
    return project_root / ".ink" / "index.db"


def _connect(project_root: Path) -> Optional[sqlite3.Connection]:
    path = _db_path(project_root)
    if not path.exists():
        logger.warning("quality_metrics: index.db not found at %s", path)
        return None
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        logger.warning("quality_metrics: failed to open %s: %s", path, exc)
        return None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    try:
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (name,),
        )
        return cur.fetchone() is not None
    except sqlite3.Error:
        return False


def _range_clause(range_: ChapterRange, column: str) -> Tuple[str, Tuple[int, ...]]:
    """Return ``(sql_fragment, params)`` for optional chapter scoping."""
    if range_ is None:
        return "", ()
    start, end = range_
    return f"AND {column} BETWEEN ? AND ?", (int(start), int(end))


# ---------------------------------------------------------------------------
# Q1 — Progression cross-chapter conflicts
# ---------------------------------------------------------------------------


def q1_progression_conflicts(
    conn: sqlite3.Connection, chapter_range: ChapterRange = None
) -> Optional[int]:
    """Count (character_id, dimension) pairs whose value "jumps" inconsistently
    across chapters.

    A conflict = two rows for the same (character_id, dimension) where the
    later row's ``from_value`` does **not** equal the earlier row's
    ``to_value``. This catches progression DB entries that were written without
    respecting the previous slice (ghost rewrites, back-fills).
    """
    if not _table_exists(conn, "character_progressions"):
        logger.warning("quality_metrics: character_progressions table missing, Q1 -> None")
        return None
    range_sql, range_params = _range_clause(chapter_range, "chapter_no")
    sql = f"""
        SELECT character_id, dimension, chapter_no, from_value, to_value
        FROM character_progressions
        WHERE 1=1 {range_sql}
        ORDER BY character_id, dimension, chapter_no
    """
    try:
        rows = conn.execute(sql, range_params).fetchall()
    except sqlite3.Error as exc:
        logger.warning("quality_metrics: Q1 query failed: %s", exc)
        return None

    conflicts = 0
    prev_key: Optional[Tuple[str, str]] = None
    prev_to: Optional[str] = None
    for row in rows:
        key = (row["character_id"], row["dimension"])
        from_v = row["from_value"]
        to_v = row["to_value"]
        if prev_key == key and prev_to is not None and from_v is not None:
            # compare as strings; None on either side ⇒ skip (benign initial)
            if str(from_v) != str(prev_to):
                conflicts += 1
        prev_key = key
        prev_to = to_v
    return conflicts


# ---------------------------------------------------------------------------
# Q2 — Foreshadow plant / resolve ratio
# ---------------------------------------------------------------------------


def q2_foreshadow_ratio(
    conn: sqlite3.Connection, chapter_range: ChapterRange = None
) -> Optional[float]:
    """Return ``resolved / planted`` in the chapter range (1.0 == perfect closure).

    Uses ``plot_thread_registry``:
        planted  := rows whose ``planted_chapter`` is inside the range.
        resolved := planted rows whose ``status='resolved'``
                    AND ``resolved_chapter`` is inside the range.
    """
    if not _table_exists(conn, "plot_thread_registry"):
        logger.warning(
            "quality_metrics: plot_thread_registry table missing, Q2 -> None"
        )
        return None

    plant_range, plant_params = _range_clause(chapter_range, "planted_chapter")
    try:
        planted = conn.execute(
            f"SELECT COUNT(*) FROM plot_thread_registry WHERE planted_chapter > 0 {plant_range}",
            plant_params,
        ).fetchone()[0]
    except sqlite3.Error as exc:
        logger.warning("quality_metrics: Q2 planted query failed: %s", exc)
        return None

    resolve_range, resolve_params = _range_clause(chapter_range, "resolved_chapter")
    try:
        resolved = conn.execute(
            f"""SELECT COUNT(*) FROM plot_thread_registry
                WHERE status = 'resolved'
                  AND resolved_chapter IS NOT NULL
                  {resolve_range}""",
            resolve_params,
        ).fetchone()[0]
    except sqlite3.Error as exc:
        logger.warning("quality_metrics: Q2 resolved query failed: %s", exc)
        return None

    if planted == 0:
        return 0.0 if resolved == 0 else float(resolved)  # no denominator → surface raw resolved
    return round(resolved / planted, 4)


# ---------------------------------------------------------------------------
# Q3 — Propagation debt outstanding
# ---------------------------------------------------------------------------


def q3_propagation_debt(
    project_root: Path, chapter_range: ChapterRange = None
) -> Optional[int]:
    """Count open PropagationDebtItems in ``.ink/propagation_debt.json``.

    The store is JSON (not SQL), but reading it is cheap and still zero-LLM.
    Scoped by ``chapter_detected`` when ``chapter_range`` is supplied.
    """
    path = project_root / ".ink" / "propagation_debt.json"
    if not path.exists():
        logger.warning(
            "quality_metrics: propagation_debt.json missing, Q3 -> None"
        )
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return 0
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("quality_metrics: Q3 read failed: %s", exc)
        return None

    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return 0
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("status") not in (None, "open"):
            continue
        if chapter_range is not None:
            ch = item.get("chapter_detected")
            if not isinstance(ch, int):
                continue
            start, end = chapter_range
            if not (start <= ch <= end):
                continue
        count += 1
    return count


# ---------------------------------------------------------------------------
# Q4 — Review metrics passed ratio
# ---------------------------------------------------------------------------


def q4_review_passed_ratio(
    conn: sqlite3.Connection, chapter_range: ChapterRange = None
) -> Optional[float]:
    """Fraction of ``review_metrics`` rows with ``overall_score >= 0.8``
    and zero critical issues.

    Range semantics: a review row ``(start_chapter, end_chapter)`` counts when
    it overlaps the requested range.
    """
    if not _table_exists(conn, "review_metrics"):
        logger.warning("quality_metrics: review_metrics table missing, Q4 -> None")
        return None

    range_sql = ""
    range_params: Tuple[int, ...] = ()
    if chapter_range is not None:
        start, end = chapter_range
        range_sql = "WHERE start_chapter <= ? AND end_chapter >= ?"
        range_params = (int(end), int(start))

    try:
        rows = conn.execute(
            f"SELECT overall_score, critical_issues FROM review_metrics {range_sql}",
            range_params,
        ).fetchall()
    except sqlite3.Error as exc:
        logger.warning("quality_metrics: Q4 query failed: %s", exc)
        return None

    if not rows:
        return 0.0
    passed = 0
    for row in rows:
        score = row["overall_score"] or 0.0
        crit_raw = row["critical_issues"]
        critical_count = _count_jsonish(crit_raw)
        if score >= 0.8 and critical_count == 0:
            passed += 1
    return round(passed / len(rows), 4)


def _count_jsonish(raw: Any) -> int:
    if raw is None:
        return 0
    if isinstance(raw, (list, tuple)):
        return len(raw)
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return 0
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return 0
        return len(parsed) if isinstance(parsed, list) else 0
    return 0


# ---------------------------------------------------------------------------
# Q5 / Q6 — consistency / continuity critical totals
# ---------------------------------------------------------------------------


def _critical_total_for_checker(
    conn: sqlite3.Connection, checker_name: str, chapter_range: ChapterRange
) -> Optional[int]:
    if not _table_exists(conn, "review_metrics"):
        logger.warning(
            "quality_metrics: review_metrics table missing, %s critical -> None",
            checker_name,
        )
        return None
    range_sql = ""
    range_params: Tuple[int, ...] = ()
    if chapter_range is not None:
        start, end = chapter_range
        range_sql = "WHERE start_chapter <= ? AND end_chapter >= ?"
        range_params = (int(end), int(start))

    try:
        rows = conn.execute(
            f"SELECT critical_issues, review_payload_json FROM review_metrics {range_sql}",
            range_params,
        ).fetchall()
    except sqlite3.Error as exc:
        logger.warning("quality_metrics: %s query failed: %s", checker_name, exc)
        return None

    total = 0
    for row in rows:
        total += _count_checker_critical(row["critical_issues"], checker_name)
        payload = _safe_json(row["review_payload_json"])
        if isinstance(payload, dict):
            checker_results = payload.get("checker_results") or {}
            per_checker = checker_results.get(checker_name) if isinstance(checker_results, dict) else None
            if isinstance(per_checker, dict):
                violations = per_checker.get("violations") or per_checker.get("issues") or []
                if isinstance(violations, list):
                    for viol in violations:
                        if isinstance(viol, dict) and str(viol.get("severity", "")).lower() == "critical":
                            total += 1
    return total


def _safe_json(raw: Any) -> Any:
    if raw is None or isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _count_checker_critical(raw: Any, checker_name: str) -> int:
    data = _safe_json(raw)
    if not isinstance(data, list):
        return 0
    count = 0
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("severity", "")).lower() != "critical":
            continue
        src = entry.get("source") or entry.get("checker") or entry.get("category") or ""
        if checker_name in str(src):
            count += 1
    return count


def q5_consistency_critical(
    conn: sqlite3.Connection, chapter_range: ChapterRange = None
) -> Optional[int]:
    return _critical_total_for_checker(conn, "consistency-checker", chapter_range)


def q6_continuity_critical(
    conn: sqlite3.Connection, chapter_range: ChapterRange = None
) -> Optional[int]:
    return _critical_total_for_checker(conn, "continuity-checker", chapter_range)


# ---------------------------------------------------------------------------
# Q7 — Candidate facts unresolved
# ---------------------------------------------------------------------------


def q7_candidate_facts_unresolved(
    conn: sqlite3.Connection, chapter_range: ChapterRange = None
) -> Optional[int]:
    if not _table_exists(conn, "candidate_facts"):
        logger.warning("quality_metrics: candidate_facts table missing, Q7 -> None")
        return None
    range_sql, range_params = _range_clause(chapter_range, "chapter")
    try:
        row = conn.execute(
            f"""SELECT COUNT(*) FROM candidate_facts
                WHERE status = 'candidate' {range_sql}""",
            range_params,
        ).fetchone()
        return int(row[0])
    except sqlite3.Error as exc:
        logger.warning("quality_metrics: Q7 query failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Q8 — state_kv vs index.db drift
# ---------------------------------------------------------------------------


def q8_state_index_drift(conn: sqlite3.Connection) -> Optional[int]:
    """Count drift incidents between ``state_kv`` and index.db derived tables.

    Current checks (each contributes at most 1 to the count):

    1. ``state_kv["project_progress"].current_chapter`` vs
       ``MAX(chapter) FROM chapters`` — mismatch ⇒ +1.
    2. ``state_kv["entity_count"]`` (if present) vs ``COUNT(*) FROM entities``.
    3. ``state_kv["foreshadow_active"]`` vs
       ``COUNT(*) FROM plot_thread_registry WHERE status='active'``.

    Missing ``state_kv`` ⇒ Q8 = None.
    """
    if not _table_exists(conn, "state_kv"):
        logger.warning("quality_metrics: state_kv table missing, Q8 -> None")
        return None

    kv: Dict[str, Any] = {}
    try:
        for row in conn.execute("SELECT key, value FROM state_kv").fetchall():
            kv[row["key"]] = _safe_json(row["value"])
    except sqlite3.Error as exc:
        logger.warning("quality_metrics: Q8 state_kv read failed: %s", exc)
        return None

    drift = 0

    # Check 1: current_chapter
    progress = kv.get("project_progress")
    kv_chapter: Optional[int] = None
    if isinstance(progress, dict):
        raw = progress.get("current_chapter")
        if isinstance(raw, int):
            kv_chapter = raw
    if kv_chapter is not None and _table_exists(conn, "chapters"):
        try:
            max_ch = conn.execute("SELECT MAX(chapter) FROM chapters").fetchone()[0] or 0
        except sqlite3.Error:
            max_ch = None
        if max_ch is not None and int(max_ch) != int(kv_chapter):
            drift += 1

    # Check 2: entity_count
    kv_entity = kv.get("entity_count")
    if isinstance(kv_entity, int) and _table_exists(conn, "entities"):
        try:
            actual = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] or 0
        except sqlite3.Error:
            actual = None
        if actual is not None and int(actual) != int(kv_entity):
            drift += 1

    # Check 3: foreshadow_active
    kv_active = kv.get("foreshadow_active")
    if isinstance(kv_active, int) and _table_exists(conn, "plot_thread_registry"):
        try:
            actual = conn.execute(
                "SELECT COUNT(*) FROM plot_thread_registry WHERE status = 'active'"
            ).fetchone()[0] or 0
        except sqlite3.Error:
            actual = None
        if actual is not None and int(actual) != int(kv_active):
            drift += 1

    return drift


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def collect_quality_metrics(
    project_root: Union[str, Path],
    chapter_range: ChapterRange = None,
) -> QualityReport:
    """Run all 8 collectors and return a :class:`QualityReport`.

    Failures in individual collectors leave the corresponding field as ``None``.
    An unreadable ``index.db`` still yields a populated :class:`QualityReport`
    (Q3 reads JSON, others become ``None``).
    """
    root = Path(project_root)
    report = QualityReport(
        project_root=str(root),
        chapter_range=chapter_range,
    )

    # Q3 reads JSON — independent of DB
    try:
        report.q3_propagation_debt_open = q3_propagation_debt(root, chapter_range)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("quality_metrics: Q3 raised: %s", exc)

    conn = _connect(root)
    if conn is None:
        return report

    try:
        _fill_db_metrics(report, conn, chapter_range)
    finally:
        conn.close()
    return report


def _fill_db_metrics(
    report: QualityReport, conn: sqlite3.Connection, chapter_range: ChapterRange
) -> None:
    collectors = (
        ("q1_progression_conflicts", lambda: q1_progression_conflicts(conn, chapter_range)),
        ("q2_foreshadow_plant_resolve_ratio", lambda: q2_foreshadow_ratio(conn, chapter_range)),
        ("q4_review_passed_ratio", lambda: q4_review_passed_ratio(conn, chapter_range)),
        ("q5_consistency_critical_total", lambda: q5_consistency_critical(conn, chapter_range)),
        ("q6_continuity_critical_total", lambda: q6_continuity_critical(conn, chapter_range)),
        ("q7_candidate_facts_unresolved", lambda: q7_candidate_facts_unresolved(conn, chapter_range)),
        ("q8_state_index_drift_count", lambda: q8_state_index_drift(conn)),
    )
    for field_name, fn in collectors:
        try:
            setattr(report, field_name, fn())
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("quality_metrics: %s raised: %s", field_name, exc)
            setattr(report, field_name, None)
