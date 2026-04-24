"""Tests for the preflight aggregator (US-015).

Three scenarios cover the contract:

1. All checks pass → clean report, no exception.
2. One check fails with auto_create_infra_cases=True → infra_health case
   written to the case library, raw_text_hash dedup prevents duplicates on
   repeated runs.
3. One check fails with raise_on_fail=False → returns report carrying the
   failed check; caller decides what to do next.
"""
from __future__ import annotations

import json
from pathlib import Path

from ink_writer.case_library.store import CaseStore
from ink_writer.preflight.checker import (
    PreflightConfig,
    PreflightReport,
    run_preflight,
)


def _make_reference_corpus(root: Path, n: int = 3) -> None:
    chapters = root / "book" / "chapters"
    chapters.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (chapters / f"ch{i:03d}.txt").write_text("x", encoding="utf-8")


def _make_case_library_root(root: Path) -> None:
    (root / "cases").mkdir(parents=True, exist_ok=True)


def _make_rules_file(path: Path, n: int = 2) -> None:
    path.write_text(
        json.dumps([{"id": f"EW-{i:04d}"} for i in range(n)]), encoding="utf-8"
    )


def _config(
    tmp_path: Path,
    *,
    rules_exists: bool = True,
    min_corpus_files: int = 1,
) -> PreflightConfig:
    reference_root = tmp_path / "reference_corpus"
    case_library_root = tmp_path / "case_library"
    rules_path = tmp_path / "editor_wisdom" / "rules.json"

    _make_reference_corpus(reference_root, n=3)
    _make_case_library_root(case_library_root)
    if rules_exists:
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        _make_rules_file(rules_path, n=2)

    return PreflightConfig(
        reference_root=reference_root,
        case_library_root=case_library_root,
        editor_wisdom_rules_path=rules_path,
        qdrant_in_memory=True,
        min_corpus_files=min_corpus_files,
    )


def test_all_pass_returns_clean_report(tmp_path: Path) -> None:
    config = _config(tmp_path, rules_exists=True)

    report = run_preflight(config)

    assert isinstance(report, PreflightReport)
    assert report.all_passed is True
    assert report.failed == []
    # Order: reference / case_library / editor_wisdom / qdrant (no key flags here).
    assert [r.name for r in report.results] == [
        "reference_corpus_readable",
        "case_library_loadable",
        "editor_wisdom_index_loadable",
        "qdrant_connection",
    ]


def test_failed_check_creates_infra_case(tmp_path: Path) -> None:
    # Missing rules file → editor_wisdom_index_loadable fails.
    config = _config(tmp_path, rules_exists=False)

    report = run_preflight(config, auto_create_infra_cases=True)

    assert report.all_passed is False
    failed_names = [r.name for r in report.failed]
    assert "editor_wisdom_index_loadable" in failed_names

    store = CaseStore(config.case_library_root)
    cases = list(store.iter_cases())
    assert len(cases) >= 1
    editor_wisdom_cases = [
        c
        for c in cases
        if c.domain.value == "infra_health"
        and "editor_wisdom_index_loadable" in c.title
    ]
    assert len(editor_wisdom_cases) == 1
    only = editor_wisdom_cases[0]
    assert only.severity.value == "P0"
    assert [layer.value for layer in only.layer] == ["infra_health"]
    assert only.source.type.value == "infra_check"

    # Re-run: sha256 dedup means no additional cases are written.
    before = store.list_ids()
    run_preflight(config, auto_create_infra_cases=True)
    after = CaseStore(config.case_library_root).list_ids()
    assert after == before


def test_failed_check_without_raise_returns_failed_report(tmp_path: Path) -> None:
    # Missing rules file produces a failure, but raise_on_fail=False (default).
    config = _config(tmp_path, rules_exists=False)

    report = run_preflight(config)

    assert report.all_passed is False
    assert any(
        r.name == "editor_wisdom_index_loadable" and r.passed is False
        for r in report.results
    )
    # No case library mutations when auto_create_infra_cases is off.
    assert CaseStore(config.case_library_root).list_ids() == []
