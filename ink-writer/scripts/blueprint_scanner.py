#!/usr/bin/env python3
"""Scan CWD top-level for a usable blueprint .md file.

Plugin-internal copy of ink_writer.core.auto.blueprint_scanner so it runs
without depending on the outer Python package. Keep in lockstep with:
  ink_writer/core/auto/blueprint_scanner.py
"""
from __future__ import annotations

from pathlib import Path

BLACKLIST = {
    "README.md",
    "CLAUDE.md",
    "TODO.md",
    "CHANGELOG.md",
    "LICENSE.md",
    "CONTRIBUTING.md",
    "AGENTS.md",
    "GEMINI.md",
}


def _is_blacklisted(name):
    upper = name.upper()
    if upper in {b.upper() for b in BLACKLIST}:
        return True
    if upper.endswith(".DRAFT.MD"):
        return True
    return False


def find_blueprint(cwd):
    cwd = Path(cwd)
    if not cwd.is_dir():
        return None
    candidates = []
    for entry in cwd.iterdir():
        if not entry.is_file():
            continue
        if not entry.name.lower().endswith(".md"):
            continue
        if _is_blacklisted(entry.name):
            continue
        candidates.append(entry)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_size)


if __name__ == "__main__":
    import argparse
    import sys

    try:
        from runtime_compat import enable_windows_utf8_stdio

        enable_windows_utf8_stdio()
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Scan a directory for a usable blueprint .md")
    parser.add_argument("--cwd", required=True, help="Directory to scan")
    args = parser.parse_args()

    result = find_blueprint(args.cwd)
    if result:
        print(str(result))
    sys.exit(0)
