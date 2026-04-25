"""M4 P0 策划期独立 dry-run 计数器（spec §5.4）。

与 M3 章节级 ``dry_run.observation_chapters`` 完全独立——策划期 5 次观察期
只统计 ``ink-init + ink-plan`` 跑次，不与 ink-write 计数互通。

计数文件路径默认 ``data/.planning_dry_run_counter``（仅含一行整数）。
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_COUNTER_PATH = Path("data/.planning_dry_run_counter")
DEFAULT_OBSERVATION_RUNS = 5


def _resolve(counter_path: Path | str | None) -> Path:
    if counter_path is None:
        return DEFAULT_COUNTER_PATH
    return Path(counter_path)


def get_counter(counter_path: Path | str | None = None) -> int:
    """读当前计数；文件不存在或非整数返回 0。"""
    path = _resolve(counter_path)
    if not path.exists():
        return 0
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read().strip()
        return int(raw) if raw else 0
    except (OSError, ValueError):
        return 0


def increment_counter(counter_path: Path | str | None = None) -> int:
    """计数 +1 并落盘；返回更新后的计数。"""
    path = _resolve(counter_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new_count = get_counter(path) + 1
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(str(new_count))
    return new_count


def is_dry_run_active(
    counter_path: Path | str | None = None,
    *,
    observation_runs: int = DEFAULT_OBSERVATION_RUNS,
    enabled: bool = True,
    switch_to_block_after: bool = True,
) -> bool:
    """是否仍在观察期。

    - ``enabled=False`` → 永远 False（直接走真阻断）。
    - ``switch_to_block_after=False`` → 永远 True（永久 dry-run）。
    - 否则 ``counter < observation_runs`` 时为 True。
    """
    if not enabled:
        return False
    if not switch_to_block_after:
        return True
    return get_counter(counter_path) < observation_runs
