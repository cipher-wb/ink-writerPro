"""Case ingest entry point — sha256 dedup + auto case_id allocation.

``ingest_case`` is the single write path into the case library. Every call
hashes the ``raw_text`` (SHA-256) and scans the store for an existing case
whose ``source.raw_text`` matches. If found, the caller gets the existing
case_id back with ``created=False`` and the store is not mutated (no YAML
write, no ingest_log append). Otherwise the next ``CASE-YYYY-NNNN`` id is
allocated (based on the current year and max existing serial), the case is
saved, and an audit event is appended to ``ingest_log.jsonl``.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from ink_writer.case_library.models import (
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
from ink_writer.case_library.store import CaseStore


@dataclass(frozen=True)
class IngestResult:
    case_id: str
    created: bool
    raw_text_hash: str


def _hash_raw_text(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def _find_existing_by_hash(store: CaseStore, raw_text_hash: str) -> str | None:
    for case in store.iter_cases():
        if _hash_raw_text(case.source.raw_text) == raw_text_hash:
            return case.case_id
    return None


def _allocate_case_id(store: CaseStore) -> str:
    year = datetime.now(UTC).year
    prefix = f"CASE-{year}-"
    max_serial = 0
    for cid in store.list_ids():
        if not cid.startswith(prefix):
            continue
        try:
            serial = int(cid[len(prefix) :])
        except ValueError:
            continue
        if serial > max_serial:
            max_serial = serial
    return f"{prefix}{max_serial + 1:04d}"


def ingest_case(
    store: CaseStore,
    *,
    title: str,
    raw_text: str,
    domain: str,
    layer: list[str],
    severity: str,
    tags: list[str],
    source_type: str,
    ingested_at: str,
    failure_description: str,
    observable: list[str],
    reviewer: str | None = None,
    ingested_from: str | None = None,
    scope_genre: list[str] | None = None,
    scope_chapter: list[str] | None = None,
    initial_status: str = "active",
) -> IngestResult:
    """Ingest a raw_text-keyed case; dedup by SHA-256 of raw_text.

    Returns:
        IngestResult with ``created=True`` when a new YAML was written, or
        ``created=False`` when an existing case_id was returned. In the dedup
        path the store is not mutated.
    """
    raw_text_hash = _hash_raw_text(raw_text)

    existing = _find_existing_by_hash(store, raw_text_hash)
    if existing is not None:
        return IngestResult(
            case_id=existing, created=False, raw_text_hash=raw_text_hash
        )

    case_id = _allocate_case_id(store)
    case = Case(
        case_id=case_id,
        title=title,
        status=CaseStatus(initial_status),
        severity=CaseSeverity(severity),
        domain=CaseDomain(domain),
        layer=[CaseLayer(item) for item in layer],
        tags=list(tags),
        scope=Scope(
            genre=list(scope_genre) if scope_genre else [],
            chapter=list(scope_chapter) if scope_chapter else [],
        ),
        source=Source(
            type=SourceType(source_type),
            raw_text=raw_text,
            ingested_at=ingested_at,
            reviewer=reviewer,
            ingested_from=ingested_from,
        ),
        failure_pattern=FailurePattern(
            description=failure_description,
            observable=list(observable),
        ),
    )
    store.save(case)
    store.append_ingest_log(
        {
            "event": "ingest",
            "case_id": case_id,
            "raw_text_hash": raw_text_hash,
            "at": datetime.now(UTC).isoformat(),
        }
    )
    return IngestResult(case_id=case_id, created=True, raw_text_hash=raw_text_hash)
