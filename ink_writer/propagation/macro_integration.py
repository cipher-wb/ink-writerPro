"""FIX-17 P4c: macro-review propagation 触发器与执行器。

ink-macro-review skill 在 Tier2 入口调用 :func:`should_run` 判断是否触发，
若触发则调用 :func:`run_propagation` 执行 drift 扫描 + 落盘 + stderr 摘要。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, TextIO, Union

from ink_writer.propagation.debt_store import DebtStore
from ink_writer.propagation.drift_detector import detect_drifts
from ink_writer.propagation.models import PropagationDebtItem

DEFAULT_INTERVAL = 50
INTERVAL_ENV = "INK_PROPAGATION_INTERVAL"


def get_interval(env: Optional[Mapping[str, str]] = None) -> int:
    """读取 INK_PROPAGATION_INTERVAL（缺省/非法 → 50）。"""
    source = env if env is not None else os.environ
    raw = source.get(INTERVAL_ENV)
    if raw is None or str(raw).strip() == "":
        return DEFAULT_INTERVAL
    try:
        value = int(str(raw).strip())
    except ValueError:
        return DEFAULT_INTERVAL
    return value if value > 0 else DEFAULT_INTERVAL


def should_run(
    current_chapter: int,
    *,
    interval: Optional[int] = None,
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """current_chapter > 0 且能被 interval 整除时触发。"""
    if current_chapter <= 0:
        return False
    eff_interval = interval if interval is not None else get_interval(env)
    if eff_interval <= 0:
        return False
    return current_chapter % eff_interval == 0


def _window_range(current_chapter: int, interval: int) -> range:
    start = max(1, current_chapter - interval + 1)
    return range(start, current_chapter + 1)


def run_propagation(
    project_root: Union[str, Path],
    current_chapter: int,
    *,
    interval: Optional[int] = None,
    env: Optional[Mapping[str, str]] = None,
    records: Optional[Mapping[int, Mapping[str, Any]]] = None,
    stderr: Optional[TextIO] = None,
) -> List[PropagationDebtItem]:
    """扫描最近 interval 章 → save_debts → stderr 摘要。返回 drift 列表。"""
    eff_interval = interval if interval is not None else get_interval(env)
    chapters: Iterable[int] = _window_range(current_chapter, eff_interval)
    drifts = detect_drifts(project_root, chapters, records=records)

    store = DebtStore(project_root=Path(project_root))
    if drifts:
        store.save_debts(drifts)

    rel_path = store.path
    try:
        rel_path = store.path.relative_to(Path(project_root))
    except ValueError:
        pass

    stream = stderr if stderr is not None else sys.stderr
    print(
        f"Propagation: {len(drifts)} drifts detected, saved to {rel_path}",
        file=stream,
    )
    return drifts
