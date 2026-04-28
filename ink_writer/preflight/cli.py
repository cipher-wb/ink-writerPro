"""``ink preflight`` CLI — Step 0 gate for ``ink-write`` (M1+).

Wraps :func:`ink_writer.preflight.checker.run_preflight` in an argparse entry
point. Operators can run it directly:

    python -m ink_writer.preflight.cli --auto-create-infra-cases --raise-on-fail

Output format
-------------
First line::

    all_passed=<True|False>

Followed by one line per check::

    [OK ] <name>: <detail>
    [FAIL] <name>: <detail>

Exit codes
----------
* ``0``   every check passed
* ``1``   at least one check failed
* ``2``   top-level unexpected error

``main`` NEVER raises — every failure is translated into a non-zero return
code with a stderr message.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from ink_writer.preflight.checker import (
    PreflightConfig,
    PreflightReport,
    run_preflight,
)
from ink_writer.preflight.errors import PreflightError
from ink_writer.qdrant.client import QdrantConfig

DEFAULT_REFERENCE_ROOT = Path("benchmark/reference_corpus")
DEFAULT_CASE_LIBRARY_ROOT = Path("data/case_library")
DEFAULT_EDITOR_WISDOM_RULES = Path("data/editor-wisdom/rules.json")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ink-preflight",
        description="Ink-write Step 0 preflight health check (M1+).",
    )
    parser.add_argument(
        "--reference-root", type=Path, default=DEFAULT_REFERENCE_ROOT
    )
    parser.add_argument(
        "--case-library-root", type=Path, default=DEFAULT_CASE_LIBRARY_ROOT
    )
    parser.add_argument(
        "--editor-wisdom-rules", type=Path, default=DEFAULT_EDITOR_WISDOM_RULES
    )
    parser.add_argument(
        "--qdrant-in-memory",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use in-memory Qdrant (default). Use --no-qdrant-in-memory for real server.",
    )
    parser.add_argument("--qdrant-host", default="127.0.0.1")
    parser.add_argument("--qdrant-port", type=int, default=6333)
    parser.add_argument(
        "--require-embedding-key",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--require-rerank-key",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--min-corpus-files", type=int, default=100)
    parser.add_argument("--auto-create-infra-cases", action="store_true")
    parser.add_argument("--raise-on-fail", action="store_true")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root directory. When set, all relative paths "
        "(reference-root, case-library-root, editor-wisdom-rules) "
        "are resolved against this directory.",
    )
    return parser


def _format_report(report: PreflightReport) -> str:
    lines = [f"all_passed={report.all_passed}"]
    for r in report.results:
        tag = "[OK ]" if r.passed else "[FAIL]"
        lines.append(f"{tag} {r.name}: {r.detail}")
    return "\n".join(lines) + "\n"


def _resolve(path: Path, project_root: Path | None) -> Path:
    """Resolve *path* to absolute if *project_root* is given and *path* is relative."""
    if project_root is not None and not path.is_absolute():
        return (project_root / path).resolve()
    return path


def _build_config(args: argparse.Namespace) -> PreflightConfig:
    qdrant_cfg = (
        None
        if args.qdrant_in_memory
        else QdrantConfig(host=args.qdrant_host, port=args.qdrant_port)
    )
    pr = args.project_root
    return PreflightConfig(
        reference_root=_resolve(args.reference_root, pr),
        case_library_root=_resolve(args.case_library_root, pr),
        editor_wisdom_rules_path=_resolve(args.editor_wisdom_rules, pr),
        qdrant_config=qdrant_cfg,
        qdrant_in_memory=args.qdrant_in_memory,
        require_embedding_key=args.require_embedding_key,
        require_rerank_key=args.require_rerank_key,
        min_corpus_files=args.min_corpus_files,
        project_root=str(pr) if pr is not None else None,
    )


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
        # argparse exits on --help (0) or invalid args (2); the message was
        # already written to stderr.
        return exc.code if isinstance(exc.code, int) else 2

    try:
        config = _build_config(args)
        # Always drive run_preflight with raise_on_fail=False so we can print
        # the full per-check report before translating to an exit code.
        report = run_preflight(
            config,
            raise_on_fail=False,
            auto_create_infra_cases=args.auto_create_infra_cases,
        )
    except Exception as err:  # noqa: BLE001 — CLI top-level guard
        print(f"preflight unexpected error: {err}", file=sys.stderr)
        return 2

    sys.stdout.write(_format_report(report))

    # --- debug invariant: context_required_files (dormant until Context Contract is formalized) ---
    # Per spec §13 Q2, the canonical list of "required skill files" the context-agent must
    # read is not yet machine-readable. When that lands, populate _required and _read_files
    # from the contract; until then this hook is a no-op (invariant returns None on empty
    # required list, per its fail-soft policy).
    try:
        from pathlib import Path as _Path
        from ink_writer.debug.collector import Collector as _DebugCollector
        from ink_writer.debug.config import load_config as _load_debug_cfg
        from ink_writer.debug.invariants.context_required_files import check as _check_ctx

        _project_root = _Path.cwd()
        _dbg_cfg = _load_debug_cfg(
            global_yaml_path=_Path("config/debug.yaml"),
            project_root=_project_root,
        )
        if _dbg_cfg.master_enabled and _dbg_cfg.layers.layer_c_invariants \
                and _dbg_cfg.invariants.get("context_required_files", {}).get("enabled", True):
            _required: list[str] = []      # TODO: populate from formalized Context Contract
            _read_files: list[str] = []    # TODO: populate from preflight or context-agent telemetry
            _inc = _check_ctx(
                required=_required,
                actually_read=_read_files,
                run_id="preflight",
                chapter=None,
            )
            if _inc is not None:
                _DebugCollector(_dbg_cfg).record(_inc)
    except Exception:
        pass  # Debug must never break preflight.

    if args.raise_on_fail and not report.all_passed:
        failed_names = [r.name for r in report.failed]
        # Mirror PreflightError's message so ops greps see the same phrase
        # whether we raised or not.
        err = PreflightError(
            failed_names, f"preflight failed: {failed_names}"
        )
        print(str(err), file=sys.stderr)

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
