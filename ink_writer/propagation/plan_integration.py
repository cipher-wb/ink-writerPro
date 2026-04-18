"""FIX-17 P4d: ink-plan 消费 propagation_debt 的辅助函数。

ink-plan skill 在规划新卷时调用本模块：

1. :func:`load_active_debts` 读取 ``.ink/propagation_debt.json`` 中尚未关闭的 debts
   （status ∈ {"open", "in_progress"}），作为规划硬约束注入。
2. :func:`filter_debts_for_range` 过滤出 target_chapter 落在本次规划章节区间内的
   debts，交给 planner 在 chapter plan 中列出 ``consumed_debt_ids``。
3. :func:`mark_debts_resolved` 在 plan 落盘后将被消化的 debts 状态改为 ``resolved``。
4. :func:`render_debts_for_plan` 把 debts 渲染成 markdown 注入 planner 提示。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Sequence, Union

from ink_writer.propagation.debt_store import DebtStore
from ink_writer.propagation.models import PropagationDebtItem

ACTIVE_STATUSES = frozenset({"open", "in_progress"})


def load_active_debts(
    project_root: Union[str, Path],
) -> List[PropagationDebtItem]:
    """读取项目下 ``.ink/propagation_debt.json`` 中 active 状态的 debts。"""
    store = DebtStore(project_root=Path(project_root))
    file = store.load()
    return [item for item in file.items if item.status in ACTIVE_STATUSES]


def filter_debts_for_range(
    debts: Iterable[PropagationDebtItem],
    start_chapter: int,
    end_chapter: int,
) -> List[PropagationDebtItem]:
    """筛出 target_chapter 落在 [start_chapter, end_chapter] 区间内的 debts。"""
    if start_chapter > end_chapter:
        start_chapter, end_chapter = end_chapter, start_chapter
    return [
        item
        for item in debts
        if start_chapter <= item.target_chapter <= end_chapter
    ]


def mark_debts_resolved(
    project_root: Union[str, Path],
    debt_ids: Sequence[str],
) -> List[str]:
    """把指定 debt_id 集合标记为 resolved，并写回文件。

    返回真正状态被翻转的 debt_id 列表（便于调用方日志/断言）。
    """
    if not debt_ids:
        return []
    store = DebtStore(project_root=Path(project_root))
    file = store.load()
    target = set(debt_ids)
    changed: List[str] = []
    for item in file.items:
        if item.debt_id in target and item.status != "resolved":
            item.status = "resolved"
            changed.append(item.debt_id)
    if changed:
        store.save(file)
    return changed


def render_debts_for_plan(debts: Sequence[PropagationDebtItem]) -> str:
    """把 debts 渲染为 markdown，便于 planner 作为硬约束引用。"""
    if not debts:
        return "（无 active propagation debts，本轮无需反向消化）"
    lines = ["## 待消化的反向传播债务（hard constraint）"]
    for item in debts:
        lines.append(
            f"- [{item.debt_id}] target_ch={item.target_chapter} "
            f"severity={item.severity} rule={item.rule_violation}: "
            f"{item.suggested_fix or '（无建议，规划时请自行补齐）'}"
        )
    return "\n".join(lines) + "\n"
