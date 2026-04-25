"""dry-run 模式控制 + 章节计数器（M3 P1 / spec §5.6 + Q10）。

US-009 (2026-04-25 起)：

* ``is_dry_run(cfg, *, base_dir=None, book=None)``：cfg.dry_run.enabled=False → False；
  counter ≥ observation_chapters 且 switch_to_block_after=True 时进入"准备切真"判定；
  若同时配置了 ``cfg.dry_run.success_criteria.delivered_rate_threshold`` 且传入了
  ``book``，则会读取该 book 的 evidence 聚合 delivered_rate，未达阈值则保持 dry-run
  （即"5 章观察期质量不达标，不切真阻断"）。
* counter 持久化在 ``<base_dir>/.dry_run_counter``，默认 ``base_dir=Path("data")``。
* ``increment_dry_run_counter`` 原子地 +1 写回（mkdir parents），并发安全（Unix
  ``fcntl.flock`` / Win32 ``msvcrt.locking``）。
* ``read_dry_run_counter``：文件不存在或解析失败返 0（保守降级）。
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_DEFAULT_BASE_DIR = Path("data")
_COUNTER_FILENAME = ".dry_run_counter"


def _resolve_counter_path(base_dir: Path | str | None) -> Path:
    base = Path(base_dir) if base_dir is not None else _DEFAULT_BASE_DIR
    return base / _COUNTER_FILENAME


@contextmanager
def _locked_file(path: Path, mode: str):
    """跨平台文件锁：Unix fcntl.flock，Windows msvcrt.locking。

    路径父目录由调用方保证存在；以 ``mode`` 打开后立即取独占锁，with 退出时释放。
    """
    fh = open(path, mode, encoding="utf-8")
    try:
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            except OSError:
                # 无法加锁则降级（保留旧行为，不阻塞调用方）
                pass
            try:
                yield fh
            finally:
                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield fh
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


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
    """并发安全地把 counter +1 写回，返回新值。

    用文件锁包住"读-改-写"，多进程同时调用时不会丢更新；父目录若不存在自动创建。
    """
    path = _resolve_counter_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    # 保证文件存在以便加锁（"a" 模式不截断）
    if not path.exists():
        path.touch()

    with _locked_file(path, "r+") as fh:
        raw = fh.read().strip()
        try:
            current = max(int(raw), 0) if raw else 0
        except ValueError:
            current = 0
        new_value = current + 1
        fh.seek(0)
        fh.truncate()
        fh.write(str(new_value))
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    return new_value


def _observation_quality_passed(
    *,
    book: str,
    base_dir: Path,
    threshold: float,
) -> bool:
    """读取 ``<base_dir>/data/<book>/chapters/*.evidence.json`` 聚合 delivered_rate，
    与阈值对比；当无 evidence 可读时（total=0）保守返回 ``False``（即"还没观察够，别切"）。
    """
    # 局部 import 防循环依赖（dry_run_report 不依赖 dry_run）
    from ink_writer.evidence_chain.dry_run_report import (
        aggregate_dry_run_metrics,
    )

    metrics = aggregate_dry_run_metrics(book=book, base_dir=base_dir)
    total = int(metrics.get("total_chapters", 0) or 0)
    if total <= 0:
        return False
    delivered = int(metrics.get("delivered", 0) or 0)
    rate = delivered / total
    return rate >= float(threshold)


def is_dry_run(
    cfg: dict[str, Any],
    *,
    base_dir: Path | str | None = None,
    book: str | None = None,
) -> bool:
    """根据 cfg.dry_run 与持久化 counter 共同判定是否仍处 dry-run 期。

    判定顺序：
      1. ``cfg.dry_run.enabled`` 为 False → False。
      2. counter < observation_chapters → True（观察期未到）。
      3. counter ≥ observation_chapters 但 ``switch_to_block_after=False`` → True。
      4. 准备 auto-switch；若配置了 ``success_criteria.delivered_rate_threshold``
         且传入了 ``book``，要求观察期内 delivered_rate ≥ 阈值，否则保持 dry-run
         （质量未达标，先别切）。
      5. 否则 → False（auto-switch 真阻断）。

    Args:
        cfg: 章节级运行配置；至少含 ``dry_run.enabled / observation_chapters /
            switch_to_block_after``，可选 ``dry_run.success_criteria.delivered_rate_threshold``。
        base_dir: counter 持久化父目录，默认 ``Path("data")``。
        book: 当前章节所属 book 名；启用质量关卡时必传，否则关卡 skip 不生效。
    """
    dry_run_cfg = cfg.get("dry_run") if isinstance(cfg, dict) else None
    if not isinstance(dry_run_cfg, dict):
        return False
    if not dry_run_cfg.get("enabled", False):
        return False

    observation = int(dry_run_cfg.get("observation_chapters", 0) or 0)
    switch_after = bool(dry_run_cfg.get("switch_to_block_after", False))

    counter = read_dry_run_counter(base_dir=base_dir)
    if counter < observation:
        return True
    if not switch_after:
        return True

    # 走到这里说明已到观察期上限且配置允许 auto-switch；检查质量关卡
    success_criteria = dry_run_cfg.get("success_criteria") or {}
    threshold = success_criteria.get("delivered_rate_threshold") if isinstance(
        success_criteria, dict
    ) else None
    if threshold is not None and book:
        base = Path(base_dir) if base_dir is not None else _DEFAULT_BASE_DIR
        # base_dir 默认就是 "data/"；aggregate_dry_run_metrics 期望的 base 上层是
        # 含 ``data/`` 的目录，因此回退一层
        scan_base = base.parent if base.name == "data" else base
        if not _observation_quality_passed(
            book=book, base_dir=scan_base, threshold=float(threshold)
        ):
            return True  # 质量未达标，保持 dry-run

    return False
