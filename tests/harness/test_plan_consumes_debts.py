"""US-017 (FIX-17 P4d): ink-plan 消费 propagation_debt 集成测试。

验证 :mod:`ink_writer.propagation.plan_integration`：

- ``load_active_debts`` 只返回 status ∈ {"open", "in_progress"} 的项。
- ``filter_debts_for_range`` 根据 target_chapter 区间过滤。
- ``mark_debts_resolved`` 把被消化的 debts 翻转为 resolved 并持久化。
- ``render_debts_for_plan`` 生成可注入 planner 的 markdown。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ink_writer.propagation import (
    ACTIVE_STATUSES,
    DebtStore,
    PropagationDebtItem,
    filter_debts_for_range,
    load_active_debts,
    mark_debts_resolved,
    render_debts_for_plan,
)


def _seed_store(tmp_path: Path, items):
    store = DebtStore(project_root=tmp_path)
    store.save_debts(items)
    return store


def _item(debt_id: str, target_chapter: int, status: str = "open") -> PropagationDebtItem:
    return PropagationDebtItem(
        debt_id=debt_id,
        chapter_detected=target_chapter + 5,
        rule_violation="character.power_level",
        target_chapter=target_chapter,
        severity="high",
        suggested_fix="补伏笔",
        status=status,  # type: ignore[arg-type]
    )


def test_active_statuses_constant():
    assert ACTIVE_STATUSES == frozenset({"open", "in_progress"})


def test_load_active_debts_filters_out_closed(tmp_path: Path):
    _seed_store(
        tmp_path,
        [
            _item("DEBT-1", 10, "open"),
            _item("DEBT-2", 20, "in_progress"),
            _item("DEBT-3", 30, "resolved"),
            _item("DEBT-4", 40, "wont_fix"),
        ],
    )
    active = load_active_debts(tmp_path)
    ids = sorted(item.debt_id for item in active)
    assert ids == ["DEBT-1", "DEBT-2"]


def test_load_active_debts_missing_file_returns_empty(tmp_path: Path):
    assert load_active_debts(tmp_path) == []


def test_filter_debts_for_range_inclusive_bounds():
    debts = [_item("A", 5), _item("B", 10), _item("C", 15), _item("D", 20)]
    in_range = filter_debts_for_range(debts, 10, 20)
    assert [d.debt_id for d in in_range] == ["B", "C", "D"]


def test_filter_debts_for_range_swapped_bounds_tolerated():
    debts = [_item("A", 5), _item("B", 15)]
    assert [d.debt_id for d in filter_debts_for_range(debts, 20, 1)] == ["A", "B"]


def test_mark_debts_resolved_updates_file_and_returns_changed(tmp_path: Path):
    _seed_store(
        tmp_path,
        [
            _item("DEBT-1", 10, "open"),
            _item("DEBT-2", 20, "in_progress"),
            _item("DEBT-3", 30, "open"),
        ],
    )

    changed = mark_debts_resolved(tmp_path, ["DEBT-1", "DEBT-2"])
    assert sorted(changed) == ["DEBT-1", "DEBT-2"]

    payload = json.loads((tmp_path / ".ink" / "propagation_debt.json").read_text(encoding="utf-8"))
    status_by_id = {row["debt_id"]: row["status"] for row in payload["items"]}
    assert status_by_id == {
        "DEBT-1": "resolved",
        "DEBT-2": "resolved",
        "DEBT-3": "open",
    }


def test_mark_debts_resolved_idempotent(tmp_path: Path):
    _seed_store(tmp_path, [_item("DEBT-1", 10, "resolved")])
    # Already resolved → no changes reported.
    assert mark_debts_resolved(tmp_path, ["DEBT-1"]) == []


def test_mark_debts_resolved_empty_input_noop(tmp_path: Path):
    # No file should be created when input list is empty.
    assert mark_debts_resolved(tmp_path, []) == []
    assert not (tmp_path / ".ink" / "propagation_debt.json").exists()


def test_render_debts_for_plan_includes_ids_and_targets():
    debts = [
        _item("DEBT-1", 12),
        _item("DEBT-2", 45),
    ]
    rendered = render_debts_for_plan(debts)
    assert "DEBT-1" in rendered
    assert "target_ch=12" in rendered
    assert "DEBT-2" in rendered
    assert "target_ch=45" in rendered
    assert "hard constraint" in rendered


def test_render_debts_for_plan_empty_returns_sentinel():
    rendered = render_debts_for_plan([])
    assert "无" in rendered


# --- 端到端：模拟 plan 消费流程 ---


def test_plan_consumes_debts_end_to_end(tmp_path: Path):
    _seed_store(
        tmp_path,
        [
            _item("DEBT-A", 5, "open"),
            _item("DEBT-B", 25, "in_progress"),
            _item("DEBT-C", 80, "open"),  # out of range → not consumed
            _item("DEBT-D", 30, "resolved"),
        ],
    )

    # Planner: load active + filter for volume range [10, 50]
    active = load_active_debts(tmp_path)
    consumable = filter_debts_for_range(active, 10, 50)
    consumed_ids = [item.debt_id for item in consumable]
    assert consumed_ids == ["DEBT-B"]

    # Simulate plan annotation
    chapter_plan = {"volume": 2, "range": [10, 50], "consumed_debt_ids": consumed_ids}
    assert chapter_plan["consumed_debt_ids"] == ["DEBT-B"]

    # Commit: mark consumed debts resolved
    changed = mark_debts_resolved(tmp_path, consumed_ids)
    assert changed == ["DEBT-B"]

    # Re-load: active set shrinks
    remaining_active = {item.debt_id for item in load_active_debts(tmp_path)}
    assert remaining_active == {"DEBT-A", "DEBT-C"}
