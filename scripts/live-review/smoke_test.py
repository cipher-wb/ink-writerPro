#!/usr/bin/env python3
"""US-LR-013: live-review end-to-end smoke test.

Default mode runs without ANTHROPIC_API_KEY (uses fixture mock_response for
review checker; init path uses pre-built or freshly-built vector index).

Pass `--with-api` to exercise the real Anthropic LLM path on the review step
(user-triggered manual operation per spec §M-9; not part of ralph CI).

Usage:
    python3 scripts/live-review/smoke_test.py
    python3 scripts/live-review/smoke_test.py --with-api
    python3 scripts/live-review/smoke_test.py --index-dir TMP --report-out R.md
"""
from __future__ import annotations

# US-LR-013: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio

_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    "../../ink-writer/scripts",
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ink_writer.live_review._vector_index import build_index  # noqa: E402
from ink_writer.live_review.checker import run_live_review_checker  # noqa: E402
from ink_writer.live_review.init_injection import check_genre  # noqa: E402

DEFAULT_INDEX_DIR = _REPO_ROOT / "data" / "live-review" / "vector_index"
DEFAULT_REPORT_OUT = _REPO_ROOT / "reports" / "live-review-smoke-report.md"
DEFAULT_CASES_DIR = (
    _REPO_ROOT / "tests" / "live_review" / "fixtures" / "sample_30_cases"
)
FIXTURE_CHAPTER = (
    _REPO_ROOT / "tests" / "live_review" / "fixtures" / "sample_chapter_violating.txt"
)
FIXTURE_CHECKER_MOCK = (
    _REPO_ROOT
    / "tests"
    / "live_review"
    / "fixtures"
    / "mock_live_review_checker_response.json"
)


@dataclass
class StepResult:
    name: str
    status: str  # 'PASS' | 'FAIL'
    elapsed_s: float
    detail: str = ""


def _ensure_index(index_dir: Path, cases_dir: Path) -> tuple[StepResult, bool]:
    """Reuse existing index or build from cases_dir; report PASS/FAIL + ok flag."""
    t0 = time.time()
    if (index_dir / "index.faiss").exists() and (index_dir / "meta.jsonl").exists():
        return (
            StepResult(
                "ensure_index", "PASS", time.time() - t0, f"reuse existing {index_dir}"
            ),
            True,
        )
    if not cases_dir.is_dir():
        return (
            StepResult(
                "ensure_index",
                "FAIL",
                time.time() - t0,
                f"cases-dir not found: {cases_dir}",
            ),
            False,
        )
    try:
        stats = build_index(cases_dir, index_dir)
    except Exception as e:  # noqa: BLE001 — surface any builder error in report
        return (
            StepResult(
                "ensure_index", "FAIL", time.time() - t0, f"{type(e).__name__}: {e}"
            ),
            False,
        )
    return (
        StepResult(
            "ensure_index",
            "PASS",
            time.time() - t0,
            f"built {stats['cases_indexed']} cases (dim={stats['embedding_dim']})",
        ),
        True,
    )


def _step_init(index_dir: Path) -> StepResult:
    """Step 1: ink-init Step 99.5 — check_genre returns warning_level + render_text."""
    t0 = time.time()
    query = "都市重生律师"
    try:
        result = check_genre(query, top_k=3, index_dir=index_dir)
    except Exception as e:  # noqa: BLE001 — record exception detail in report
        return StepResult(
            "init_check_genre", "FAIL", time.time() - t0, f"{type(e).__name__}: {e}"
        )
    warning = result.get("warning_level")
    if warning not in {"ok", "warn", "no_data"}:
        return StepResult(
            "init_check_genre",
            "FAIL",
            time.time() - t0,
            f"unexpected warning_level={warning!r}",
        )
    if not result.get("render_text"):
        return StepResult(
            "init_check_genre", "FAIL", time.time() - t0, "render_text empty"
        )
    return StepResult(
        "init_check_genre",
        "PASS",
        time.time() - t0,
        (
            f"warning_level={warning}, "
            f"similar_cases={len(result.get('similar_cases', []))}"
        ),
    )


