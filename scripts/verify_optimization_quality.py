#!/usr/bin/env python3
"""Compare review reports before/after optimization to verify quality hasn't degraded.

Usage:
    python3 scripts/verify_optimization_quality.py --before dir1 --after dir2

Compares 4 dimensions:
  1. overall_score: avg diff ≤ 2
  2. Per-checker scores: each avg diff ≤ 3
  3. Issue count: after ≤ before + 1
  4. Entity extraction count: diff ≤ 5%
"""

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio
_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    '../ink-writer/scripts',
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass

import argparse
import glob
import json
import os
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
OVERALL_SCORE_THRESHOLD = 2
CHECKER_SCORE_THRESHOLD = 3
ISSUES_EXTRA_ALLOWED = 1
ENTITY_DIFF_PERCENT = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_reports(directory: str) -> list[dict[str, Any]]:
    """Load all review_ch*.json files from *directory*."""
    pattern = os.path.join(directory, "review_ch*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No review_ch*.json files found in {directory}")
    reports: list[dict] = []
    for fpath in files:
        with open(fpath, encoding="utf-8") as fh:
            reports.append(json.load(fh))
    return reports


def load_data_agent_outputs(directory: str) -> list[dict[str, Any]]:
    """Load data_agent_payload_ch*.json or data_agent_output_ch*.json files."""
    results: list[dict] = []
    for pat in ("data_agent_payload_ch*.json", "data_agent_output_ch*.json"):
        for fpath in sorted(glob.glob(os.path.join(directory, pat))):
            with open(fpath, encoding="utf-8") as fh:
                results.append(json.load(fh))
    return results


def extract_metrics(reports: list[dict], data_outputs: list[dict]) -> dict[str, Any]:
    """Aggregate metrics from review reports and optional data-agent outputs."""
    overall_scores: list[float] = []
    checker_scores: dict[str, list[float]] = {}
    total_issues = 0
    entity_count = 0

    for report in reports:
        overall_scores.append(float(report.get("overall_score", 0)))

        for name, result in report.get("checker_results", {}).items():
            checker_scores.setdefault(name, []).append(float(result.get("overall_score", 0)))
            total_issues += len(result.get("issues", []))

        # Try entity count from review_payload_json
        payload = report.get("review_payload_json", {})
        entity_count += int(payload.get("entity_count", 0))

    # Entity counts from data-agent outputs
    for out in data_outputs:
        entity_count += int(out.get("entities_appeared", 0))
        entity_count += int(out.get("entities_new", 0))

    avg_overall = sum(overall_scores) / len(overall_scores) if overall_scores else 0.0
    avg_checker = {k: sum(v) / len(v) for k, v in checker_scores.items()}

    return {
        "avg_overall": avg_overall,
        "avg_checker": avg_checker,
        "total_issues": total_issues,
        "entity_count": entity_count,
    }


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def compare_metrics(
    before: dict[str, Any],
    after: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Compare before/after metrics. Returns (passed, detail_lines)."""
    passed = True
    details: list[str] = []

    # 1. overall_score
    diff = before["avg_overall"] - after["avg_overall"]
    status = "PASS" if diff <= OVERALL_SCORE_THRESHOLD else "FAIL"
    if status == "FAIL":
        passed = False
    details.append(
        f"| overall_score | {before['avg_overall']:.1f} | {after['avg_overall']:.1f} | {diff:+.1f} | ≤{OVERALL_SCORE_THRESHOLD} | {status} |"
    )

    # 2. Per-checker scores
    all_checkers = sorted(set(before["avg_checker"]) | set(after["avg_checker"]))
    for checker in all_checkers:
        b = before["avg_checker"].get(checker, 0.0)
        a = after["avg_checker"].get(checker, 0.0)
        d = b - a
        st = "PASS" if d <= CHECKER_SCORE_THRESHOLD else "FAIL"
        if st == "FAIL":
            passed = False
        details.append(f"| {checker} | {b:.1f} | {a:.1f} | {d:+.1f} | ≤{CHECKER_SCORE_THRESHOLD} | {st} |")

    # 3. Issue count
    b_issues = before["total_issues"]
    a_issues = after["total_issues"]
    extra = a_issues - b_issues
    st = "PASS" if extra <= ISSUES_EXTRA_ALLOWED else "FAIL"
    if st == "FAIL":
        passed = False
    details.append(f"| issues_count | {b_issues} | {a_issues} | {extra:+d} | ≤+{ISSUES_EXTRA_ALLOWED} | {st} |")

    # 4. Entity extraction count
    b_ent = before["entity_count"]
    a_ent = after["entity_count"]
    if b_ent > 0:
        pct = abs(b_ent - a_ent) / b_ent * 100
    else:
        pct = 0.0 if a_ent == 0 else 100.0
    st = "PASS" if pct <= ENTITY_DIFF_PERCENT else "FAIL"
    if st == "FAIL":
        passed = False
    details.append(
        f"| entity_count | {b_ent} | {a_ent} | {pct:.1f}% | ≤{ENTITY_DIFF_PERCENT}% | {st} |"
    )

    return passed, details


def format_report(passed: bool, details: list[str]) -> str:
    """Render a markdown comparison report."""
    header = "# Optimization Quality Verification Report\n\n"
    verdict = f"**Result: {'PASS ✓' if passed else 'FAIL ✗'}**\n\n"
    table_hdr = "| Metric | Before | After | Diff | Threshold | Status |\n|--------|--------|-------|------|-----------|--------|\n"
    return header + verdict + table_hdr + "\n".join(details) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare review reports before/after optimization.")
    parser.add_argument("--before", required=True, help="Directory with pre-optimization review JSONs")
    parser.add_argument("--after", required=True, help="Directory with post-optimization review JSONs")
    args = parser.parse_args(argv)

    before_reports = load_reports(args.before)
    after_reports = load_reports(args.after)

    before_data = load_data_agent_outputs(args.before)
    after_data = load_data_agent_outputs(args.after)

    before_metrics = extract_metrics(before_reports, before_data)
    after_metrics = extract_metrics(after_reports, after_data)

    passed, details = compare_metrics(before_metrics, after_metrics)
    report = format_report(passed, details)
    print(report)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
