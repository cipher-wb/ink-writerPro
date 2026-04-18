"""FIX-11 migration: rewrite ``data_modules.*`` imports to ``ink_writer.core.<bucket>.*``.

Direction A (per tasks/design-fix-11-python-pkg-merge.md §3) was recommended: merge
``ink-writer/scripts/data_modules/`` into ``ink_writer/core/{state,index,context,cli,extract,infra}/``.

This script is a *mechanical rewriter* only — it does NOT move files on disk. File moves
are handled separately via ``git mv`` per the design doc. This script:

1. Scans ``*.py``, ``*.md``, ``SKILL.md``, ``pytest.ini`` under the repo root.
2. Rewrites ``from data_modules.X``, ``from scripts.data_modules.X``, ``import data_modules.X``
   to the new ``ink_writer.core.<bucket>.X`` paths.
3. Comments out ``sys.path.insert(...)`` lines that inject ``scripts`` / ``scripts/data_modules``.
4. Updates ``pytest.ini`` ``testpaths`` and ``pythonpath`` lines.

Default mode is **dry-run**: writes a unified diff to ``/tmp/fix11-diff.txt``. Passing
``--apply`` also writes the changes back to disk.

Usage:
    python -m scripts.migration.fix11_merge_packages [--root PATH] [--apply] [--diff-out PATH]
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path
from typing import Iterable

BUCKET_MAP: dict[str, str] = {
    # state bucket
    "state_manager": "state",
    "sql_state_manager": "state",
    "snapshot_manager": "state",
    "state_validator": "state",
    "migrate_state_to_sqlite": "state",
    "schemas": "state",
    # index bucket
    "index_manager": "index",
    "index_chapter_mixin": "index",
    "index_debt_mixin": "index",
    "index_entity_mixin": "index",
    "index_observability_mixin": "index",
    "index_reading_mixin": "index",
    "index_types": "index",
    # context bucket
    "context_manager": "context",
    "context_ranker": "context",
    "context_weights": "context",
    "memory_compressor": "context",
    "query_router": "context",
    "writing_guidance_builder": "context",
    "rag_adapter": "context",
    # cli bucket
    "ink": "cli",
    "cli_args": "cli",
    "cli_output": "cli",
    "checkpoint_utils": "cli",
    # extract bucket
    "entity_linker": "extract",
    "genre_aliases": "extract",
    "genre_profile_builder": "extract",
    "style_anchor": "extract",
    "style_sampler": "extract",
    "golden_three": "extract",
    "anti_ai_lint": "extract",
    # infra bucket
    "api_client": "infra",
    "observability": "infra",
    "config": "infra",
}

EXCLUDED_DIR_NAMES: set[str] = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "venv",
    "archive",
    # don't touch the legacy source tree itself — those files get `git mv`'d wholesale
    "data_modules",
}

TARGET_SUFFIXES: tuple[str, ...] = (".py", ".md")
TARGET_FILENAMES: tuple[str, ...] = ("pytest.ini", "SKILL.md")

# --- regexes ---------------------------------------------------------------

# from data_modules.<mod> import ...
RE_FROM_DM = re.compile(r"^(?P<indent>\s*)from\s+(?:scripts\.)?data_modules\.(?P<mod>\w+)(?P<rest>\s+import\s+.+)$")
# from data_modules import <mod1>, <mod2> ...
RE_FROM_DM_FLAT = re.compile(r"^(?P<indent>\s*)from\s+(?:scripts\.)?data_modules\s+import\s+(?P<names>[^#\n]+?)(?P<tail>\s*(?:#.*)?)$")
# import data_modules.<mod> [as <alias>]
RE_IMPORT_DM_DOTTED = re.compile(r"^(?P<indent>\s*)import\s+(?:scripts\.)?data_modules\.(?P<mod>\w+)(?P<alias>\s+as\s+\w+)?\s*$")
# sys.path.insert referencing scripts dir (wraps data_modules access)
RE_SYS_PATH = re.compile(r"sys\.path\.insert\s*\([^)]*?(?:data_modules|/scripts['\"]|scripts\b)[^)]*?\)", re.IGNORECASE)

# pytest.ini tokens we rewrite
PYTHONPATH_DROP_TOKENS = ("ink-writer/scripts",)
TESTPATHS_SUBSTITUTIONS = (
    ("ink-writer/scripts/data_modules/tests", "ink_writer/core/tests"),
)


def _bucket_for(module: str) -> str | None:
    return BUCKET_MAP.get(module)


def _rewrite_py_line(line: str) -> str:
    """Rewrite a single Python source line. Returns the (possibly) new line (no trailing newline)."""
    stripped_newline = line.rstrip("\n")

    m = RE_FROM_DM.match(stripped_newline)
    if m:
        bucket = _bucket_for(m.group("mod"))
        if bucket is None:
            return line
        new = f"{m.group('indent')}from ink_writer.core.{bucket}.{m.group('mod')}{m.group('rest')}"
        return new + ("\n" if line.endswith("\n") else "")

    m = RE_IMPORT_DM_DOTTED.match(stripped_newline)
    if m:
        bucket = _bucket_for(m.group("mod"))
        if bucket is None:
            return line
        alias = m.group("alias") or ""
        new = f"{m.group('indent')}import ink_writer.core.{bucket}.{m.group('mod')}{alias}"
        return new + ("\n" if line.endswith("\n") else "")

    m = RE_FROM_DM_FLAT.match(stripped_newline)
    if m:
        names = [n.strip() for n in m.group("names").split(",") if n.strip()]
        # only rewrite if every name is a known module; otherwise leave (safer).
        buckets = {n: _bucket_for(n) for n in names}
        if all(buckets.values()):
            indent = m.group("indent")
            tail = m.group("tail") or ""
            lines = [f"{indent}from ink_writer.core.{buckets[n]} import {n}" for n in names]
            new = "\n".join(lines) + tail
            return new + ("\n" if line.endswith("\n") else "")

    # sys.path.insert(...) → comment it out (keeps git blame readable)
    if RE_SYS_PATH.search(stripped_newline) and not stripped_newline.lstrip().startswith("#"):
        indent_match = re.match(r"^(\s*)", stripped_newline)
        indent = indent_match.group(1) if indent_match else ""
        body = stripped_newline[len(indent):]
        new = f"{indent}# [FIX-11] removed: {body}"
        return new + ("\n" if line.endswith("\n") else "")

    return line


def rewrite_python(source: str) -> str:
    """Rewrite a Python source blob. Line-based; idempotent."""
    out_lines = []
    for raw in source.splitlines(keepends=True):
        out_lines.append(_rewrite_py_line(raw))
    return "".join(out_lines)


def rewrite_markdown(source: str) -> str:
    """Rewrite md/SKILL.md content. Conservative — only touches identifiable import/path snippets."""
    out = source

    def _sub_from(match: re.Match[str]) -> str:
        mod = match.group("mod")
        bucket = _bucket_for(mod)
        if bucket is None:
            return match.group(0)
        rest = match.group("rest")
        return f"from ink_writer.core.{bucket}.{mod}{rest}"

    out = re.sub(
        r"from\s+(?:scripts\.)?data_modules\.(?P<mod>\w+)(?P<rest>\s+import\s+[^\n`]+)",
        _sub_from,
        out,
    )
    # shell-style sys.path.insert examples in docs → drop-in FIX-11 notice
    out = re.sub(
        r"sys\.path\.insert\([^)]*?(?:data_modules|/scripts['\"]|scripts\b)[^)]*?\)",
        "# [FIX-11] sys.path.insert no longer required — ink_writer is importable",
        out,
        flags=re.IGNORECASE,
    )
    return out


def rewrite_pytest_ini(source: str) -> str:
    """Rewrite pytest.ini testpaths + pythonpath entries."""
    out = source
    for old, new in TESTPATHS_SUBSTITUTIONS:
        out = out.replace(old, new)

    def _fix_pythonpath(match: re.Match[str]) -> str:
        prefix = match.group(1)
        tokens = match.group(2).split()
        kept = [t for t in tokens if t not in PYTHONPATH_DROP_TOKENS]
        return f"{prefix}{' '.join(kept)}"

    out = re.sub(r"^(pythonpath\s*=\s*)(.+)$", _fix_pythonpath, out, flags=re.MULTILINE)
    return out


def rewrite_file(path: Path, source: str) -> str:
    """Dispatch to the right rewriter based on file name/suffix."""
    name = path.name
    if name == "pytest.ini":
        return rewrite_pytest_ini(source)
    if name.endswith(".py"):
        return rewrite_python(source)
    if name.endswith(".md"):  # covers SKILL.md too
        return rewrite_markdown(source)
    return source


def iter_target_files(root: Path) -> Iterable[Path]:
    """Walk ``root`` yielding files the migration should inspect."""
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        name = path.name
        if name in TARGET_FILENAMES or name.endswith(TARGET_SUFFIXES):
            yield path


def compute_diff(root: Path) -> tuple[list[str], list[tuple[Path, str, str]]]:
    """Return (unified_diff_lines, list_of_changes) for all target files under root."""
    diff_lines: list[str] = []
    changes: list[tuple[Path, str, str]] = []
    for path in iter_target_files(root):
        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rewritten = rewrite_file(path, original)
        if rewritten == original:
            continue
        rel = path.relative_to(root)
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            rewritten.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
        diff_lines.extend(diff)
        changes.append((path, original, rewritten))
    return diff_lines, changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FIX-11 import rewriter (data_modules → ink_writer.core)")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repo root to scan")
    parser.add_argument("--apply", action="store_true", help="Actually rewrite files (default: dry-run)")
    parser.add_argument("--diff-out", type=Path, default=Path("/tmp/fix11-diff.txt"), help="Where to write the unified diff")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    diff_lines, changes = compute_diff(root)

    args.diff_out.parent.mkdir(parents=True, exist_ok=True)
    args.diff_out.write_text("".join(diff_lines), encoding="utf-8")

    print(f"[fix11] scanned {sum(1 for _ in iter_target_files(root))} files")
    print(f"[fix11] {len(changes)} files would change")
    print(f"[fix11] diff → {args.diff_out}")

    if args.apply:
        for path, _original, rewritten in changes:
            path.write_text(rewritten, encoding="utf-8")
        print(f"[fix11] APPLIED changes to {len(changes)} files")
    else:
        print("[fix11] dry-run only; re-run with --apply to write changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
