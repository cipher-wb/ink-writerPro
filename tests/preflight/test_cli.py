"""CLI smoke tests for ``ink_writer.preflight.cli`` (US-016).

Two scenarios:

1. All checks pass in minimal mode (in-memory Qdrant, no API keys required):
   stdout starts with ``all_passed=True`` and rc is 0.
2. Missing ``rules.json`` forces ``editor_wisdom_index_loadable`` to fail:
   stdout contains ``all_passed=False`` and rc is non-zero.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from ink_writer.preflight.cli import main


def _make_reference_corpus(root: Path, n: int = 3) -> None:
    chapters = root / "book" / "chapters"
    chapters.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (chapters / f"ch{i:03d}.txt").write_text("x", encoding="utf-8")


def _make_rules_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([{"id": "EW-0001"}, {"id": "EW-0002"}]),
        encoding="utf-8",
    )


def _common_args(tmp_path: Path, *, with_rules: bool) -> list[str]:
    reference_root = tmp_path / "reference_corpus"
    case_library_root = tmp_path / "case_library"
    rules_path = tmp_path / "editor_wisdom" / "rules.json"

    _make_reference_corpus(reference_root, n=3)
    (case_library_root / "cases").mkdir(parents=True, exist_ok=True)
    if with_rules:
        _make_rules_file(rules_path)

    return [
        "--reference-root",
        str(reference_root),
        "--case-library-root",
        str(case_library_root),
        "--editor-wisdom-rules",
        str(rules_path),
        "--qdrant-in-memory",
        "--no-require-embedding-key",
        "--no-require-rerank-key",
        "--min-corpus-files",
        "1",
    ]


def test_cli_runs_in_minimal_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = _common_args(tmp_path, with_rules=True)

    rc = main(argv)

    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.splitlines()[0] == "all_passed=True"
    # Every listed check should be OK.
    for line in captured.out.splitlines()[1:]:
        assert line.startswith("[OK ]"), f"unexpected non-OK line: {line}"


def test_cli_failed_returns_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = _common_args(tmp_path, with_rules=False)

    rc = main(argv)

    captured = capsys.readouterr()
    assert rc != 0
    assert "all_passed=False" in captured.out
    # The missing rules file must surface as a [FAIL] line for editor_wisdom.
    assert any(
        line.startswith("[FAIL]") and "editor_wisdom_index_loadable" in line
        for line in captured.out.splitlines()
    ), captured.out
