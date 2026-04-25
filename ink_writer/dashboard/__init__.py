"""Dashboard aggregation surface — M5 治理指标 + overview JSON。

Public surface used by ink CLI and the Web Dashboard:

- :mod:`ink_writer.dashboard.aggregator` — pure metric helpers (recurrence
  rate, repair speed, editor score trend, checker accuracy, dry-run pass
  rate, switch recommendation).
- :mod:`ink_writer.dashboard.m5_overview` — bundled JSON payload served at
  ``/api/m5-overview``.

Spec §13 acceptance: all helpers degrade gracefully when source files are
missing (return ``0.0`` / empty list) so a fresh project never crashes the
dashboard.
"""
import argparse
from pathlib import Path

from ink_writer.dashboard.aggregator import (
    compute_checker_accuracy,
    compute_editor_score_trend,
    compute_m3_dry_run_pass_rate,
    compute_m4_dry_run_pass_rate,
    compute_recurrence_rate,
    compute_repair_speed,
    recommend_dry_run_switch,
)
from ink_writer.dashboard.m5_overview import get_m5_overview

__all__ = [
    "cli_main",
    "compute_checker_accuracy",
    "compute_editor_score_trend",
    "compute_m3_dry_run_pass_rate",
    "compute_m4_dry_run_pass_rate",
    "compute_recurrence_rate",
    "compute_repair_speed",
    "get_m5_overview",
    "recommend_dry_run_switch",
]


def cli_main(argv: list[str] | None = None) -> int:
    """Top-level dashboard CLI — routes ``report`` subcommand to weekly_report.

    Used by ``ink dashboard <subcommand>`` style wrappers (US-006). Today only
    the ``report`` subcommand is registered; future subcommands (overview /
    serve) plug in the same way.
    """
    parser = argparse.ArgumentParser(
        prog="ink dashboard",
        description="Ink dashboard CLI — M5 治理周报 / 指标聚合入口。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    report_p = sub.add_parser(
        "report", help="生成 M5 周报 markdown（reports/weekly/<Y>-W<NN>.md）。"
    )
    report_p.add_argument("--week", type=int, required=True)
    report_p.add_argument("--year", type=int, default=2026)
    report_p.add_argument("--book", default=None)
    report_p.add_argument("--base-dir", default="data")
    report_p.add_argument("--out", default=None)

    args = parser.parse_args(argv)

    if args.command == "report":
        from ink_writer.dashboard.weekly_report import generate_weekly_report

        out_path = generate_weekly_report(
            week_num=args.week,
            year=args.year,
            book=args.book,
            base_dir=Path(args.base_dir),
            out_path=Path(args.out) if args.out else None,
        )
        print(f"周报已生成：{out_path}")
        return 0

    parser.error(f"未知子命令：{args.command}")
    return 2  # pragma: no cover — argparse already exited
