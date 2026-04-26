"""Live-review 病例 ID 分配（薄封装于 case_library._id_alloc.allocate_case_id）。"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ink_writer.case_library._id_alloc import allocate_case_id

_DEFAULT_PREFIX_TEMPLATE = "CASE-LR-{year}-"


def allocate_live_review_id(cases_dir: Path, year: int | None = None) -> str:
    """分配下一个 ``CASE-LR-{year}-NNNN`` 病例 ID。

    Args:
        cases_dir: 病例 yaml 写盘目标目录（实际是 ``data/case_library/cases/live_review``）。
        year: 4 位年份；None 时取当前 UTC 年。

    底层复用 ``case_library._id_alloc.allocate_case_id``，counter file 路径
    形如 ``cases_dir/.id_alloc_case_lr_2026.cnt``，与现有 ``CASE-`` / ``CASE-LEARN-``
    / ``CASE-PROMOTE-`` 自动隔离不串号。
    """
    if year is None:
        year = datetime.now(UTC).year
    prefix = _DEFAULT_PREFIX_TEMPLATE.format(year=year)
    return allocate_case_id(cases_dir, prefix=prefix)


__all__ = ["allocate_live_review_id"]
