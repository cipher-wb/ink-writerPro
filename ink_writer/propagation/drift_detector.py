"""FIX-17 P4b: canon drift detector.

扫描 index.db.review_metrics（critical_issues + checker_results）识别
"下游章节发现的上游矛盾"，产出 PropagationDebtItem 列表供后续反向传播清算。

判定规则（符合 US-015 acceptance）:
1. critical_issues 中带 target_chapter < chapter_detected 或 type 归属
   {"cross_chapter_conflict", "back_propagation"} 视为 drift
2. checker_results["consistency-checker"|"continuity-checker"].violations
   中 target_chapter < chapter_detected 视为 drift

US-004：增量 debt 持久化到 ``.ink/drift_debts.db``。当
``detect_drifts(..., incremental=True)`` 时，仅扫描 ``chapter_id > last_seen_max``
的章节，已扫过的章节直接读取 cache，返回合并结果。
CLI ``python -m ink_writer.propagation.drift_detector --reset`` 清空 cache。
"""

from __future__ import annotations

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio
_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    '../../ink-writer/scripts',
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from ink_writer.propagation.models import PropagationDebtItem, Severity

_CROSS_CHAPTER_TYPES = {"cross_chapter_conflict", "back_propagation", "canon_drift"}
_DRIFT_CHECKERS = ("consistency-checker", "continuity-checker")
_CHAPTER_KEYS = ("target_chapter", "ref_chapter", "source_chapter", "chapter")

DEFAULT_MAX_CHAPTERS_PER_SCAN = 50
DEFAULT_CRITICAL_ISSUE_LIMIT = 20
DRIFT_DEBTS_DB_REL_PATH = Path(".ink") / "drift_debts.db"

