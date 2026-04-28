# ink_writer/core/auto/blueprint_scanner.py
"""Scan CWD top-level for a usable blueprint .md file.

Used by ink-auto S0a branch to find a user-supplied blueprint.
"""
from __future__ import annotations

from pathlib import Path

BLACKLIST = {
    "README.MD",
    "CLAUDE.MD",
    "TODO.MD",
    "CHANGELOG.MD",
    "LICENSE.MD",
    "CONTRIBUTING.MD",
    "AGENTS.MD",
    "GEMINI.MD",
}


def _is_blacklisted(name: str) -> bool:
    upper = name.upper()
    if upper in {b.upper() for b in BLACKLIST}:
        return True
    if upper.endswith(".DRAFT.MD"):
        return True
    return False


def find_blueprint(cwd: Path | str) -> Path | None:
    cwd = Path(cwd)
    if not cwd.is_dir():
        return None
    candidates: list[Path] = []
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
