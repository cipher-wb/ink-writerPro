"""Preflight aggregator — runs the six independent checks and optionally:

1. auto-creates infra_health cases for every failure (sha256-dedup guarantees
   repeated runs do not inflate the library), and
2. raises :class:`PreflightError` so callers (e.g. ink-write Step 0) can
   fail-fast before doing any writing work.

The checker is deliberately pure orchestration: every piece of state (where to
look for reference_corpus, which editor-wisdom rules file, whether to use the
in-memory Qdrant client for tests) lives in :class:`PreflightConfig`. The six
check functions live in ``ink_writer.preflight.checks`` and NEVER raise; this
module decides what to do with their results.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ink_writer.case_library.ingest import ingest_case
from ink_writer.case_library.store import CaseStore
from ink_writer.preflight.checks import (
    CheckResult,
    check_case_library_loadable,
    check_editor_wisdom_index_loadable,
    check_embedding_api_reachable,
    check_qdrant_connection,
    check_reference_corpus_readable,
    check_rerank_api_reachable,
)
from ink_writer.preflight.errors import PreflightError
from ink_writer.qdrant.client import QdrantConfig


@dataclass
class PreflightConfig:
    reference_root: Path
    case_library_root: Path
    editor_wisdom_rules_path: Path
    qdrant_config: QdrantConfig | None = None
    qdrant_in_memory: bool = False
    require_embedding_key: bool = False
    require_rerank_key: bool = False
    min_corpus_files: int = 100


@dataclass(frozen=True)
class PreflightReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failed(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed]


def _run_all_checks(config: PreflightConfig) -> list[CheckResult]:
    results: list[CheckResult] = [
        check_reference_corpus_readable(
            config.reference_root, min_files=config.min_corpus_files
        ),
        check_case_library_loadable(config.case_library_root),
        check_editor_wisdom_index_loadable(config.editor_wisdom_rules_path),
    ]
    if config.qdrant_in_memory:
        results.append(
            check_qdrant_connection(config=QdrantConfig(memory=True))
        )
    else:
        results.append(check_qdrant_connection(config=config.qdrant_config))

    if config.require_embedding_key:
        results.append(check_embedding_api_reachable())
    if config.require_rerank_key:
        results.append(check_rerank_api_reachable())
    return results


def _auto_create_infra_case(store: CaseStore, check: CheckResult) -> None:
    ingest_case(
        store,
        title=f"preflight failure: {check.name}",
        raw_text=f"preflight check failed: {check.name}: {check.detail}",
        domain="infra_health",
        layer=["infra_health"],
        severity="P0",
        tags=["preflight", check.name],
        source_type="infra_check",
        ingested_at=date.today().isoformat(),
        failure_description=check.detail,
        observable=[f"{check.name}.passed == False"],
    )


def run_preflight(
    config: PreflightConfig,
    *,
    raise_on_fail: bool = False,
    auto_create_infra_cases: bool = False,
) -> PreflightReport:
    """Run all preflight checks and return an aggregated report.

    Args:
        config: What to check and how (paths, flags).
        raise_on_fail: If True, raise :class:`PreflightError` when any check
            failed.
        auto_create_infra_cases: If True, for every failed check call
            :func:`ingest_case` to record an infra_health case. SHA-256 dedup in
            ingest_case ensures repeated runs do not inflate the library.

    Returns:
        :class:`PreflightReport` with every check result.

    Raises:
        PreflightError: when ``raise_on_fail`` is True and at least one check
            failed. The error carries the list of failing check names.
    """
    results = _run_all_checks(config)
    report = PreflightReport(results=results)

    if auto_create_infra_cases and report.failed:
        store = CaseStore(config.case_library_root)
        for check in report.failed:
            _auto_create_infra_case(store, check)

    if raise_on_fail and report.failed:
        failed_names = [r.name for r in report.failed]
        raise PreflightError(
            failed_names, f"preflight failed: {failed_names}"
        )

    return report