_DRIFT_DEBTS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS drift_debts (
    chapter_id TEXT NOT NULL,
    debt_type TEXT NOT NULL,
    payload JSON,
    last_seen INTEGER,
    PRIMARY KEY(chapter_id, debt_type)
)
"""
_LAST_SEEN_META_KEY = "__last_seen_max__"


ChapterRange = Union[Sequence[int], Iterable[int], Tuple[int, int]]


def _normalize_range(chapter_range: ChapterRange) -> List[int]:
    if isinstance(chapter_range, tuple) and len(chapter_range) == 2 and all(
        isinstance(x, int) for x in chapter_range
    ):
        start, end = chapter_range
        return list(range(int(start), int(end) + 1))
    return [int(c) for c in chapter_range]


def _safe_json_load(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
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


def _extract_target_chapter(entry: Mapping[str, Any]) -> Optional[int]:
    for key in _CHAPTER_KEYS:
        value = entry.get(key)
        if value is None:
            continue
        try:
            ch = int(value)
        except (TypeError, ValueError):
            continue
        if ch >= 1:
            return ch
    return None


def _severity_from_entry(entry: Mapping[str, Any], default: Severity = "medium") -> Severity:
    sev = str(entry.get("severity", default)).lower()
    if sev in ("low", "medium", "high", "critical"):
        return sev  # type: ignore[return-value]
    return default


def _describe_rule(entry: Mapping[str, Any], checker: Optional[str] = None) -> str:
    # 优先级：rule > type > message > description > checker 名
    for key in ("rule", "type", "category", "code", "message", "description"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip() if checker is None else f"{checker}:{value.strip()}"
    return checker or "unknown_violation"


def _suggested_fix(entry: Mapping[str, Any]) -> str:
    for key in ("suggested_fix", "suggestion", "fix", "remediation", "action"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _drift_from_entry(
    entry: Mapping[str, Any],
    chapter_detected: int,
    idx: int,
    *,
    checker: Optional[str] = None,
) -> Optional[PropagationDebtItem]:
    if not isinstance(entry, Mapping):
        return None
    target = _extract_target_chapter(entry)
    entry_type = str(entry.get("type") or entry.get("category") or "").lower()
    qualifies_by_type = entry_type in _CROSS_CHAPTER_TYPES
    qualifies_by_chapter = target is not None and target < chapter_detected
    if not (qualifies_by_chapter or qualifies_by_type):
        return None
    # 仍需一个合法 target_chapter；若仅靠 type 但缺 target，回退到 chapter_detected-1
    if target is None:
        target = max(1, chapter_detected - 1)
    if target >= chapter_detected:
        return None

    prefix = "DRIFT" if checker else "DEBT"
    return PropagationDebtItem(
        debt_id=f"{prefix}-{chapter_detected:04d}-{idx:03d}",
        chapter_detected=chapter_detected,
        rule_violation=_describe_rule(entry, checker=checker),
        target_chapter=target,
        severity=_severity_from_entry(entry),
        suggested_fix=_suggested_fix(entry),
        status="open",
    )


def _drifts_from_data(
    chapter: int,
    data: Mapping[str, Any],
    *,
    critical_limit: Optional[int] = DEFAULT_CRITICAL_ISSUE_LIMIT,
) -> List[PropagationDebtItem]:
    drifts: List[PropagationDebtItem] = []
    counter = 1

    critical = _safe_json_load(data.get("critical_issues")) or []
    if isinstance(critical, list):
        critical_drift_count = 0
        for entry in critical:
            if not isinstance(entry, Mapping):
                continue
            drift = _drift_from_entry(entry, chapter, counter)
            if drift is not None:
                drifts.append(drift)
                counter += 1
                critical_drift_count += 1
                if critical_limit is not None and critical_drift_count >= critical_limit:
                    break

    checker_results = data.get("checker_results")
    if isinstance(checker_results, Mapping):
        for checker in _DRIFT_CHECKERS:
            payload = checker_results.get(checker)
            if not isinstance(payload, Mapping):
                continue
            violations = payload.get("violations") or payload.get("issues") or []
            if not isinstance(violations, list):
                continue
            for entry in violations:
                if not isinstance(entry, Mapping):
                    continue
                drift = _drift_from_entry(entry, chapter, counter, checker=checker)
                if drift is not None:
                    drifts.append(drift)
                    counter += 1

    return drifts


def _row_to_data(row: sqlite3.Row) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    payload = _safe_json_load(row["review_payload_json"])
    if isinstance(payload, Mapping):
        data.update(payload)
    critical = _safe_json_load(row["critical_issues"])
    if critical is not None and "critical_issues" not in data:
        data["critical_issues"] = critical
    return data


def _load_records_from_db_legacy(
    project_root: Path, chapters: Sequence[int]
) -> Dict[int, Dict[str, Any]]:
    """旧 O(n) 路径：每章一次 SELECT，保留以便零回归回退。"""
    db_path = project_root / ".ink" / "index.db"
    records: Dict[int, Dict[str, Any]] = {}
    if not db_path.exists() or not chapters:
        return records
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        for ch in chapters:
            cur.execute(
                """
                SELECT critical_issues, review_payload_json
                FROM review_metrics
                WHERE start_chapter <= ? AND end_chapter >= ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (ch, ch),
            )
            row = cur.fetchone()
            if row is None:
                continue
            records[ch] = _row_to_data(row)
        conn.close()
    except sqlite3.Error:
        return records
    return records


def _load_records_from_db_batched(
    project_root: Path,
    chapters: Sequence[int],
    *,
    max_chapters_per_scan: int = DEFAULT_MAX_CHAPTERS_PER_SCAN,
) -> Dict[int, Dict[str, Any]]:
    """批量路径：每批一次范围重叠查询 + Python 端分配最新行至各章。

    对 1000 章区间，查询次数从 ~1000 降到 ceil(1000/max_chapters_per_scan) ≤ 20。
    """
    db_path = project_root / ".ink" / "index.db"
    records: Dict[int, Dict[str, Any]] = {}
    if not db_path.exists() or not chapters:
        return records
    if max_chapters_per_scan < 1:
        max_chapters_per_scan = DEFAULT_MAX_CHAPTERS_PER_SCAN
    sorted_chapters = sorted({int(c) for c in chapters})
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        for start in range(0, len(sorted_chapters), max_chapters_per_scan):
            batch = sorted_chapters[start : start + max_chapters_per_scan]
            if not batch:
                continue
            min_ch, max_ch = batch[0], batch[-1]
            # (start_chapter, end_chapter) 是 PRIMARY KEY，GROUP BY 语义等同
            # 去重；ORDER BY updated_at DESC 保证后续 Python 端“先到先得”即选到
            # 最新覆盖行。
            cur.execute(
                """
                SELECT start_chapter, end_chapter, critical_issues, review_payload_json
                FROM review_metrics
                WHERE start_chapter <= ? AND end_chapter >= ?
                GROUP BY start_chapter, end_chapter
                ORDER BY updated_at DESC
                """,
                (max_ch, min_ch),
            )
            rows = cur.fetchall()
            for row in rows:
                s = int(row["start_chapter"])
                e = int(row["end_chapter"])
                for ch in batch:
                    if ch in records:
                        continue
                    if s <= ch <= e:
                        records[ch] = _row_to_data(row)
        conn.close()
    except sqlite3.Error:
        return records
    return records


