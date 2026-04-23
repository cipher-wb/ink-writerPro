"""Tests for ink_writer.case_library.store.CaseStore."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml
from ink_writer.case_library.errors import CaseNotFoundError, CaseValidationError
from ink_writer.case_library.models import Case
from ink_writer.case_library.store import CaseStore


def _make_case(sample_case_dict: dict) -> Case:
    return Case.from_dict(sample_case_dict)


def test_save_then_load(tmp_path: Path, sample_case_dict: dict) -> None:
    store = CaseStore(tmp_path / "lib")
    case = _make_case(sample_case_dict)

    written = store.save(case)

    assert written == tmp_path / "lib" / "cases" / f"{case.case_id}.yaml"
    assert written.exists()

    loaded = store.load(case.case_id)
    assert loaded.to_dict() == case.to_dict()


def test_save_writes_yaml_with_utf8(tmp_path: Path, sample_case_dict: dict) -> None:
    store = CaseStore(tmp_path / "lib")
    case = _make_case(sample_case_dict)

    path = store.save(case)

    # Raw bytes must contain the original Chinese title (UTF-8, not escaped).
    raw = path.read_bytes()
    assert "主角接到电话 3 秒就不慌，反应不真实".encode() in raw

    # Parsed YAML preserves the case_id ordering (sort_keys=False).
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert list(parsed.keys())[0] == "case_id"
    assert parsed["title"] == sample_case_dict["title"]


def test_load_missing_raises(tmp_path: Path) -> None:
    store = CaseStore(tmp_path / "lib")
    with pytest.raises(CaseNotFoundError):
        store.load("CASE-2026-9999")


def test_save_invalid_case_raises(tmp_path: Path, sample_case_dict: dict) -> None:
    store = CaseStore(tmp_path / "lib")
    case = Case.from_dict(sample_case_dict)
    # Empty observable trips schema minItems=1 while keeping all enum values
    # legal, so to_dict() serializes cleanly and save() is the gate we exercise.
    case.failure_pattern.observable = []

    with pytest.raises(CaseValidationError):
        store.save(case)

    assert not (tmp_path / "lib" / "cases" / f"{case.case_id}.yaml").exists()


def test_list_returns_all_case_ids(tmp_path: Path, sample_case_dict: dict) -> None:
    store = CaseStore(tmp_path / "lib")
    first = _make_case(sample_case_dict)
    second_dict = copy.deepcopy(sample_case_dict)
    second_dict["case_id"] = "CASE-2026-0002"
    second = _make_case(second_dict)
    third_dict = copy.deepcopy(sample_case_dict)
    third_dict["case_id"] = "CASE-2026-0003"
    third = _make_case(third_dict)

    store.save(third)
    store.save(first)
    store.save(second)

    assert store.list_ids() == [
        "CASE-2026-0001",
        "CASE-2026-0002",
        "CASE-2026-0003",
    ]


def test_pack_jsonl_emits_one_line_per_case(
    tmp_path: Path, sample_case_dict: dict
) -> None:
    store = CaseStore(tmp_path / "lib")
    for idx in (1, 2):
        d = copy.deepcopy(sample_case_dict)
        d["case_id"] = f"CASE-2026-000{idx}"
        store.save(Case.from_dict(d))

    out = tmp_path / "pack" / "cases.jsonl"
    count = store.pack_jsonl(out)

    assert count == 2
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    ids = [json.loads(line)["case_id"] for line in lines]
    assert ids == ["CASE-2026-0001", "CASE-2026-0002"]
    # ensure_ascii=False preserved Chinese directly.
    assert "主角" in lines[0]


def test_append_ingest_log(tmp_path: Path) -> None:
    store = CaseStore(tmp_path / "lib")
    store.append_ingest_log({"event": "ingest", "case_id": "CASE-2026-0001"})
    store.append_ingest_log({"event": "ingest", "case_id": "CASE-2026-0002"})

    log_path = tmp_path / "lib" / "ingest_log.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"event": "ingest", "case_id": "CASE-2026-0001"}
    assert json.loads(lines[1]) == {"event": "ingest", "case_id": "CASE-2026-0002"}
