#!/usr/bin/env python3
"""US-LR-011: build live-review vector index over CASE-LR-*.yaml cases.

Usage:
    python3 scripts/live-review/build_vector_index.py \
        --cases-dir data/case_library/cases/live_review \
        --out-dir data/live-review/vector_index
"""
from __future__ import annotations

# US-LR-011: ensure Windows stdio is UTF-8 wrapped when launched directly.
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
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ink_writer.live_review._vector_index import build_index  # noqa: E402

DEFAULT_CASES_DIR = _REPO_ROOT / "data" / "case_library" / "cases" / "live_review"
DEFAULT_OUT_DIR = _REPO_ROOT / "data" / "live-review" / "vector_index"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases-dir",
        type=Path,
        default=DEFAULT_CASES_DIR,
        help=f"Cases directory (default: {DEFAULT_CASES_DIR})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Output index directory (default: {DEFAULT_OUT_DIR})",
    )
    args = parser.parse_args()

    if not args.cases_dir.is_dir():
        print(f"[build_vector_index] cases-dir not found: {args.cases_dir}", file=sys.stderr)
        return 2

    try:
        stats = build_index(args.cases_dir, args.out_dir)
    except ValueError as e:
        print(f"[build_vector_index] {e}", file=sys.stderr)
        return 1

    print(
        f"OK indexed {stats['cases_indexed']} cases (dim={stats['embedding_dim']}) "
        f"→ {args.out_dir}/"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
