"""``ink case`` CLI — list / show / create / status / rebuild-index.

The CLI is the operator-facing entry point to ``CaseStore`` / ``ingest_case`` /
``CaseIndex``. ``main(argv)`` never raises: every failure is translated into a
non-zero return code with a stderr message, so shell callers can rely on exit
codes rather than exception stack traces.

Exit codes
----------
* ``0``   success
* ``2``   case not found / unknown command / argparse error / generic I/O
* ``3``   case validation failure (including unknown enum values)

Examples
--------
::

    python -m ink_writer.case_library.cli --library-root data/case_library list
    python -m ink_writer.case_library.cli --library-root data/case_library show CASE-2026-0001
    python -m ink_writer.case_library.cli --library-root data/case_library status active
    python -m ink_writer.case_library.cli --library-root data/case_library rebuild-index
    python -m ink_writer.case_library.cli --library-root data/case_library create \\
        --title "..." --raw-text "..." --domain writing_quality \\
        --layer downstream --severity P1 --tags reader_immersion \\
        --source-type editor_review --ingested-at 2026-04-24 \\
        --failure-description "..." --observable "..."
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml
from jsonschema import ValidationError

from ink_writer.case_library.approval import apply_batch_yaml
from ink_writer.case_library.errors import (
    CaseLibraryError,
    CaseNotFoundError,
    CaseValidationError,
)
from ink_writer.case_library.index import CaseIndex
from ink_writer.case_library.ingest import ingest_case
from ink_writer.case_library.meta_rule_cli import (
    dispatch as meta_rule_dispatch,
)
from ink_writer.case_library.meta_rule_cli import (
    register_subparsers as register_meta_rule_subparsers,
)
from ink_writer.case_library.rules_to_cases import convert_rules_to_cases
from ink_writer.case_library.store import CaseStore

DEFAULT_LIBRARY_ROOT = Path("data/case_library")
DEFAULT_RULES_PATH = Path("data/editor-wisdom/rules.json")
STATUS_CHOICES = ("pending", "active", "resolved", "regressed", "retired")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ink-case",
        description="Operator CLI for the ink-writer case library.",
    )
    parser.add_argument(
        "--library-root",
        type=Path,
        default=DEFAULT_LIBRARY_ROOT,
        help="Case library root (default: data/case_library)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Print every case_id line-by-line")

    show = sub.add_parser("show", help="Dump a single case as YAML")
    show.add_argument("case_id")

    status_cmd = sub.add_parser("status", help="Filter case_ids by status")
    status_cmd.add_argument("value", choices=list(STATUS_CHOICES))

    sub.add_parser("rebuild-index", help="DROP+CREATE sqlite inverted index")

    create = sub.add_parser("create", help="Ingest a new case (sha256 dedup)")
    create.add_argument("--title", required=True)
    create.add_argument("--raw-text", required=True)
    create.add_argument("--domain", required=True)
    create.add_argument("--layer", required=True, action="append")
    create.add_argument("--severity", required=True)
    create.add_argument("--tags", required=True, action="append")
    create.add_argument("--source-type", required=True)
    create.add_argument("--ingested-at", required=True)
    create.add_argument("--failure-description", required=True)
    create.add_argument("--observable", required=True, action="append")
    create.add_argument("--reviewer", default=None)
    create.add_argument("--ingested-from", default=None)
    create.add_argument("--scope-genre", action="append", default=None)
    create.add_argument("--scope-chapter", action="append", default=None)
    create.add_argument("--initial-status", default="active")

    convert = sub.add_parser(
        "convert-from-editor-wisdom",
        help="Convert editor-wisdom rules.json into cases (severity split + sha256 dedup)",
    )
    convert.add_argument(
        "--rules",
        type=Path,
        default=DEFAULT_RULES_PATH,
        help="Path to rules.json (default: data/editor-wisdom/rules.json)",
    )
    convert.add_argument(
        "--dry-run",
        action="store_true",
        help="Count would-create cases without writing to store",
    )

    approve = sub.add_parser(
        "approve",
        help="Apply a batch YAML of case approvals (approve/reject/defer)",
    )
    approve.add_argument(
        "--batch",
        type=Path,
        required=True,
        help="Path to approvals YAML (schema: case_approval_batch_schema.json)",
    )

    register_meta_rule_subparsers(sub)

    return parser


def _cmd_list(store: CaseStore) -> int:
    for case_id in store.list_ids():
        print(case_id)
    return 0


def _cmd_show(store: CaseStore, case_id: str) -> int:
    try:
        case = store.load(case_id)
    except CaseNotFoundError as exc:
        print(f"case not found: {exc}", file=sys.stderr)
        return 2
    text = yaml.safe_dump(
        case.to_dict(),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    sys.stdout.write(text)
    return 0


def _cmd_status(store: CaseStore, status: str) -> int:
    for case in store.iter_cases():
        if case.status.value == status:
            print(case.case_id)
    return 0


def _cmd_create(store: CaseStore, args: argparse.Namespace) -> int:
    try:
        result = ingest_case(
            store,
            title=args.title,
            raw_text=args.raw_text,
            domain=args.domain,
            layer=args.layer,
            severity=args.severity,
            tags=args.tags,
            source_type=args.source_type,
            ingested_at=args.ingested_at,
            failure_description=args.failure_description,
            observable=args.observable,
            reviewer=args.reviewer,
            ingested_from=args.ingested_from,
            scope_genre=args.scope_genre,
            scope_chapter=args.scope_chapter,
            initial_status=args.initial_status,
        )
    except CaseValidationError as exc:
        print(f"case validation failed: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        # Unknown enum value raised by StrEnum constructor (domain / layer /
        # severity / source_type / initial_status) — surface as validation.
        print(f"case validation failed: {exc}", file=sys.stderr)
        return 3

    if result.created:
        print(result.case_id)
    else:
        print(f"{result.case_id} (already existed; raw_text dedup)")
    return 0


def _cmd_rebuild_index(library_root: Path, store: CaseStore) -> int:
    index = CaseIndex(library_root / "index.sqlite")
    count = index.build(store)
    print(f"indexed={count}")
    return 0


def _cmd_convert_from_editor_wisdom(
    library_root: Path, rules_path: Path, dry_run: bool
) -> int:
    if not rules_path.exists():
        print(f"rules file not found: {rules_path}", file=sys.stderr)
        return 2
    report = convert_rules_to_cases(
        rules_path=rules_path,
        library_root=library_root,
        dry_run=dry_run,
    )
    print(
        f"created={report.created} skipped={report.skipped} "
        f"failed={report.failed} by_severity={report.by_severity}"
    )
    if report.failures:
        print("first failures (up to 10):", file=sys.stderr)
        for rule_id, err in report.failures[:10]:
            print(f"  {rule_id}: {err}", file=sys.stderr)
    return 0 if report.failed == 0 else 1


def _cmd_approve(library_root: Path, batch_path: Path) -> int:
    if not batch_path.exists():
        print(f"batch file not found: {batch_path}", file=sys.stderr)
        return 2
    try:
        report = apply_batch_yaml(yaml_path=batch_path, library_root=library_root)
    except ValidationError as exc:
        print(f"approval batch schema violation: {exc.message}", file=sys.stderr)
        return 3
    print(f"applied={report.applied} failed={report.failed}")
    if report.failures:
        print("first failures (up to 10):", file=sys.stderr)
        for case_id, err in report.failures[:10]:
            print(f"  {case_id}: {err}", file=sys.stderr)
    return 0 if report.failed == 0 else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Top-level entry point. Never raises — returns non-zero on error."""
    try:
        from runtime_compat import enable_windows_utf8_stdio

        enable_windows_utf8_stdio()
    except Exception:  # pragma: no cover — optional helper; Mac/Linux no-op
        pass

    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse exits on --help (0) or invalid args (2); both already
        # wrote their own message.
        code = exc.code if isinstance(exc.code, int) else 2
        return code

    try:
        store = CaseStore(args.library_root)
        if args.command == "list":
            return _cmd_list(store)
        if args.command == "show":
            return _cmd_show(store, args.case_id)
        if args.command == "status":
            return _cmd_status(store, args.value)
        if args.command == "create":
            return _cmd_create(store, args)
        if args.command == "rebuild-index":
            return _cmd_rebuild_index(args.library_root, store)
        if args.command == "convert-from-editor-wisdom":
            return _cmd_convert_from_editor_wisdom(
                args.library_root, args.rules, args.dry_run
            )
        if args.command == "approve":
            return _cmd_approve(args.library_root, args.batch)
        if args.command == "meta-rule":
            return meta_rule_dispatch(args)
        print(f"unknown command: {args.command}", file=sys.stderr)
        return 2
    except CaseLibraryError as exc:
        print(f"case library error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — CLI top-level guard
        print(f"unexpected error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
