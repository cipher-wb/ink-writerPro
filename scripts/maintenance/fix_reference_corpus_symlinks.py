#!/usr/bin/env python3
"""Fix broken symlinks under ``benchmark/reference_corpus`` (US-001).

Background
----------
Historically ``benchmark/reference_corpus/<book>/chapters/*.txt`` were created as
absolute symlinks into ``/Users/cipher/AI/ink/...`` (i.e. without the ``小说``
directory segment the repo now lives under). The corpus moved but the symlinks
were never relinked, so every entry became a broken link and reference corpus
loading silently degraded — see ``CASE-2026-0000`` (the zero-case of the case
library).

This script walks ``reference_root`` and for every ``*.txt`` file decides one
of three outcomes, idempotently:

1. **broken symlink** — delete the link, find the matching file under
   ``corpus_root`` (by preserving the ``<book>/chapters/<name>.txt`` suffix),
   copy the bytes over. If the source is missing, record the path in the
   ``missing_paths`` list of the report without failing the whole run.
2. **real file (already fixed)** — skip, count in ``skipped``.
3. **source missing** — leave the broken link in place, report it.

All ``open()`` / ``Path.read_text()`` calls use ``encoding="utf-8"`` per the
project's Windows compat guideline.

CLI
---
::

    python scripts/maintenance/fix_reference_corpus_symlinks.py \
        --reference-root benchmark/reference_corpus \
        --corpus-root    benchmark/corpus

Exit codes
----------
``0`` always (even if some sources are missing — the report tells the operator
which ones to chase down). Unexpected exceptions bubble up as Python errors,
which is fine for an ops script.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FixReport:
    """Outcome of one :func:`fix_reference_corpus_symlinks` run."""

    fixed: int = 0
    skipped: int = 0
    missing_source: int = 0
    missing_paths: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"fixed={self.fixed} skipped={self.skipped} "
            f"missing_source={self.missing_source}"
        )


def _iter_txt_files(reference_root: Path) -> list[Path]:
    """Return every ``*.txt`` under ``reference_root`` (symlinks included)."""

    return sorted(p for p in reference_root.rglob("*.txt"))


def _resolve_source_for(entry: Path, reference_root: Path, corpus_root: Path) -> Path:
    """Map ``reference_root/<book>/chapters/ch001.txt`` → ``corpus_root/<same>``."""

    rel = entry.relative_to(reference_root)
    return corpus_root / rel


def _is_broken_symlink(entry: Path) -> bool:
    # ``Path.exists()`` on a symlink follows the link — False means target
    # missing. Combined with ``is_symlink()`` this detects dangling links.
    return entry.is_symlink() and not entry.exists()


def fix_reference_corpus_symlinks(
    reference_root: Path,
    corpus_root: Path,
) -> FixReport:
    """Replace broken symlinks under *reference_root* with hard copies of the
    matching files under *corpus_root*. Idempotent: already-real files are
    skipped, missing sources are reported but do not abort the run.
    """

    reference_root = Path(reference_root)
    corpus_root = Path(corpus_root)
    report = FixReport()

    if not reference_root.exists():
        return report

    for entry in _iter_txt_files(reference_root):
        if _is_broken_symlink(entry):
            source = _resolve_source_for(entry, reference_root, corpus_root)
            if not source.exists() or not source.is_file():
                report.missing_source += 1
                report.missing_paths.append(str(entry))
                continue
            # Remove the dangling link (unlink also handles symlinks), then
            # copy the real bytes. Preserve mtime for corpus provenance.
            entry.unlink()
            entry.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, entry)
            report.fixed += 1
        elif entry.is_file() and not entry.is_symlink():
            report.skipped += 1
        elif entry.is_symlink() and entry.exists():
            # Healthy symlink pointing into a reachable source — leave alone.
            report.skipped += 1
        else:
            # Neither a file nor a symlink (shouldn't happen under rglob *.txt)
            # — treat as missing to surface in the report.
            report.missing_source += 1
            report.missing_paths.append(str(entry))

    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replace broken symlinks under benchmark/reference_corpus with "
            "hard copies from benchmark/corpus. See CASE-2026-0000."
        ),
    )
    parser.add_argument(
        "--reference-root",
        type=Path,
        default=Path("benchmark/reference_corpus"),
        help="Reference corpus root (default: benchmark/reference_corpus)",
    )
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=Path("benchmark/corpus"),
        help="Source corpus root (default: benchmark/corpus)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        from runtime_compat import enable_windows_utf8_stdio

        enable_windows_utf8_stdio()
    except Exception:  # pragma: no cover — optional helper; Mac/Linux no-op
        pass

    args = _build_parser().parse_args(argv)
    report = fix_reference_corpus_symlinks(args.reference_root, args.corpus_root)

    print(report.summary())
    if report.missing_paths:
        print("missing_paths:")
        for path in report.missing_paths:
            print(f"  - {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
