"""US-006: ``ink dashboard report --week N`` weekly markdown generator.

Pulls the bundled :func:`get_m5_overview` payload and renders a five-section
markdown report covering the four headline metrics, Layer-4 recurrent cases,
Layer-5 pending meta-rule proposals, dry-run posture, and a derived action
list.

Defaults write to ``reports/weekly/<year>-W<NN>.md`` from the current working
directory; pass ``out_path=`` to override.
"""
from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path
from typing import Any

from ink_writer.case_library.store import CaseStore
from ink_writer.dashboard.m5_overview import get_m5_overview


def _week_range(week_num: int, year: int) -> tuple[str, str]:
    """Return ``(monday, sunday)`` ISO date strings for ISO ``year-Wweek_num``.

    Example: ``_week_range(17, 2026) == ("2026-04-20", "2026-04-26")``.
    """
    monday = _dt.date.fromisocalendar(year, week_num, 1)
    sunday = _dt.date.fromisocalendar(year, week_num, 7)
    return monday.isoformat(), sunday.isoformat()


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _fmt_score_trend(trend: list[dict[str, Any]]) -> str:
    if not trend:
        return "（暂无编辑评分数据）"
    pieces: list[str] = []
    for item in trend[-5:]:
        date = item.get("date") or "?"
        score = item.get("score")
        book = item.get("book") or "?"
        score_s = f"{score}" if score is not None else "?"
        pieces.append(f"{date} `{book}` 分数={score_s}")
    return "；".join(pieces)


