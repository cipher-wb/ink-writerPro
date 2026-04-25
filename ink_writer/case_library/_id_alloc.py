"""并发安全的 case ID 分配（P1 修复 — review §二 #6）。

原 ``_next_learn_id`` / ``_next_promote_id`` 是 glob+max+1，无锁；多进程同时跑
``ink-learn --auto-case-from-failure`` 会撞 ID 互相覆盖。

本模块用 per-prefix 计数器文件 + 跨平台文件锁串行化分配；同时每次分配都会再
glob 一次现存 yaml 取 max 兜底（防止外部手工 PR 添加的 case 让计数器落后）。
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _locked_file(path: Path, mode: str):
    """跨平台独占文件锁；与 rewrite_loop/dry_run.py 内的实现行为一致。"""
    fh = open(path, mode, encoding="utf-8")
    try:
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            except OSError:
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


def _scan_max(cases_dir: Path, prefix: str) -> int:
    max_seen = 0
    for path in cases_dir.glob(f"{prefix}*.yaml"):
        suffix = path.stem.removeprefix(prefix)
        if suffix.isdigit():
            max_seen = max(max_seen, int(suffix))
    return max_seen


def allocate_case_id(cases_dir: Path, prefix: str) -> str:
    """并发安全分配下一个 ``{prefix}NNNN`` ID。

    Args:
        cases_dir: 写盘目标目录；不存在自动创建。
        prefix: 形如 ``"CASE-LEARN-"`` / ``"CASE-PROMOTE-"`` 的前缀（含尾部 -）。

    流程：
      1. 计数器文件 ``cases_dir/.id_alloc_<sanitized_prefix>.cnt``；首次创建时
         初始化为现存 max。
      2. 上独占锁，读 counter，再 glob 一次取 max 兜底，取 ``max(counter, glob_max) + 1``。
      3. 把新值写回 counter，释放锁返回。
    """
    cases_dir.mkdir(parents=True, exist_ok=True)
    sanitized = prefix.strip("-").replace("-", "_") or "case"
    counter_path = cases_dir / f".id_alloc_{sanitized}.cnt"

    if not counter_path.exists():
        # 首次：以现存 yaml 的 max 初始化
        counter_path.write_text(str(_scan_max(cases_dir, prefix)), encoding="utf-8")

    with _locked_file(counter_path, "r+") as fh:
        raw = fh.read().strip()
        try:
            cur = max(int(raw), 0) if raw else 0
        except ValueError:
            cur = 0
        # 再 glob 一次防外部手工添加 case 让 counter 落后
        cur = max(cur, _scan_max(cases_dir, prefix))
        new_num = cur + 1
        fh.seek(0)
        fh.truncate()
        fh.write(str(new_num))
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass

    return f"{prefix}{new_num:04d}"


__all__ = ["allocate_case_id"]
