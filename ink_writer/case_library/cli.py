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

from ink_writer.case_library.errors import (
    CaseLibraryError,
    CaseNotFoundError,
    CaseValidationError,
)
from ink_writer.case_library.index import CaseIndex
from ink_writer.case_library.ingest import ingest_case
from ink_writer.case_library.store import CaseStore

DEFAULT_LIBRARY_ROOT = Path("data/case_library")
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