# 兼容别名：老代码 / 测试可能 import _load_records_from_db
def _load_records_from_db(
    project_root: Path,
    chapters: Sequence[int],
    *,
    max_chapters_per_scan: int = DEFAULT_MAX_CHAPTERS_PER_SCAN,
    legacy: bool = False,
) -> Dict[int, Dict[str, Any]]:
    if legacy:
        return _load_records_from_db_legacy(project_root, chapters)
    return _load_records_from_db_batched(
        project_root, chapters, max_chapters_per_scan=max_chapters_per_scan
    )


def _drift_debts_db_path(project_root: Path) -> Path:
    return project_root / DRIFT_DEBTS_DB_REL_PATH


def _open_drift_debts_cache(project_root: Path) -> sqlite3.Connection:
    """Open (or create) .ink/drift_debts.db with the US-004 schema."""
    db_path = _drift_debts_db_path(project_root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(_DRIFT_DEBTS_SCHEMA_SQL)
    conn.commit()
    return conn


def _cache_last_seen_max(conn: sqlite3.Connection) -> int:
    """Return the highest ``last_seen`` across all cached rows (0 if empty)."""
    row = conn.execute(
        "SELECT COALESCE(MAX(last_seen), 0) AS m FROM drift_debts"
    ).fetchone()
    if row is None:
        return 0
    value = row["m"] if isinstance(row, sqlite3.Row) else row[0]
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _cache_load_debts(conn: sqlite3.Connection) -> List[PropagationDebtItem]:
    """Load all cached drift debts, skipping rows with missing/corrupt payload."""
    debts: List[PropagationDebtItem] = []
    cursor = conn.execute(
        "SELECT payload FROM drift_debts "
        "WHERE debt_type != ? "
        "ORDER BY CAST(chapter_id AS INTEGER), debt_type",
        (_LAST_SEEN_META_KEY,),
    )
    for row in cursor.fetchall():
        payload = _safe_json_load(row["payload"])
        if not isinstance(payload, Mapping):
            continue
        try:
            debts.append(PropagationDebtItem.model_validate(dict(payload)))
        except Exception:  # pragma: no cover - defensive only
            continue
    return debts


def _cache_upsert_debts(
    conn: sqlite3.Connection,
    drifts: Sequence[PropagationDebtItem],
    watermark: int,
) -> None:
    """Insert-or-replace drift rows keyed by (chapter_detected, debt_id) and
    always refresh the watermark meta row so ``MAX(last_seen)`` reflects the
    most recently scanned chapter range even when zero drifts landed."""
    rows: List[Tuple[str, str, str, int]] = []
    for d in drifts:
        rows.append(
            (
                f"{int(d.chapter_detected):04d}",
                d.debt_id,
                json.dumps(d.model_dump(mode="json"), ensure_ascii=False),
                int(watermark),
            )
        )
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO drift_debts(chapter_id, debt_type, payload, last_seen) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )
    # Always write a meta row for the watermark so empty scans still bump it.
    conn.execute(
        "INSERT OR REPLACE INTO drift_debts(chapter_id, debt_type, payload, last_seen) "
        "VALUES (?, ?, NULL, ?)",
        (f"{int(watermark):04d}", _LAST_SEEN_META_KEY, int(watermark)),
    )
    conn.commit()


def reset_drift_debts_cache(project_root: Union[str, Path]) -> bool:
    """Drop the drift_debts table (keeps DB file for simplicity).

    Returns True if a cache existed and was cleared, False if no DB file.
    """
    root = Path(project_root)
    db_path = _drift_debts_db_path(root)
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("DROP TABLE IF EXISTS drift_debts")
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error:
        return False


