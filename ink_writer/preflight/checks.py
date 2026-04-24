"""Six independent preflight check functions.

Every check returns a :class:`CheckResult` and NEVER raises. The checker in
``ink_writer.preflight.checker`` is responsible for aggregation, optional
``PreflightError`` escalation, and auto-creating infra_health cases.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ink_writer.qdrant.client import QdrantConfig, get_client_from_config
from ink_writer.qdrant.errors import QdrantUnreachableError

if TYPE_CHECKING:
    from qdrant_client import QdrantClient


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def check_reference_corpus_readable(
    reference_root: Path, *, min_files: int = 100
) -> CheckResult:
    name = "reference_corpus_readable"
    if not reference_root.exists() or not reference_root.is_dir():
        return CheckResult(
            name, False, f"reference_root {reference_root} missing or not a directory"
        )
    broken = 0
    readable = 0
    for p in reference_root.rglob("*.txt"):
        if p.is_symlink() and not p.exists():
            broken += 1
        elif p.is_file():
            readable += 1
    if broken > 0:
        return CheckResult(name, False, f"{broken} broken symlink(s)")
    if readable < min_files:
        return CheckResult(
            name, False, f"{readable} files readable (< {min_files} minimum)"
        )
    return CheckResult(name, True, f"{readable} files readable")


def check_case_library_loadable(library_root: Path) -> CheckResult:
    name = "case_library_loadable"
    cases_dir = library_root / "cases"
    if not cases_dir.exists() or not cases_dir.is_dir():
        return CheckResult(name, False, f"{cases_dir} missing or not a directory")
    n = sum(1 for _ in cases_dir.glob("CASE-*.yaml"))
    return CheckResult(name, True, f"{n} cases on disk")


def check_editor_wisdom_index_loadable(rules_path: Path) -> CheckResult:
    name = "editor_wisdom_index_loadable"
    if not rules_path.exists() or not rules_path.is_file():
        return CheckResult(name, False, f"rules file {rules_path} not found")
    try:
        with rules_path.open(encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as err:
        return CheckResult(name, False, f"rules file {rules_path} invalid JSON: {err}")
    if isinstance(data, list):
        n = len(data)
    elif isinstance(data, dict):
        inner = data.get("rules", data)
        n = len(inner) if isinstance(inner, (list, dict)) else 1
    else:
        n = 0
    return CheckResult(name, True, f"{n} rules indexed")


def check_qdrant_connection(
    *, client: QdrantClient | None = None, config: QdrantConfig | None = None
) -> CheckResult:
    name = "qdrant_connection"
    try:
        if client is None:
            client = get_client_from_config(config or QdrantConfig())
        collections = client.get_collections().collections
        return CheckResult(name, True, f"{len(collections)} collection(s) reachable")
    except QdrantUnreachableError as err:
        return CheckResult(name, False, f"Qdrant unreachable: {err}")
    except Exception as err:  # noqa: BLE001 — preflight NEVER raises
        return CheckResult(name, False, f"unexpected error: {err}")


def check_embedding_api_reachable() -> CheckResult:
    name = "embedding_api_reachable"
    if not os.environ.get("EMBED_API_KEY"):
        return CheckResult(name, False, "EMBED_API_KEY not set")
    return CheckResult(name, True, "EMBED_API_KEY set")


def check_rerank_api_reachable() -> CheckResult:
    name = "rerank_api_reachable"
    if not os.environ.get("RERANK_API_KEY"):
        return CheckResult(name, False, "RERANK_API_KEY not set")
    return CheckResult(name, True, "RERANK_API_KEY set")
