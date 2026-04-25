"""US-010 — ink-learn promote (project_memory.json → CASE-PROMOTE-NNNN)."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from ink_writer.case_library.store import CaseStore
from ink_writer.learn.promote import promote_short_term_to_long_term


def _write_memory(path: Path, patterns: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"patterns": patterns}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


@pytest.fixture
def case_store(tmp_path: Path) -> CaseStore:
    return CaseStore(tmp_path / "case_library")


@pytest.fixture
def now_dt() -> datetime:
    return datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC)


def test_promotes_high_frequency_pattern(
    tmp_path: Path, case_store: CaseStore, now_dt: datetime
) -> None:
    memory = tmp_path / ".ink" / "book-A" / "project_memory.json"
    _write_memory(
        memory,
        [
            {"text": "对话密度过低导致节奏拖沓", "kind": "failure", "count": 5},
        ],
    )

    proposed = promote_short_term_to_long_term(
        project_memory_path=memory,
        case_store=case_store,
        cases_dir=case_store.cases_dir,
        now=now_dt,
    )

    assert len(proposed) == 1
    case = proposed[0]
    assert case.case_id == "CASE-PROMOTE-0001"
    assert case.status.value == "pending"
    assert case.severity.value == "P2"
    assert "m5_promote" in case.tags
    assert "failure" in case.tags
    assert case.failure_pattern.description == "对话密度过低导致节奏拖沓"
    on_disk = case_store.cases_dir / "CASE-PROMOTE-0001.yaml"
    assert on_disk.exists()
    with open(on_disk, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert data["case_id"] == "CASE-PROMOTE-0001"
    assert data["source"]["ingested_from"] == "ink_learn_promote"


def test_skips_below_min_occurrences(
    tmp_path: Path, case_store: CaseStore, now_dt: datetime
) -> None:
    memory = tmp_path / ".ink" / "book-A" / "project_memory.json"
    _write_memory(
        memory,
        [
            {"text": "鲜见的尝试", "kind": "failure", "count": 2},
            {"text": "另一个低频模式", "kind": "success", "count": 1},
        ],
    )

    proposed = promote_short_term_to_long_term(
        project_memory_path=memory,
        case_store=case_store,
        cases_dir=case_store.cases_dir,
        min_occurrences=3,
        now=now_dt,
    )
    assert proposed == []


def test_handles_missing_project_memory(
    tmp_path: Path, case_store: CaseStore, now_dt: datetime
) -> None:
    missing = tmp_path / ".ink" / "book-A" / "project_memory.json"
    proposed = promote_short_term_to_long_term(
        project_memory_path=missing,
        case_store=case_store,
        cases_dir=case_store.cases_dir,
        now=now_dt,
    )
    assert proposed == []


def test_success_kind_assigns_p3(
    tmp_path: Path, case_store: CaseStore, now_dt: datetime
) -> None:
    memory = tmp_path / ".ink" / "book-A" / "project_memory.json"
    _write_memory(
        memory,
        [
            {"text": "倒计时危机钩复用得当", "kind": "success", "count": 4},
        ],
    )

    proposed = promote_short_term_to_long_term(
        project_memory_path=memory,
        case_store=case_store,
        cases_dir=case_store.cases_dir,
        now=now_dt,
    )

    assert len(proposed) == 1
    case = proposed[0]
    assert case.severity.value == "P3"
    assert "success" in case.tags
    assert "m5_promote" in case.tags