def detect_drifts(
    project_root: Union[str, Path],
    chapter_range: ChapterRange,
    *,
    records: Optional[Mapping[int, Mapping[str, Any]]] = None,
    max_chapters_per_scan: int = DEFAULT_MAX_CHAPTERS_PER_SCAN,
    critical_limit: Optional[int] = DEFAULT_CRITICAL_ISSUE_LIMIT,
    legacy: bool = False,
    incremental: bool = False,
) -> List[PropagationDebtItem]:
    """扫描 chapter_range 内每章 review_metrics，返回 drift 列表。

    Args:
        project_root: 项目根目录，期望 `.ink/index.db` 存在。
        chapter_range: 章节区间，支持 (start, end) 元组或 Iterable[int]。
        records: 可选 mock 数据，提供后跳过 DB 读取（测试友好）。
        max_chapters_per_scan: 每批最多扫描章数（默认 50），超过则分批；仅
            影响默认的批量路径，不影响 legacy=True。
        critical_limit: 单章 critical_issues 最多生成多少条 drift（默认 20）；
            传 None 关闭早停。
        legacy: True 则走旧 O(n) 路径（1000 章 → 1000 次 SQL），默认 False。
        incremental: True 则启用 US-004 增量 cache：仅扫 chapter_id >
            last_seen_max 的章节，并把结果累加回 `.ink/drift_debts.db`。返回
            cache 中全部历史 drift + 本轮新增（已按 chapter_detected 稳定排序）。
    """
    chapters = _normalize_range(chapter_range)

    if incremental:
        cache_conn = _open_drift_debts_cache(Path(project_root))
        try:
            last_seen_max = _cache_last_seen_max(cache_conn)
            new_chapters = [c for c in chapters if c > last_seen_max]
            # Preserve caller ordering for the scan but dedupe for DB filter.
            if records is None:
                if new_chapters:
                    if legacy:
                        new_records: Mapping[int, Mapping[str, Any]] = (
                            _load_records_from_db_legacy(
                                Path(project_root), new_chapters
                            )
                        )
                    else:
                        new_records = _load_records_from_db_batched(
                            Path(project_root),
                            new_chapters,
                            max_chapters_per_scan=max_chapters_per_scan,
                        )
                else:
                    new_records = {}
            else:
                new_records = {
                    ch: records[ch] for ch in new_chapters if ch in records
                }

            new_drifts: List[PropagationDebtItem] = []
            for ch in new_chapters:
                data = new_records.get(ch)
                if not data:
                    continue
                new_drifts.extend(
                    _drifts_from_data(ch, data, critical_limit=critical_limit)
                )

            # Watermark = max chapter requested this call (so repeat calls with
            # same range short-circuit even when zero drifts landed), capped by
            # prior last_seen_max so non-incremental rescan ranges do not
            # regress the cursor.
            if chapters:
                new_watermark = max(last_seen_max, max(chapters))
            else:
                new_watermark = last_seen_max
            _cache_upsert_debts(cache_conn, new_drifts, new_watermark)

            merged = _cache_load_debts(cache_conn)
            merged.sort(key=lambda d: (d.chapter_detected, d.debt_id))
            return merged
        finally:
            cache_conn.close()

    if records is None:
        if legacy:
            records = _load_records_from_db_legacy(Path(project_root), chapters)
        else:
            records = _load_records_from_db_batched(
                Path(project_root),
                chapters,
                max_chapters_per_scan=max_chapters_per_scan,
            )
    drifts: List[PropagationDebtItem] = []
    for ch in chapters:
        data = records.get(ch)
        if not data:
            continue
        drifts.extend(_drifts_from_data(ch, data, critical_limit=critical_limit))
    return drifts


def _cli_main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry for US-004: python -m ink_writer.propagation.drift_detector --reset."""
    parser = argparse.ArgumentParser(
        prog="python -m ink_writer.propagation.drift_detector",
        description="Drift-detector cache management (US-004).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear .ink/drift_debts.db so the next incremental scan starts from chapter 1.",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root holding .ink/ (default: current working directory).",
    )
    args = parser.parse_args(argv)
    root = Path(args.project_root).resolve()
    if args.reset:
        cleared = reset_drift_debts_cache(root)
        target = _drift_debts_db_path(root)
        if cleared:
            print(f"drift_debts cache cleared: {target}")
        else:
            print(f"no drift_debts cache at {target} (nothing to clear)")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI thin wrapper
    sys.exit(_cli_main())
