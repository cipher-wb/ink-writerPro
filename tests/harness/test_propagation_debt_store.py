"""US-014 (FIX-17 P4a): propagation_debt.json schema + DebtStore 往返测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ink_writer.propagation import DebtStore, PropagationDebtFile, PropagationDebtItem


def _sample_item(debt_id: str = "DEBT-0050-001") -> PropagationDebtItem:
    return PropagationDebtItem(
        debt_id=debt_id,
        chapter_detected=50,
        rule_violation="character.power_level 回溯矛盾",
        target_chapter=32,
        severity="high",
        suggested_fix="在第 32 章补充功法突破伏笔",
        status="open",
    )


def test_load_returns_empty_when_file_missing(tmp_path: Path):
    store = DebtStore(project_root=tmp_path)
    file = store.load()
    assert isinstance(file, PropagationDebtFile)
    assert file.items == []
    assert file.schema_version == 1


def test_save_and_load_roundtrip(tmp_path: Path):
    store = DebtStore(project_root=tmp_path)
    file = PropagationDebtFile(items=[_sample_item()])
    store.save(file)

    assert store.path.exists()
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert raw["items"][0]["debt_id"] == "DEBT-0050-001"
    assert raw["items"][0]["severity"] == "high"

    reloaded = store.load()
    assert len(reloaded.items) == 1
    assert reloaded.items[0] == file.items[0]


def test_append_upserts_existing(tmp_path: Path):
    store = DebtStore(project_root=tmp_path)
    store.append(_sample_item())

    updated = _sample_item()
    updated.status = "resolved"
    store.append(updated)

    file = store.load()
    assert len(file.items) == 1
    assert file.items[0].status == "resolved"


def test_append_inserts_new_items(tmp_path: Path):
    store = DebtStore(project_root=tmp_path)
    store.append(_sample_item("DEBT-0050-001"))
    store.append(_sample_item("DEBT-0051-001"))

    file = store.load()
    assert {item.debt_id for item in file.items} == {"DEBT-0050-001", "DEBT-0051-001"}


def test_schema_rejects_invalid_chapter():
    with pytest.raises(Exception):
        PropagationDebtItem(
            debt_id="bad",
            chapter_detected=0,
            rule_violation="x",
            target_chapter=1,
        )


def test_schema_rejects_invalid_severity():
    with pytest.raises(Exception):
        PropagationDebtItem(
            debt_id="bad",
            chapter_detected=1,
            rule_violation="x",
            target_chapter=1,
            severity="catastrophic",  # type: ignore[arg-type]
        )
