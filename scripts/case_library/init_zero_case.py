#!/usr/bin/env python3
"""Register CASE-2026-0000 — the zero-case of the case library (US-009).

Background
----------
Before the case library existed we still had one production incident worth
learning from: the ``benchmark/reference_corpus/*/chapters/*.txt`` symlinks
silently went dangling after the repo moved (US-001 fixed the data). Making
that incident the first row in the library is how this whole program eats
its own dog food — every future infra_health issue follows the same shape.

The zero-case is fixed:

* ``case_id = CASE-2026-0000`` (reserved — the auto-allocator in
  ``ingest_case`` starts at ``0001`` so there is no collision)
* ``status = active`` (still learning from it via preflight)
* ``severity = P0`` / ``domain = infra_health`` / ``layer = [infra_health]``
* Bound to ``preflight-reference-corpus-readable`` (the checker lands in
  US-014/US-015; pointing at it now is a forward-compatible hook)

CLI
---
::

    python scripts/case_library/init_zero_case.py \
        --library-root data/case_library

Idempotent: re-running after the file exists prints ``already exists`` and
exits 0 without rewriting anything.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
_INK_SCRIPTS = _REPO_ROOT / "ink-writer" / "scripts"
for _candidate in (_REPO_ROOT, _INK_SCRIPTS):
    _sp = str(_candidate)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from ink_writer.case_library.models import (  # noqa: E402
    Case,
    CaseDomain,
    CaseLayer,
    CaseSeverity,
    CaseStatus,
    FailurePattern,
    Scope,
    Source,
    SourceType,
)
from ink_writer.case_library.store import CaseStore  # noqa: E402

ZERO_CASE_ID = "CASE-2026-0000"


def _build_zero_case() -> Case:
    return Case(
        case_id=ZERO_CASE_ID,
        title="reference_corpus 软链接全断导致范文召回静默失效",
        status=CaseStatus.ACTIVE,
        severity=CaseSeverity.P0,
        domain=CaseDomain.INFRA_HEALTH,
        layer=[CaseLayer.INFRA_HEALTH],
        tags=["reference_corpus", "symlink", "silent_degradation"],
        scope=Scope(
            genre=[],
            chapter=[],
            trigger="repo 搬迁或 benchmark/corpus 路径变更后未重建 reference_corpus",
        ),
        source=Source(
            type=SourceType.INFRA_CHECK,
            raw_text=(
                "benchmark/reference_corpus/<book>/chapters/*.txt 全部是指向旧绝对路径的"
                "软链接；repo 搬到 /Users/cipher/AI/小说/ink/ 之后 target 全部失效，"
                "Retriever 在加载范文时静默返回空列表，下游 writer/polish 失去风格锚点。"
            ),
            ingested_at="2026-04-23",
            reviewer="self",
            ingested_from="benchmark/reference_corpus/",
        ),
        failure_pattern=FailurePattern(
            description=(
                "reference_corpus 以软链接形态存在、target 指向仓库外部绝对路径；"
                "仓库位置变化后链接全断，Retriever 加载时不抛错仅静默返回空结果，"
                "导致下游组件失去可读范文但不可观测。"
            ),
            observable=[
                "broken symlink count under reference_corpus/*/chapters > 0",
                "corpus_root readable file count < min_files threshold",
            ],
        ),
        bound_assets={
            "checkers": [
                {
                    "checker_id": "preflight-reference-corpus-readable",
                    "version": "v1",
                    "created_for_this_case": True,
                }
            ]
        },
        resolution={
            "introduced_at": "2026-04-23",
            "validation_chapters": [],
            "related_cases": [],
        },
        evidence_links=[],
    )


def init_zero_case(library_root: Path) -> bool:
    """Ensure ``CASE-2026-0000`` exists under *library_root*.

    Returns ``True`` if a new YAML was written, ``False`` if the case was
    already present. Never raises for the idempotent "already there" path.
    """

    store = CaseStore(Path(library_root))
    if ZERO_CASE_ID in store.list_ids():
        return False
    store.save(_build_zero_case())
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Register CASE-2026-0000 — the infra_health zero-case for the "
            "reference_corpus symlink incident. Idempotent."
        ),
    )
    parser.add_argument(
        "--library-root",
        type=Path,
        default=Path("data/case_library"),
        help="Case library root (default: data/case_library)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        from runtime_compat import enable_windows_utf8_stdio

        enable_windows_utf8_stdio()
    except Exception:  # pragma: no cover — optional helper; Mac/Linux no-op
        pass

    args = _build_parser().parse_args(argv)
    created = init_zero_case(args.library_root)
    print("created" if created else "already exists")
    return 0


if __name__ == "__main__":
    sys.exit(main())
