"""Tests for scripts.case_library.init_zero_case (US-009)."""
from __future__ import annotations

from pathlib import Path

from ink_writer.case_library.models import (
    CaseDomain,
    CaseLayer,
    CaseSeverity,
    CaseStatus,
    SourceType,
)
from ink_writer.case_library.store import CaseStore
from scripts.case_library.init_zero_case import (
    ZERO_CASE_ID,
    init_zero_case,
)


def test_zero_case_is_infra_health_active(tmp_path: Path) -> None:
    library_root = tmp_path / "lib"

    created = init_zero_case(library_root)

    assert created is True

    store = CaseStore(library_root)
    case = store.load(ZERO_CASE_ID)

    assert case.case_id == "CASE-2026-0000"
    assert case.status == CaseStatus.ACTIVE
    assert case.severity == CaseSeverity.P0
    assert case.domain == CaseDomain.INFRA_HEALTH
    assert case.layer == [CaseLayer.INFRA_HEALTH]
    assert set(case.tags) >= {"reference_corpus", "symlink", "silent_degradation"}
    assert case.source.type == SourceType.INFRA_CHECK
    assert case.source.reviewer == "self"
    assert case.source.ingested_at == "2026-04-23"
    assert case.source.ingested_from == "benchmark/reference_corpus/"
    assert len(case.failure_pattern.observable) >= 2

    checkers = case.bound_assets.get("checkers", [])
    assert any(
        c.get("checker_id") == "preflight-reference-corpus-readable"
        and c.get("version") == "v1"
        and c.get("created_for_this_case") is True
        for c in checkers
    )


def test_zero_case_init_is_idempotent(tmp_path: Path) -> None:
    library_root = tmp_path / "lib"

    first = init_zero_case(library_root)
    second = init_zero_case(library_root)

    assert first is True
    assert second is False

    store = CaseStore(library_root)
    assert store.list_ids().count(ZERO_CASE_ID) == 1
