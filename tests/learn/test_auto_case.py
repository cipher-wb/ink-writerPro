"""US-009 — ink-learn auto_case (propose pending cases from blocked patterns)."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from ink_writer.case_library.store import CaseStore
from ink_writer.learn.auto_case import _hit_case_ids, propose_cases_from_failures


def _write_chapter_evidence(
    *,
    base_dir: Path,
    book: str,
    chapter: str,
    cases_violated: list[str],
    outcome: str = "blocked",
    produced_at: str = "2026-04-24T00:00:00+00:00",
) -> Path:
    out = base_dir / book / "chapters" / f"{chapter}.evidence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "$schema": "https://ink-writer/evidence_chain_v1",
        "book": book,
        "chapter": chapter,
        "phase": "writing",
        "stage": None,
        "produced_at": produced_at,
        "dry_run": False,
        "outcome": outcome,
        "phase_evidence": {
            "checkers": [
                {
                    "id": "test-checker",
                    "score": 0.0,
                    "blocked": outcome == "blocked",
                    "cases_violated": list(cases_violated),
                    "cases_hit": [],
                }
            ],
        },
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    return out


def _write_throttle(tmp_path: Path, **overrides: int) -> Path:
    payload = {
        "auto_case_from_failure": {
            "max_per_week": 5,
            "min_pattern_occurrences": 2,
            "pattern_window_days": 7,
            **overrides,
        }
    }
    path = tmp_path / "ink_learn_throttle.yaml"
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False)
    return path


@pytest.fixture
def case_store(tmp_path: Path) -> CaseStore:
    return CaseStore(tmp_path / "case_library")


@pytest.fixture
def now_dt() -> datetime:
    return datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC)


def test_proposes_when_pattern_repeats(
    tmp_path: Path, case_store: CaseStore, now_dt: datetime
) -> None:
    base_dir = tmp_path / "data"
    pattern = ["CASE-2026-0001", "CASE-2026-0002"]
    _write_chapter_evidence(
        base_dir=base_dir, book="book-A", chapter="0001", cases_violated=pattern
    )
    _write_chapter_evidence(
        base_dir=base_dir, book="book-A", chapter="0002", cases_violated=pattern
    )

    proposed = propose_cases_from_failures(
        case_store=case_store,
        base_dir=base_dir,
        cases_dir=case_store.cases_dir,
        throttle_path=_write_throttle(tmp_path),
        now=now_dt,
    )

    assert len(proposed) == 1
    case = proposed[0]
    assert case.case_id == "CASE-LEARN-0001"
    assert case.status.value == "pending"
    assert case.severity.value == "P2"
    assert "m5_auto_learn" in case.tags
    assert case.failure_pattern.observable == sorted(pattern)
    # Persisted with schema validation.
    on_disk = case_store.cases_dir / "CASE-LEARN-0001.yaml"
    assert on_disk.exists()
    with open(on_disk, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert data["case_id"] == "CASE-LEARN-0001"
    assert data["source"]["ingested_from"] == "ink_learn_auto"


def test_skips_below_min_occurrences(
    tmp_path: Path, case_store: CaseStore, now_dt: datetime
) -> None:
    base_dir = tmp_path / "data"
    _write_chapter_evidence(
        base_dir=base_dir, book="book-A", chapter="0001",
        cases_violated=["CASE-2026-0010"],
    )
    # Only 1 chapter — below min_pattern_occurrences=2.
    proposed = propose_cases_from_failures(
        case_store=case_store,
        base_dir=base_dir,
        cases_dir=case_store.cases_dir,
        throttle_path=_write_throttle(tmp_path),
        now=now_dt,
    )
    assert proposed == []


def test_throttled_at_max_per_week(
    tmp_path: Path, case_store: CaseStore, now_dt: datetime
) -> None:
    base_dir = tmp_path / "data"
    # 3 distinct recurring patterns, max_per_week=2 → only 2 proposed.
    for i, pat in enumerate([
        ["CASE-2026-0100"],
        ["CASE-2026-0200"],
        ["CASE-2026-0300"],
    ]):
        _write_chapter_evidence(
            base_dir=base_dir, book="book-A", chapter=f"{i:04d}-a",
            cases_violated=pat,
        )
        _write_chapter_evidence(
            base_dir=base_dir, book="book-A", chapter=f"{i:04d}-b",
            cases_violated=pat,
        )

    proposed = propose_cases_from_failures(
        case_store=case_store,
        base_dir=base_dir,
        cases_dir=case_store.cases_dir,
        throttle_path=_write_throttle(tmp_path, max_per_week=2),
        now=now_dt,
    )
    assert len(proposed) == 2

    # A second invocation in the same week is fully throttled (already at cap).
    again = propose_cases_from_failures(
        case_store=case_store,
        base_dir=base_dir,
        cases_dir=case_store.cases_dir,
        throttle_path=_write_throttle(tmp_path, max_per_week=2),
        now=now_dt,
    )
    assert again == []


def test_hit_case_ids_rejects_dict_payload() -> None:
    """US-007 (review §三 #10) — 上游 schema 漂移交付 dict 而非 list 时，旧版用
    ``isinstance(value, Iterable)`` 会迭代 dict keys 当作 case_id silently 污染
    学习管线；收紧到 ``isinstance(value, list)`` 后必须返 [] 而非 ['CASE-A']。"""
    checker = {"cases_violated": {"CASE-A": "x"}}
    assert _hit_case_ids(checker) == []

    # 同样收紧 details.* 路径与 cases_hit 键。
    nested = {"details": {"cases_hit": {"CASE-B": "y"}}}
    assert _hit_case_ids(nested) == []

    # 其他非 list 异常 payload（set / tuple / generator / str）也被一律拒绝。
    assert _hit_case_ids({"cases_violated": {"CASE-C", "CASE-D"}}) == []
    assert _hit_case_ids({"cases_violated": ("CASE-E", "CASE-F")}) == []
    assert _hit_case_ids({"cases_violated": (x for x in ["CASE-G"])}) == []
    assert _hit_case_ids({"cases_violated": "CASE-H"}) == []

    # 正常 list 路径仍可工作（守护回归）。
    assert _hit_case_ids({"cases_violated": ["CASE-X"]}) == ["CASE-X"]
    assert _hit_case_ids(
        {"cases_hit": [{"case_id": "CASE-Y"}, "CASE-Z"]}
    ) == ["CASE-Y", "CASE-Z"]


def test_skips_passed_chapters(
    tmp_path: Path, case_store: CaseStore, now_dt: datetime
) -> None:
    base_dir = tmp_path / "data"
    # Both chapters violated the same pair, but outcome=delivered → not blocked.
    pattern = ["CASE-2026-0500", "CASE-2026-0501"]
    _write_chapter_evidence(
        base_dir=base_dir, book="book-A", chapter="0001",
        cases_violated=pattern, outcome="delivered",
    )
    _write_chapter_evidence(
        base_dir=base_dir, book="book-A", chapter="0002",
        cases_violated=pattern, outcome="delivered",
    )

    proposed = propose_cases_from_failures(
        case_store=case_store,
        base_dir=base_dir,
        cases_dir=case_store.cases_dir,
        throttle_path=_write_throttle(tmp_path),
        now=now_dt,
    )
    assert proposed == []