def _build_action_items(overview: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    pending = overview.get("pending_meta_rules") or []
    if len(pending) >= 1:
        actions.append(f"审批 {len(pending)} 条 pending 元规则")
    dry_run = overview.get("dry_run") or {}
    for channel_key, channel_label in (("m3", "M3"), ("m4", "M4")):
        channel = dry_run.get(channel_key) or {}
        if channel.get("recommendation") == "switch":
            actions.append(f"评估 {channel_label} dry-run 切真")
    return actions


def _render_markdown(
    *,
    week_num: int,
    year: int,
    week_start: str,
    week_end: str,
    book: str | None,
    overview: dict[str, Any],
) -> str:
    metrics = overview.get("metrics") or {}
    dry_run = overview.get("dry_run") or {}
    pending = overview.get("pending_meta_rules") or []
    recurrent = overview.get("recurrent_cases") or []
    actions = _build_action_items(overview)

    lines: list[str] = []
    lines.append(f"# Ink Writer 周报 {year}-W{week_num:02d}")
    lines.append("")
    scope = f"区间：{week_start} → {week_end}"
    if book:
        scope += f"  ｜  书目：`{book}`"
    lines.append(scope)
    lines.append("")

    lines.append("## 4 大指标")
    recurrence = metrics.get("recurrence_rate", 0.0) or 0.0
    repair = metrics.get("repair_speed_days", 0.0) or 0.0
    accuracy = metrics.get("checker_accuracy", 0.0) or 0.0
    trend = metrics.get("editor_score_trend") or []
    lines.append(f"- 复发率：{_fmt_pct(recurrence)}")
    lines.append(f"- 平均修复时长：{repair:.1f} 天（M5 占位 — 待 case schema 加 resolved_at）")
    lines.append(f"- 检查器准确率：{_fmt_pct(accuracy)}（M5 占位 — 待人工标注样本落地）")
    lines.append(f"- 编辑评分趋势：{_fmt_score_trend(trend)}")
    lines.append("")

    lines.append("## Layer 4 复发追踪")
    if not recurrent:
        lines.append("- 本周无新增复发 case。")
    else:
        for item in recurrent:
            cid = item.get("case_id", "?")
            title = item.get("title", "")
            count = item.get("recurrence_count", 0)
            severity = item.get("severity", "?")
            last = item.get("last_regressed_at") or "?"
            lines.append(
                f"- `{cid}` {title} — 复发 {count} 次（最近 {last}，严重度 {severity}）"
            )
    lines.append("")

    lines.append("## Layer 5 元规则浮现")
    if not pending:
        lines.append("- 暂无 pending 元规则。")
    else:
        for item in pending:
            mid = item.get("proposal_id", "?")
            sim = item.get("similarity")
            sim_s = f"{sim:.2f}" if isinstance(sim, (int, float)) else "?"
            covered = item.get("covered_cases") or []
            merged = item.get("merged_rule") or ""
            lines.append(
                f"- `{mid}` sim={sim_s} cases={len(covered)} :: {merged}"
            )
    lines.append("")

    lines.append("## Dry-run 状态")
    for channel_key, channel_label in (("m3", "M3 章节"), ("m4", "M4 策划")):
        channel = dry_run.get(channel_key) or {}
        counter = channel.get("counter", 0)
        pass_rate = channel.get("pass_rate", 0.0) or 0.0
        recommendation = channel.get("recommendation", "continue")
        lines.append(
            f"- {channel_label}：观察 {counter} 次，通过率 {_fmt_pct(pass_rate)}，建议 `{recommendation}`"
        )
    lines.append("")

    lines.append("## 行动项")
    if not actions:
        lines.append("- 本周暂无紧急行动项。")
    else:
        for action in actions:
            lines.append(f"- {action}")
    lines.append("")

    return "\n".join(lines)


def generate_weekly_report(
    *,
    week_num: int,
    year: int = 2026,
    book: str | None = None,
    base_dir: Path = Path("data"),
    out_path: Path | None = None,
) -> Path:
    """Generate the markdown weekly report and return the written path.

    Args:
        week_num: ISO week number (1–53).
        year: ISO year (default 2026).
        book: optional book filter — currently surfaced in the report header
            only; metric scoping by book is a post-M5 follow-up.
        base_dir: project ``data/`` root (counters + per-book evidence live here).
        out_path: explicit output path; defaults to
            ``reports/weekly/<year>-W<NN>.md`` from the current working dir.
    """
    week_start, week_end = _week_range(week_num, year)

    base = Path(base_dir)
    case_store = CaseStore(base / "case_library")
    overview = get_m5_overview(base_dir=base, case_store=case_store)

    markdown = _render_markdown(
        week_num=week_num,
        year=year,
        week_start=week_start,
        week_end=week_end,
        book=book,
        overview=overview,
    )

    if out_path is None:
        out_path = Path("reports") / "weekly" / f"{year}-W{week_num:02d}.md"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(markdown)
    return out_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ink_writer.dashboard.weekly_report",
        description="US-006: 生成 M5 周报 markdown（reports/weekly/<Y>-W<NN>.md）。",
    )
    parser.add_argument(
        "--week",
        type=int,
        required=True,
        help="ISO 周编号 1-53（必填）。",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2026,
        help="ISO 年份（默认 2026）。",
    )
    parser.add_argument(
        "--book",
        default=None,
        help="可选书目筛选；当前仅在报告头部显示。",
    )
    parser.add_argument(
        "--base-dir",
        default="data",
        help="项目数据根目录（默认 data）。",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="输出 markdown 路径；默认 reports/weekly/<Y>-W<NN>.md。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:  # pragma: no cover — Windows stdio bootstrap (no-op on Mac/Linux)
        import os
        import sys

        scripts_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "../../ink-writer/scripts",
        )
        if os.path.isdir(scripts_dir) and scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from runtime_compat import enable_windows_utf8_stdio

        enable_windows_utf8_stdio()
    except Exception:
        pass
    parser = _build_parser()
    args = parser.parse_args(argv)
    out_path = generate_weekly_report(
        week_num=args.week,
        year=args.year,
        book=args.book,
        base_dir=Path(args.base_dir),
        out_path=Path(args.out) if args.out else None,
    )
    print(f"周报已生成：{out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
