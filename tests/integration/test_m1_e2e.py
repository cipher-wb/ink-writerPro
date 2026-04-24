"""M1 end-to-end integration (US-017).

Covers the preflight → auto-case → ink-case-list loop end-to-end.

Two scenarios:

1. **Preflight failure path**: ``reference_root`` is deliberately absent so
   ``check_reference_corpus_readable`` fails; ``--auto-create-infra-cases``
   must then materialise at least one ``domain=infra_health`` /
   ``severity=P0`` case that ``ink case list`` can see.
2. **Preflight success path**: a fully provisioned environment must return
   ``all_passed=True`` with ``rc==0`` and **must not** create any cases.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from ink_writer.case_library.cli import main as case_cli_main
from ink_writer.case_library.store import CaseStore
from ink_writer.preflight.cli import main as preflight_cli_main


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


def _preflight_argv(
    *,
    reference_root: Path,
    case_library_root: Path,
    rules_path: Path,
    auto_create: bool,
) -> list[str]:
    argv = [
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
    if auto_create:
        argv.append("--auto-create-infra-cases")
    return argv


def test_preflight_fail_creates_infra_case_visible_via_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Intentionally do NOT create reference_root → reference_corpus_readable
    # fails. We still provide an empty case library directory so the aggregator
    # can write the auto-created case into it.
    reference_root = tmp_path / "reference_corpus"  # absent by design
    case_library_root = tmp_path / "case_library"
    (case_library_root / "cases").mkdir(parents=True, exist_ok=True)
    rules_path = tmp_path / "editor_wisdom" / "rules.json"
    _make_rules_file(rules_path)

    argv = _preflight_argv(
        reference_root=reference_root,
        case_library_root=case_library_root,
        rules_path=rules_path,
        auto_create=True,
    )

    rc = preflight_cli_main(argv)

    preflight_out = capsys.readouterr().out
    assert rc != 0, preflight_out
    assert "all_passed=False" in preflight_out, preflight_out
    assert any(
        line.startswith("[FAIL]") and "reference_corpus_readable" in line
        for line in preflight_out.splitlines()
    ), preflight_out

    # ``ink case list`` must see at least one case_id now.
    rc_list = case_cli_main(["--library-root", str(case_library_root), "list"])
    assert rc_list == 0
    list_out_lines = [
        line for line in capsys.readouterr().out.splitlines() if line.strip()
    ]
    assert list_out_lines, "expected at least one case listed by ink case list"

    # Every newly-auto-created case must be infra_health / P0.
    store = CaseStore(case_library_root)
    for case_id in list_out_lines:
        case = store.load(case_id)
        assert case.domain.value == "infra_health", case_id
        assert case.severity.value == "P0", case_id


def test_preflight_pass_creates_no_new_cases(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reference_root = tmp_path / "reference_corpus"
    case_library_root = tmp_path / "case_library"
    rules_path = tmp_path / "editor_wisdom" / "rules.json"

    _make_reference_corpus(reference_root, n=3)
    (case_library_root / "cases").mkdir(parents=True, exist_ok=True)
    _make_rules_file(rules_path)

    argv = _preflight_argv(
        reference_root=reference_root,
        case_library_root=case_library_root,
        rules_path=rules_path,
        auto_create=True,
    )

    rc = preflight_cli_main(argv)

    preflight_out = capsys.readouterr().out
    assert rc == 0, preflight_out
    assert preflight_out.splitlines()[0] == "all_passed=True", preflight_out

    rc_list = case_cli_main(["--library-root", str(case_library_root), "list"])
    assert rc_list == 0
    list_out = capsys.readouterr().out.strip()
    assert list_out == "", f"expected empty case list, got: {list_out!r}"
