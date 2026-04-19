"""FIX-17 P4b: canon drift detector.

扫描 index.db.review_metrics（critical_issues + checker_results）识别
"下游章节发现的上游矛盾"，产出 PropagationDebtItem 列表供后续反向传播清算。

判定规则（符合 US-015 acceptance）:
1. critical_issues 中带 target_chapter < chapter_detected 或 type 归属
   {"cross_chapter_conflict", "back_propagation"} 视为 drift
2. checker_results["consistency-checker"|"continuity-checker"].violations
   中 target_chapter < chapter_detected 视为 drift
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from ink_writer.propagation.models import PropagationDebtItem, Severity

_CROSS_CHAPTER_TYPES = {"cross_chapter_conflict", "back_propagation", "canon_drift"}
_DRIFT_CHECKERS = ("consistency-checker", "continuity-checker")
_CHAPTER_KEYS = ("target_chapter", "ref_chapter", "source_chapter", "chapter")

DEFAULT_MAX_CHAPTERS_PER_SCAN = 50
DEFAULT_CRITICAL_ISSUE_LIMIT = 20


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


def detect_drifts(
    project_root: Union[str, Path],
    chapter_range: ChapterRange,
    *,
    records: Optional[Mapping[int, Mapping[str, Any]]] = None,
    max_chapters_per_scan: int = DEFAULT_MAX_CHAPTERS_PER_SCAN,
    critical_limit: Optional[int] = DEFAULT_CRITICAL_ISSUE_LIMIT,
    legacy: bool = False,
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
    """
    chapters = _normalize_range(chapter_range)
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
