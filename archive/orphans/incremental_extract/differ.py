"""实体状态差异计算：对比前后章节的实体快照，仅提取变更部分。

工作流:
1. 加载 chapter N-1 的实体快照（from index.db state_changes + entities）
2. 对比 chapter N 的提取结果
3. 输出 DiffResult：new_entities, changed_entities, unchanged_entities
4. data-agent 仅对 new + changed 执行深度提取，跳过 unchanged
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ink_writer.incremental_extract.config import IncrementalExtractConfig


class DiffType(Enum):
    NEW = "new"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    REMOVED = "removed"


@dataclass
class EntityDiff:
    entity_id: str
    entity_type: str
    diff_type: DiffType
    changed_fields: list[str] = field(default_factory=list)
    old_values: dict[str, Any] = field(default_factory=dict)
    new_values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "diff_type": self.diff_type.value,
        }
        if self.changed_fields:
            d["changed_fields"] = self.changed_fields
        if self.old_values:
            d["old_values"] = self.old_values
        if self.new_values:
            d["new_values"] = self.new_values
        return d


@dataclass
class DiffResult:
    chapter: int
    prior_chapter: int
    new_entities: list[EntityDiff] = field(default_factory=list)
    changed_entities: list[EntityDiff] = field(default_factory=list)
    unchanged_entities: list[EntityDiff] = field(default_factory=list)
    removed_entities: list[EntityDiff] = field(default_factory=list)

    @property
    def total_entities(self) -> int:
        return (
            len(self.new_entities)
            + len(self.changed_entities)
            + len(self.unchanged_entities)
            + len(self.removed_entities)
        )

    @property
    def extraction_needed(self) -> list[EntityDiff]:
        return self.new_entities + self.changed_entities

    @property
    def skip_count(self) -> int:
        return len(self.unchanged_entities)

    @property
    def savings_pct(self) -> float:
        if self.total_entities == 0:
            return 0.0
        return (self.skip_count / self.total_entities) * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter": self.chapter,
            "prior_chapter": self.prior_chapter,
            "total_entities": self.total_entities,
            "new": len(self.new_entities),
            "changed": len(self.changed_entities),
            "unchanged": len(self.unchanged_entities),
            "removed": len(self.removed_entities),
            "savings_pct": round(self.savings_pct, 1),
            "extraction_needed": [e.to_dict() for e in self.extraction_needed],
        }


def compute_entity_diff(
    current_entities: list[dict[str, Any]],
    prior_entities: list[dict[str, Any]],
    chapter: int,
    prior_chapter: int,
    config: Optional[IncrementalExtractConfig] = None,
) -> DiffResult:
    """Compare current chapter entities against prior chapter state.

    Args:
        current_entities: Entities detected in the current chapter.
            Each dict must have 'entity_id', 'entity_type', and optional field data.
        prior_entities: Entity state from the prior chapter (from index.db).
            Same format.
        chapter: Current chapter number.
        prior_chapter: Prior chapter number.
        config: Configuration for diff behavior.

    Returns:
        DiffResult with categorized entities.
    """
    if config is None:
        config = IncrementalExtractConfig()

    result = DiffResult(chapter=chapter, prior_chapter=prior_chapter)

    prior_map: dict[str, dict[str, Any]] = {}
    for e in prior_entities:
        eid = e.get("entity_id", "")
        if eid:
            prior_map[eid] = e

    current_ids: set[str] = set()
    for entity in current_entities:
        eid = entity.get("entity_id", "")
        etype = entity.get("entity_type", "unknown")
        if not eid:
            continue

        current_ids.add(eid)

        if eid not in prior_map:
            result.new_entities.append(
                EntityDiff(
                    entity_id=eid,
                    entity_type=etype,
                    diff_type=DiffType.NEW,
                    new_values=_extract_fields(entity),
                )
            )
            continue

        if config.always_extract_protagonist and entity.get("is_protagonist"):
            result.changed_entities.append(
                EntityDiff(
                    entity_id=eid,
                    entity_type=etype,
                    diff_type=DiffType.CHANGED,
                    changed_fields=["protagonist_always_extract"],
                )
            )
            continue

        prior = prior_map[eid]
        changed_fields, old_vals, new_vals = _diff_fields(prior, entity)

        if changed_fields:
            result.changed_entities.append(
                EntityDiff(
                    entity_id=eid,
                    entity_type=etype,
                    diff_type=DiffType.CHANGED,
                    changed_fields=changed_fields,
                    old_values=old_vals,
                    new_values=new_vals,
                )
            )
        else:
            result.unchanged_entities.append(
                EntityDiff(
                    entity_id=eid,
                    entity_type=etype,
                    diff_type=DiffType.UNCHANGED,
                )
            )

    for eid, prior in prior_map.items():
        if eid not in current_ids:
            result.removed_entities.append(
                EntityDiff(
                    entity_id=eid,
                    entity_type=prior.get("entity_type", "unknown"),
                    diff_type=DiffType.REMOVED,
                )
            )

    return result


_SKIP_FIELDS = {
    "entity_id",
    "entity_type",
    "is_protagonist",
    "tier",
    "created_at",
    "updated_at",
}


def _extract_fields(entity: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entity.items() if k not in _SKIP_FIELDS}


def _diff_fields(
    prior: dict[str, Any], current: dict[str, Any]
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    changed: list[str] = []
    old_vals: dict[str, Any] = {}
    new_vals: dict[str, Any] = {}

    all_keys = set(prior.keys()) | set(current.keys())
    for key in all_keys:
        if key in _SKIP_FIELDS:
            continue
        old_val = prior.get(key)
        new_val = current.get(key)
        if _normalize(old_val) != _normalize(new_val):
            changed.append(key)
            if old_val is not None:
                old_vals[key] = old_val
            if new_val is not None:
                new_vals[key] = new_val

    return changed, old_vals, new_vals


def _normalize(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, dict):
        return json.dumps(val, sort_keys=True, ensure_ascii=False)
    if isinstance(val, list):
        return json.dumps(val, sort_keys=True, ensure_ascii=False)
    return val
