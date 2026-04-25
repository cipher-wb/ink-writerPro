"""``python -m ink_writer.regression_tracker`` — Layer 4 dry-run / apply CLI."""
from __future__ import annotations

import argparse
import json
import os as _os_win_stdio
import sys as _sys_win_stdio
from pathlib import Path

_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    "../../ink-writer/scripts",
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:  # pragma: no cover
    pass

from ink_writer.case_library.store import CaseStore
from ink_writer.regression_tracker.tracker import (
    apply_recurrence,
    scan_evidence_chains,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ink_writer.regression_tracker",
        description="Layer 4 regression tracker — scan evidence_chain for resolved-case recurrences.",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Skip evidence chains with produced_at < SINCE (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist detected recurrences (severity bump + status=regressed).",
    )
    parser.add_argument(
        "--base-dir",
        default="data",
        help="Parent directory of per-book evidence chains (default: data).",
    )
    parser.add_argument(
        "--library-root",
        default="data/case_library",
        help="Case library root (default: data/case_library).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    store = CaseStore(Path(args.library_root))
    records = scan_evidence_chains(
        base_dir=Path(args.base_dir),
        case_store=store,
        since=args.since,
    )

    applied = 0
    if args.apply:
        for record in records:
            apply_recurrence(record=record, case_store=store)
            applied += 1

    payload = {
        "detected": len(records),
        "applied": applied,
        "dry_run": not args.apply,
        "records": [r.to_dict() for r in records],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