def _step_review(index_dir: Path, *, with_api: bool) -> StepResult:
    """Step 2: ink-review Step 3.6 — run_live_review_checker on bad chapter.

    Default uses fixture mock_response (no LLM call).
    `--with-api` skips mock and runs real Anthropic SDK against Top-K retrieval.
    """
    t0 = time.time()
    if not FIXTURE_CHAPTER.exists():
        return StepResult(
            "review_checker",
            "FAIL",
            time.time() - t0,
            f"missing fixture {FIXTURE_CHAPTER}",
        )
    chapter = FIXTURE_CHAPTER.read_text(encoding="utf-8")
    try:
        if with_api:
            result = run_live_review_checker(
                chapter, 3, ["都市", "重生"], index_dir=index_dir
            )
        else:
            mock = json.loads(FIXTURE_CHECKER_MOCK.read_text(encoding="utf-8"))
            result = run_live_review_checker(
                chapter,
                3,
                ["都市", "重生"],
                mock_response=mock,
                index_dir=index_dir,
            )
    except Exception as e:  # noqa: BLE001 — record exception detail in report
        return StepResult(
            "review_checker", "FAIL", time.time() - t0, f"{type(e).__name__}: {e}"
        )
    if "score" not in result:
        return StepResult(
            "review_checker", "FAIL", time.time() - t0, "missing 'score' field"
        )
    if not isinstance(result.get("violations"), list):
        return StepResult(
            "review_checker",
            "FAIL",
            time.time() - t0,
            f"'violations' not list: {type(result.get('violations')).__name__}",
        )
    if not isinstance(result.get("cases_hit"), list):
        return StepResult(
            "review_checker",
            "FAIL",
            time.time() - t0,
            f"'cases_hit' not list: {type(result.get('cases_hit')).__name__}",
        )
    return StepResult(
        "review_checker",
        "PASS",
        time.time() - t0,
        f"score={result['score']:.2f}, violations={len(result['violations'])}",
    )


def _write_report(out_path: Path, steps: list[StepResult], *, with_api: bool) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    mode = "with-api" if with_api else "mock"
    failed = sum(1 for s in steps if s.status != "PASS")
    summary = "All checks PASS" if failed == 0 else f"{failed} checks FAILED"
    lines: list[str] = [
        "# Live-Review End-to-End Smoke Test Report",
        "",
        "> Generated by `scripts/live-review/smoke_test.py`",
        "",
        f"- **Date**: {now}",
        f"- **Mode**: {mode}",
        f"- **Summary**: {summary}",
        "",
        "## Steps",
        "",
        "| Step | Status | Elapsed | Detail |",
        "| --- | --- | --- | --- |",
    ]
    for s in steps:
        detail = s.detail.replace("|", "\\|")
        lines.append(f"| {s.name} | {s.status} | {s.elapsed_s:.2f}s | {detail} |")
    lines.append("")
    lines.append(summary)
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Live-Review end-to-end smoke test (mock by default)."
    )
    parser.add_argument(
        "--with-api",
        action="store_true",
        default=False,
        help="Skip mock_response on review step; call real Anthropic LLM.",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=DEFAULT_INDEX_DIR,
        help=f"FAISS index directory (default: {DEFAULT_INDEX_DIR}).",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=DEFAULT_REPORT_OUT,
        help=f"Markdown report path (default: {DEFAULT_REPORT_OUT}).",
    )
    parser.add_argument(
        "--cases-dir",
        type=Path,
        default=DEFAULT_CASES_DIR,
        help=(
            "Cases directory used to (re)build the index when missing "
            f"(default: {DEFAULT_CASES_DIR})."
        ),
    )
    args = parser.parse_args(argv)

    steps: list[StepResult] = []
    ensure_step, ok = _ensure_index(args.index_dir, args.cases_dir)
    steps.append(ensure_step)
    if ok:
        steps.append(_step_init(args.index_dir))
        steps.append(_step_review(args.index_dir, with_api=args.with_api))

    _write_report(args.report_out, steps, with_api=args.with_api)

    all_pass = all(s.status == "PASS" for s in steps)
    print(
        f"Smoke test {'PASS' if all_pass else 'FAIL'}. Report: {args.report_out}",
        flush=True,
    )
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
