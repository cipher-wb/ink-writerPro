"""Tests for CaseIndex (sqlite inverted index over the YAML case library)."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from ink_writer.case_library.index import CaseIndex
from ink_writer.case_library.models import Case
from ink_writer.case_library.store import CaseStore


@pytest.fixture
def two_case_store(tmp_path: Path, sample_case_dict: dict) -> CaseStore:
    """Seed a CaseStore with two cases spanning different status/layer/genre/tags."""
    store = CaseStore(tmp_path / "lib")

    first = deepcopy(sample_case_dict)
    first["case_id"] = "CASE-2026-0001"
    first["status"] = "active"
    first["layer"] = ["downstream"]
    first["tags"] = ["reader_immersion", "protagonist_reaction"]
    first["scope"] = {"genre": ["玄幻"], "chapter": ["ch001"]}
    store.save(Case.from_dict(first))

    second = deepcopy(sample_case_dict)
    second["case_id"] = "CASE-2026-0002"
    second["status"] = "pending"
    second["severity"] = "P0"
    second["domain"] = "infra_health"
    second["layer"] = ["infra_health", "upstream"]
    second["tags"] = ["reader_immersion", "symlink"]
    second["scope"] = {"genre": ["都市"], "chapter": ["ch002"]}
    store.save(Case.from_dict(second))

    return store


def test_build_index_creates_sqlite(tmp_path: Path, two_case_store: CaseStore) -> None:
    sqlite_path = tmp_path / "index.sqlite"
    index = CaseIndex(sqlite_path)
    indexed = index.build(two_case_store)
    assert indexed == 2
    assert sqlite_path.exists()


def test_query_by_tag(tmp_path: Path, two_case_store: CaseStore) -> None:
    index = CaseIndex(tmp_path / "index.sqlite")
    index.build(two_case_store)
    assert index.query_by_tag("reader_immersion") == [
        "CASE-2026-0001",
        "CASE-2026-0002",
    ]
    assert index.query_by_tag("symlink") == ["CASE-2026-0002"]
    assert index.query_by_tag("nonexistent") == []


def test_query_by_layer(tmp_path: Path, two_case_store: CaseStore) -> None:
    index = CaseIndex(tmp_path / "index.sqlite")
    index.build(two_case_store)
    assert index.query_by_layer("downstream") == ["CASE-2026-0001"]
    assert index.query_by_layer("infra_health") == ["CASE-2026-0002"]
    assert index.query_by_layer("upstream") == ["CASE-2026-0002"]


def test_query_by_genre(tmp_path: Path, two_case_store: CaseStore) -> None:
    index = CaseIndex(tmp_path / "index.sqlite")
    index.build(two_case_store)
    assert index.query_by_genre("玄幻") == ["CASE-2026-0001"]
    assert index.query_by_genre("都市") == ["CASE-2026-0002"]


def test_query_by_status(tmp_path: Path, two_case_store: CaseStore) -> None:
    index = CaseIndex(tmp_path / "index.sqlite")
    index.build(two_case_store)
    assert index.query_by_status("active") == ["CASE-2026-0001"]
    assert index.query_by_status("pending") == ["CASE-2026-0002"]
    assert index.query_by_status("resolved") == []


def test_rebuild_is_idempotent(tmp_path: Path, two_case_store: CaseStore) -> None:
    index = CaseIndex(tmp_path / "index.sqlite")
    assert index.build(two_case_store) == 2
    assert index.build(two_case_store) == 2
    # Queries still return the same result after rebuild.
    assert index.query_by_tag("reader_immersion") == [
        "CASE-2026-0001",
        "CASE-2026-0002",
    ]
    assert index.query_by_status("active") == ["CASE-2026-0001"]
