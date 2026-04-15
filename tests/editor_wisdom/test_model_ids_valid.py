"""Smoke test: all model IDs in editor-wisdom Python files must be valid Anthropic identifiers."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SCAN_DIRS = [
    REPO_ROOT / "scripts" / "editor-wisdom",
    REPO_ROOT / "ink_writer" / "editor_wisdom",
]

VALID_MODEL_RE = re.compile(r"^claude-(haiku|sonnet|opus)-\d(-\d)?(-\d{8})?$")

FORBIDDEN_SUBSTRINGS = ["20241022", "20250514"]

MODEL_PATTERN = re.compile(r"""["']claude-(haiku|sonnet|opus)-[^"']+["']""")


def _collect_python_files() -> list[Path]:
    files = []
    for d in SCAN_DIRS:
        if d.exists():
            files.extend(d.glob("**/*.py"))
    return sorted(files)


def _extract_model_ids(source: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(source.splitlines(), 1):
        for m in MODEL_PATTERN.finditer(line):
            model_id = m.group(0).strip("\"'")
            hits.append((i, model_id))
    return hits


@pytest.fixture(scope="module")
def all_model_ids() -> list[tuple[Path, int, str]]:
    results = []
    for f in _collect_python_files():
        src = f.read_text(encoding="utf-8")
        for lineno, mid in _extract_model_ids(src):
            results.append((f, lineno, mid))
    return results


def test_python_files_exist():
    files = _collect_python_files()
    assert len(files) > 0, "No Python files found to scan"


def test_all_model_ids_match_valid_pattern(all_model_ids):
    invalid = [
        (f.relative_to(REPO_ROOT), lineno, mid)
        for f, lineno, mid in all_model_ids
        if not VALID_MODEL_RE.match(mid)
    ]
    assert not invalid, f"Invalid model IDs found: {invalid}"


def test_no_forbidden_model_substrings(all_model_ids):
    forbidden_hits = []
    for f, lineno, mid in all_model_ids:
        for sub in FORBIDDEN_SUBSTRINGS:
            if sub in mid:
                forbidden_hits.append((f.relative_to(REPO_ROOT), lineno, mid, sub))
    assert not forbidden_hits, f"Forbidden model substrings found: {forbidden_hits}"


def test_at_least_one_model_id_found(all_model_ids):
    assert len(all_model_ids) > 0, "Expected to find at least one model ID in scanned files"
