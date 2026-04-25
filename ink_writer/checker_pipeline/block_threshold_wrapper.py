"""block_threshold_wrapper — 升级现有 prompt-based checker 的输出结构 (spec §5.1).

不动现有 checker prompt 算法；wrapper 接收 score → 加 blocked / cases_hit /
would_have_blocked 字段，由 rewrite_loop orchestrator 统一消费。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckerOutcome:
    checker_id: str
    score: float
    block_threshold: float
    blocked: bool
    would_have_blocked: bool = False
    cases_hit: list[str] = field(default_factory=list)
    notes: str = ""


def _query_cases_by_tags(case_store: Any, tags: Any) -> list[str]:
    """Query case_library by tags → cases_hit. 兼容 list[str] / list[{tag:str}]."""
    if case_store is None or not tags:
        return []
    if not hasattr(case_store, "list_ids_by_tag"):
        return []
    try:
        all_ids: set[str] = set()
        for entry in tags:
            if isinstance(entry, dict):
                tag = entry.get("tag")
            else:
                tag = entry
            if not tag:
                continue
            ids = case_store.list_ids_by_tag(tag)
            all_ids.update(ids or [])
        return sorted(all_ids)
    except Exception:  # noqa: BLE001
        return []


def apply_block_threshold(
    *,
    checker_id: str,
    score: float,
    cfg: dict,
    is_dry_run: bool,
    case_store: Any | None,
) -> CheckerOutcome:
    """包装 score 为 CheckerOutcome：加 blocked + would_have_blocked + cases_hit。

    - 未配置的 checker_id：blocked=False + notes 标记“not in thresholds yaml”
    - is_dry_run=True：blocked 永远 False，但 would_have_blocked 反映真实判定
    - cases_hit：仅当 raw_blocked=True 时查询，避免无谓 IO
    """
    checker_cfg = cfg.get(checker_id)
    if checker_cfg is None:
        return CheckerOutcome(
            checker_id=checker_id,
            score=score,
            block_threshold=0.0,
            blocked=False,
            would_have_blocked=False,
            cases_hit=[],
            notes=f"checker '{checker_id}' not in thresholds yaml; using default (no block)",
        )

    block_threshold = float(checker_cfg.get("block_threshold", 0.0))
    bound_cases = checker_cfg.get("bound_cases") or checker_cfg.get("bound_cases_tags") or []

    raw_blocked = score < block_threshold
    blocked = raw_blocked and not is_dry_run
    would_have_blocked = raw_blocked

    cases_hit = _query_cases_by_tags(case_store, bound_cases) if raw_blocked else []

    return CheckerOutcome(
        checker_id=checker_id,
        score=score,
        block_threshold=block_threshold,
        blocked=blocked,
        would_have_blocked=would_have_blocked,
        cases_hit=cases_hit,
        notes="",
    )
