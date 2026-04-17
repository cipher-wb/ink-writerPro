#!/usr/bin/env python3
"""Step 3 Harness Gate: 读取审查结果，硬拦截质量不合格的章节。

Exit codes:
  0 = 通过，可进入 Step 4
  1 = 硬拦截，必须回退 Step 2A 重写
  2 = 脚本错误（静默跳过）

v13 Health Audit US-005 修复（2026-04-17）：
  数据源优先级：index.db.review_metrics → 老 .ink/reports/review_ch*.json（fallback，打 warning）。
  若两者均无对应章节记录 → 显式 FAIL（不再是 silent PASS，v5 审计确认生产链路只写 index.db）。
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_review_data_from_index_db(project_root: Path, chapter_num: int) -> dict | None:
    """Try to load review data from index.db.review_metrics for the given chapter.

    Returns the review payload dict (same shape as legacy JSON) or None if no matching row.
    v13 US-005: index.db.review_metrics 是生产链路实际写入的表。
    """
    db_path = project_root / ".ink" / "index.db"
    if not db_path.exists():
        return None
    try:
        import sqlite3
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT overall_score, dimension_scores, severity_counts, critical_issues,
                       review_payload_json, report_file, notes
                FROM review_metrics
                WHERE start_chapter <= ? AND end_chapter >= ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (chapter_num, chapter_num),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            # 若存在完整 payload（含 checker_results）则用 payload；否则基于列组 minimal dict
            payload_json = row["review_payload_json"]
            if payload_json:
                try:
                    return json.loads(payload_json)
                except json.JSONDecodeError:
                    pass
            return {
                "overall_score": row["overall_score"] or 100,
                "severity_counts": json.loads(row["severity_counts"]) if row["severity_counts"] else {},
                "dimension_scores": json.loads(row["dimension_scores"]) if row["dimension_scores"] else {},
                "critical_issues": json.loads(row["critical_issues"]) if row["critical_issues"] else [],
                "checker_results": {},  # 老 payload_json 缺失时只能降级为 minimal 模式
            }
    except Exception as exc:
        logger.warning("index.db read failed for chapter %s: %s; falling back to JSON", chapter_num, exc)
        return None


def _load_review_data_from_json(project_root: Path, chapter_num: int) -> dict | None:
    """Legacy path：从 .ink/reports/review_ch*.json 读取审查数据。打 warning 提示该路径已迁移。"""
    reports_dir = project_root / ".ink" / "reports"
    if not reports_dir.exists():
        return None
    for f in sorted(reports_dir.glob("review_ch*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            start = data.get("start_chapter", 0)
            end = data.get("end_chapter", 0)
            if start <= chapter_num <= end:
                logger.warning(
                    "legacy JSON path used for chapter %s (%s); review data should be in index.db.review_metrics. "
                    "Migrate via save_review_metrics().",
                    chapter_num,
                    f.name,
                )
                return data
        except (json.JSONDecodeError, OSError):
            continue
    return None


def check_review_gate(project_root: Path, chapter_num: int) -> dict:
    """检查审查结果是否通过闸门。

    v13 US-005 数据源顺序：
      1. index.db.review_metrics（生产链路真实写入的表）
      2. .ink/reports/review_ch*.json（legacy fallback + warning）
      3. 两者均无记录 → 显式 FAIL（历史默认 silent PASS 是 bug）
    """
    result = {"pass": True, "reason": "", "action": "continue"}

    data = _load_review_data_from_index_db(project_root, chapter_num)
    if data is None:
        data = _load_review_data_from_json(project_root, chapter_num)

    if data is None:
        # v13 US-005：无审查数据 = 显式 FAIL（不再默认 PASS，v5 审计 Blocker 修复）
        result["pass"] = False
        result["reason"] = (
            f"no review data found for chapter {chapter_num} "
            f"(checked index.db.review_metrics and .ink/reports/review_ch*.json)"
        )
        result["action"] = "rerun_step3_review"
        return result

    overall_score = data.get("overall_score", 100)
    severity_counts = data.get("severity_counts", {})
    critical_count = severity_counts.get("critical", 0)
    checker_results = data.get("checker_results", {})

    # 规则1: 黄金三章硬拦截
    if chapter_num <= 3:
        golden = checker_results.get("golden-three-checker", {})
        golden_issues = golden.get("issues", [])
        high_issues = [i for i in golden_issues if i.get("severity") == "high"]
        if high_issues:
            result["pass"] = False
            result["reason"] = f"黄金三章(ch{chapter_num})存在 {len(high_issues)} 个 high 级问题"
            result["action"] = "rewrite_step2a"
            return result

    # 规则2: 读者体验阻断
    reader_sim = checker_results.get("reader-simulator", {})
    verdict = reader_sim.get("reader_verdict", {}).get("verdict", "")
    if verdict == "rewrite":
        if chapter_num <= 3:
            result["pass"] = False
            result["reason"] = f"reader-simulator 判定 rewrite (ch{chapter_num})"
            result["action"] = "rewrite_step2a"
            return result
        # ch4+ 仅为强警告
        print(f"⚠️  reader-simulator 判定 rewrite，强烈建议重写", file=sys.stderr)

    # 规则3: overall_score 过低
    if overall_score < 40:
        result["pass"] = False
        result["reason"] = f"overall_score={overall_score} < 40"
        result["action"] = "rewrite_step2a"
        return result

    # 规则4: critical 过多
    if critical_count >= 3:
        result["pass"] = False
        result["reason"] = f"critical issues={critical_count} >= 3"
        result["action"] = "rewrite_step2a"

    return result


class ChapterBlockedError(Exception):
    """Raised when editor-wisdom gate blocks a chapter after max retries."""


def _find_chapter_file(project_root: Path, chapter_num: int) -> Path | None:
    chapter_dir = project_root / "chapters" / str(chapter_num)
    for name in ("draft.md", "chapter.md", "final.md"):
        candidate = chapter_dir / name
        if candidate.exists():
            return candidate
    if chapter_dir.exists():
        mds = sorted(chapter_dir.glob("*.md"))
        for md in mds:
            if md.name != "blocked.md":
                return md
    return None


def run_editor_wisdom_gate(
    project_root: Path,
    chapter_num: int,
    chapter_text: str | None = None,
    *,
    checker_fn: Callable[[str, int], dict] | None = None,
    polish_fn: Callable[[str, list[dict], int], str] | None = None,
) -> int:
    """Run the editor-wisdom hard gate. Returns 0=pass, 1=blocked.

    Raises ChapterBlockedError when the gate blocks after max retries.
    """
    from ink_writer.editor_wisdom.config import load_config
    from ink_writer.editor_wisdom.review_gate import run_review_gate

    config = load_config()
    if not config.enabled:
        return 0

    if chapter_text is None:
        chapter_file = _find_chapter_file(project_root, chapter_num)
        if chapter_file is None:
            return 0
        chapter_text = chapter_file.read_text(encoding="utf-8")

    if checker_fn is None:
        def checker_fn(text: str, ch_no: int) -> dict:
            from ink_writer.editor_wisdom.checker import check_chapter
            from ink_writer.editor_wisdom.retriever import Retriever
            retriever = Retriever()
            rules = retriever.retrieve(text)
            return check_chapter(text, ch_no, rules, config=config)

    if polish_fn is None:
        def polish_fn(text: str, violations: list[dict], ch_no: int) -> str:
            return text

    result = run_review_gate(
        chapter_text=chapter_text,
        chapter_no=chapter_num,
        project_root=str(project_root),
        checker_fn=checker_fn,
        polish_fn=polish_fn,
        config=config,
    )

    if not result.passed:
        raise ChapterBlockedError(
            f"Chapter {chapter_num} blocked after {len(result.attempts)} attempts "
            f"(score={result.final_score}, threshold={result.threshold}). "
            f"See {result.blocked_path}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Step 3 Harness Gate")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    try:
        result = check_review_gate(args.project_root, args.chapter)
    except Exception as e:
        print(f"Gate error: {e}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["pass"]:
            print(f"✅ Step 3 Gate PASS (ch{args.chapter})")
        else:
            print(f"❌ Step 3 Gate FAIL: {result['reason']}")
            print(f"   Action: {result['action']}")

    if not result["pass"]:
        return 1

    try:
        run_editor_wisdom_gate(args.project_root, args.chapter)
        print(f"✅ Editor-Wisdom Gate PASS (ch{args.chapter})")
    except ChapterBlockedError as e:
        print(f"❌ Editor-Wisdom Gate BLOCKED: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
