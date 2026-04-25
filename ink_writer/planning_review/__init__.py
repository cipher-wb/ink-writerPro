"""M4 P0 上游策划期审查编排层（spec §5）。

ink-init Step 99 跑 4 个 checker（genre-novelty / golden-finger-spec /
naming-style / protagonist-motive），ink-plan Step 99 跑 3 个 checker
（golden-finger-timing / protagonist-agency-skeleton / chapter-hook-density），
两次结果按 stage 名合并写入 ``<base_dir>/<book>/planning_evidence_chain.json``。

入口
----
- ``run_ink_init_review`` — ink-init 4 checker 编排
- ``run_ink_plan_review`` — ink-plan 3 checker 编排
- ``dry_run.{get_counter,increment_counter,is_dry_run_active}`` — 独立 5 次观察期
- ``dry_run_report.generate_planning_dry_run_report`` — 聚合所有书的策划期 evidence
"""

from __future__ import annotations

from ink_writer.planning_review.dry_run import (
    get_counter,
    increment_counter,
    is_dry_run_active,
)
from ink_writer.planning_review.dry_run_report import (
    generate_planning_dry_run_report,
)
from ink_writer.planning_review.ink_init_review import run_ink_init_review
from ink_writer.planning_review.ink_plan_review import run_ink_plan_review

__all__ = [
    "generate_planning_dry_run_report",
    "get_counter",
    "increment_counter",
    "is_dry_run_active",
    "run_ink_init_review",
    "run_ink_plan_review",
]
