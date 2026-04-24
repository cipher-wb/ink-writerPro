"""US-010 tests — ``convert-from-editor-wisdom`` CLI subcommand."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from ink_writer.case_library.cli import main
from ink_writer.case_library.store import CaseStore


def _write_rules(path: Path, rules: list[dict]) -> None:
    path.write_text(json.dumps(rules, ensure_ascii=False), encoding="utf-8")


def test_convert_subcommand_creates_cases(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rules = [
        {
            "id": "EW-0001",
            "category": "opening",
            "rule": "r1",
            "why": "w1",
            "severity": "hard",
            "applies_to": ["opening_only"],
            "source_files": ["a.md"],
        },
        {
            "id": "EW-0002",
            "category": "pacing",
            "rule": "r2",
            "why": "w2",
            "severity": "soft",
            "applies_to": ["all_chapters"],
            "source_files": [],
        },
    ]
    rules_path = tmp_path / "rules.json"
    _write_rules(rules_path, rules)
    library_root = tmp_path / "lib"

    rc = main(
        [
            "--library-root",
            str(library_root),
            "convert-from-editor-wisdom",
            "--rules",
            str(rules_path),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "created=2" in out
    assert "skipped=0" in out
    assert "failed=0" in out
    assert "'hard': 1" in out
    assert "'soft': 1" in out

    store = CaseStore(library_root)
    assert len(store.list_ids()) == 2


def test_convert_idempotent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rules = [
        {
            "id": "EW-0001",
            "category": "opening",
            "rule": "r1",
            "why": "w1",
            "severity": "hard",
            "applies_to": ["opening_only"],
            "source_files": ["a.md"],
        },
    ]
    rules_path = tmp_path / "rules.json"
    _write_rules(rules_path, rules)
    library_root = tmp_path / "lib"

    rc = main(
        [
            "--library-root",
            str(library_root),
            "convert-from-editor-wisdom",
            "--rules",
            str(rules_path),
        ]
    )
    assert rc == 0
    capsys.readouterr()

    # Second run: sha256 dedup makes every rule skipped.
    rc = main(
        [
            "--library-root",
            str(library_root),
            "convert-from-editor-wisdom",
            "--rules",
            str(rules_path),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "created=0" in out
    assert "skipped=1" in out

    store = CaseStore(library_root)
    assert len(store.list_ids()) == 1


def test_convert_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rules = [
        {
            "id": "EW-0001",
            "category": "opening",
            "rule": "r1",
            "why": "w1",
            "severity": "hard",
            "applies_to": [],
            "source_files": [],
        },
    ]
    rules_path = tmp_path / "rules.json"
    _write_rules(rules_path, rules)
    library_root = tmp_path / "lib"

    rc = main(
        [
            "--library-root",
            str(library_root),
            "convert-from-editor-wisdom",
            "--rules",
            str(rules_path),
            "--dry-run",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "created=1" in out
    # Nothing actually written to store.
    store = CaseStore(library_root)
    assert store.list_ids() == []
