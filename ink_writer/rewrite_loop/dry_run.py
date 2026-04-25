"""dry-run 模式控制 + 章节计数器（M3 P1 / spec §5.6 + Q10）。

US-009 (2026-04-25 起)：

* ``is_dry_run(cfg)``：cfg.dry_run.enabled=False → False；counter ≥ observation_chapters
  且 switch_to_block_after=True → False（自动切真阻断）；否则 True。
* counter 持久化在 ``<base_dir>/.dry_run_counter``，默认 ``base_dir=Path("data")``。
* ``increment_dry_run_counter`` 原子地 +1 写回（mkdir parents）。
* ``read_dry_run_counter``：文件不存在或解析失败返 0（保守降级）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_DEFAULT_BASE_DIR = Path("data")
_COUNTER_FILENAME = ".dry_run_counter"


def _resolve_counter_path(base_dir: Path | str | None) -> Path:
    base = Path(base_dir) if base_dir is not None else _DEFAULT_BASE_DIR
    return base / _COUNTER_FILENAME


def read_dry_run_counter(*, base_dir: Path | str | None = None) -> int:
    """读取 dry-run 计数；缺文件或解析失败返 0。"""
    path = _resolve_counter_path(base_dir)
    if not path.exists():
        return 0
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read().strip()
    except OSError:
        return 0
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        return 0
    return max(value, 0)


def increment_dry_run_counter(*, base_dir: Path | str | None = None) -> int:
    """原子地把 counter +1 写回，返回新值。

    父目录若不存在自动创建（mkdir parents=True, exist_ok=True）。
    """
    path = _resolve_counter_path(base_dir)
    current = read_dry_run_counter(base_dir=base_dir)
    new_value = current + 1
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(str(new_value))
    return new_value


def is_dry_run(
    cfg: dict[str, Any],
    *,
    base_dir: Path | str | None = None,
) -> bool:
    """根据 cfg.dry_run 与持久化 counter 共同判定是否仍处 dry-run 期。

    判定顺序：
      1. ``cfg.dry_run.enabled`` 为 False → False。
      2. counter ≥ observation_chapters 且 switch_to_block_after=True → False（自动切真阻断）。
      3. 其它 → True。
    """
    dry_run_cfg = cfg.get("dry_run") if isinstance(cfg, dict) else None
    if not isinstance(dry_run_cfg, dict):
        return False
    if not dry_run_cfg.get("enabled", False):
        return False

    observation = int(dry_run_cfg.get("observation_chapters", 0) or 0)
    switch_after = bool(dry_run_cfg.get("switch_to_block_after", False))

    counter = read_dry_run_counter(base_dir=base_dir)
    return not (switch_after and counter >= observation)
