"""并发安全的 case ID 分配（P1 修复 — review §二 #6）。

原 ``_next_learn_id`` / ``_next_promote_id`` 是 glob+max+1，无锁；多进程同时跑
``ink-learn --auto-case-from-failure`` 会撞 ID 互相覆盖。

本模块用 per-prefix 计数器文件 + 跨平台文件锁串行化分配；同时每次分配都会再
glob 一次现存 yaml 取 max 兜底（防止外部手工 PR 添加的 case 让计数器落后）。
"""

from __future__ import annotations

import os
from pathlib import Path

from ink_writer._compat.locking import locked_file


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

    流程（US-004 — review §三 #6）：
      1. 计数器文件 ``cases_dir/.id_alloc_<sanitized_prefix>.cnt``。
      2. 以 ``"a+"`` 模式开 + 上独占锁；``"a+"`` 在不存在时自动创建空文件，
         初始化与读取均在锁内串行——避免旧实现"先 write_text 再上锁"窗口期
         里其他进程读到不完整状态（旧实现只靠 glob 兜底救场，可读性差）。
      3. ``fh.seek(0)`` 读 raw；空则用 ``_scan_max`` 取 glob max 初始化。
      4. 与 ``_scan_max`` 再取一次 max 防外部手工添加的 yaml 让 counter 落后。
      5. ``fh.seek(0) + truncate + write`` 写回 counter。注：``"a+"`` 在 Unix 下
         O_APPEND 写总是 seek 到 EOF 再写——但 truncate 让 EOF=0，所以写仍落在
         位置 0；Windows 上 truncate 把指针置 EOF 同样落 0。
    """
    cases_dir.mkdir(parents=True, exist_ok=True)
    sanitized = prefix.strip("-").replace("-", "_") or "case"
    counter_path = cases_dir / f".id_alloc_{sanitized}.cnt"

    with locked_file(counter_path, "a+") as fh:
        fh.seek(0)
        raw = fh.read().strip()
        try:
            stored = max(int(raw), 0) if raw else 0
        except ValueError:
            stored = 0
        cur = max(stored, _scan_max(cases_dir, prefix))
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
