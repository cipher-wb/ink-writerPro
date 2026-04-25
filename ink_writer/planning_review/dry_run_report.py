"""策划期 5 次观察期聚合报告（M4 P0 spec §5.5）。

扫描 ``<base_dir>/*/planning_evidence_chain.json``，按 checker / case 维度聚合
平均分、阻断次数、case 触发频次，输出 markdown 报告供编辑/PM review。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def _iter_planning_evidences(base_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    results: list[tuple[str, dict[str, Any]]] = []
    if not base_dir.exists():
        return results
    for sub in sorted(base_dir.iterdir()):
        if not sub.is_dir():
            continue
        candidate = sub / "planning_evidence_chain.json"
        if not candidate.exists():
            continue
        try:
            with open(candidate, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        results.append((sub.name, doc))
    return results


def _collect(
    docs: list[tuple[str, dict[str, Any]]],
) -> tuple[
    dict[str, list[float]],
    dict[str, int],
    dict[str, int],
    list[dict[str, Any]],
]:
    """聚合：每 checker score 列表 + 阻断次数 + case 触发计数 + per-stage 行。"""
    scores: dict[str, list[float]] = defaultdict(list)
    blocked_counts: dict[str, int] = defaultdict(int)
    case_counts: dict[str, int] = defaultdict(int)
    stage_rows: list[dict[str, Any]] = []

    for book, doc in docs:
        for stage in doc.get("stages", []) or []:
            stage_name = stage.get("stage", "?")
            outcome = stage.get("outcome", "?")
            dry_run = stage.get("dry_run", False)
            checkers = stage.get("phase_evidence", {}).get("checkers", []) or []
            stage_rows.append({
                "book": book,
                "stage": stage_name,
                "outcome": outcome,
                "dry_run": dry_run,
                "checker_count": len(checkers),
            })
            for ch in checkers:
                cid = ch.get("id", "?")
                score = ch.get("score")
                if isinstance(score, (int, float)):
                    scores[cid].append(float(score))
                if ch.get("blocked"):
                    blocked_counts[cid] += 1
                for case_id in ch.get("cases_hit", []) or []:
                    case_counts[case_id] += 1
    return scores, blocked_counts, case_counts, stage_rows


def _format_md(
    scores: dict[str, list[float]],
    blocked_counts: dict[str, int],
    case_counts: dict[str, int],
    stage_rows: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    lines.append("# Planning Dry-Run 聚合报告")
    lines.append("")
    lines.append(f"- 总书数（出现策划期 evidence）：{len({r['book'] for r in stage_rows})}")
    lines.append(f"- 总 stage 数：{len(stage_rows)}")
    lines.append("")

    lines.append("## Checker 平均分 / 阻断次数")
    lines.append("")
    lines.append("| checker | avg_score | runs | blocked |")
    lines.append("| --- | --- | --- | --- |")
    for cid in sorted(scores.keys() | blocked_counts.keys()):
        runs = len(scores.get(cid, []))
        avg = (
            f"{statistics.mean(scores[cid]):.3f}"
            if scores.get(cid)
            else "-"
        )
        lines.append(f"| {cid} | {avg} | {runs} | {blocked_counts.get(cid, 0)} |")
    lines.append("")

    lines.append("## Case 触发频次")
    lines.append("")
    if not case_counts:
        lines.append("（暂无 case 触发）")
    else:
        lines.append("| case_id | hits |")
        lines.append("| --- | --- |")
        for case_id, cnt in sorted(case_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"| {case_id} | {cnt} |")
    lines.append("")

    lines.append("## Per-stage 明细")
    lines.append("")
    lines.append("| book | stage | outcome | dry_run | checkers |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in stage_rows:
        lines.append(
            f"| {row['book']} | {row['stage']} | {row['outcome']} | "
            f"{row['dry_run']} | {row['checker_count']} |"
        )
    lines.append("")
    return "\n".join(lines)


def generate_planning_dry_run_report(
    *,
    base_dir: Path | str = "data",
) -> str:
    """聚合 ``<base_dir>/<book>/planning_evidence_chain.json`` 输出 markdown。"""
    target = Path(base_dir)
    docs = _iter_planning_evidences(target)
    scores, blocked, cases, rows = _collect(docs)
    return _format_md(scores, blocked, cases, rows)


def _build_cli_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ink_writer.planning_review.dry_run_report",
        description="M4 P0 策划期 5 次观察期聚合报告",
    )
    p.add_argument("--base-dir", type=Path, default=Path("data"))
    p.add_argument("--out", type=Path, default=None, help="可选：写到指定路径")
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ink-writer" / "scripts"))
        from runtime_compat import enable_windows_utf8_stdio  # noqa: PLC0415

        enable_windows_utf8_stdio()
    except ImportError:
        pass

    args = _build_cli_parser().parse_args(argv)
    md = generate_planning_dry_run_report(base_dir=args.base_dir)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md)
    else:
        print(md)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
