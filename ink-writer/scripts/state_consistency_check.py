#!/usr/bin/env python3
"""state-db 一致性自动修复（task #20251130 Bug C 治理）

历史现象（cipher 实测 2026-04-30）：
  Step 5 Data Agent 跑到一半被中断（用户 ⌃C / watchdog SIGTERM），导致：
  - chapter 表 / appearances / review_metrics / summaries 已写入
  - state.json.progress.current_chapter **没更新**
  ↓
  下次 ink-auto 启动看 state.current=N → 觉得"还要写第 N+1 章"，
  但其实 db 已经有第 N+1 章数据 → 重写一遍，浪费时间 + 数据冲突。

本脚本：
  以 db 实际章节数为权威，自动修正 state.json.progress.current_chapter。
  在 ink-auto.sh 启动时和每次 ink-write 进入前调用，防止状态漂移循环。

策略（v2，2026-04-30 修订）：
  - **优先用章节文件**作为权威源——文件存在 = 至少 Step 2A 落盘了，是最直接
    的"已完成"证据。db 表可能因 Step 5 中断没写入，但文件不会无故消失。
  - 文件不存在时，再退到 summaries（Step 5 早期产物）
  - 都没有再退到 db.chapters 表（最不可靠，Step 5 收尾才写）
  - 最后才用 db.appearances 兜底

历史教训（v1 bug）：
  v1 取 4 来源**最小值**，cipher 实测撞墙：chapters 表只有 ch1 但章节文件
  ch1-4 齐全 → state.current 被改成 1 → ink-auto 反复重写 ch2/3/4。
  v2 改为"章节文件作权威"——文件比表更可信。

退出码：
  0 - 一致或修复成功
  1 - 有错误（无法读取等）
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

# US-010 Windows UTF-8 stdio 兜底
try:
    _scripts_dir = Path(__file__).resolve().parent
    if str(_scripts_dir) not in sys.path:
        sys.path.insert(0, str(_scripts_dir))
    from runtime_compat import enable_windows_utf8_stdio
    enable_windows_utf8_stdio(skip_in_pytest=True)
except Exception:
    pass


def _max_chapter_from_chapters_table(db_path: Path) -> int | None:
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(str(db_path)) as con:
            cur = con.execute("SELECT MAX(chapter) FROM chapters")
            row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else None
    except sqlite3.Error:
        return None


def _max_chapter_from_appearances(db_path: Path) -> int | None:
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(str(db_path)) as con:
            cur = con.execute("SELECT MAX(chapter) FROM appearances")
            row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else None
    except sqlite3.Error:
        return None


def _max_chapter_from_summaries(project_root: Path) -> int | None:
    summaries_dir = project_root / ".ink" / "summaries"
    if not summaries_dir.is_dir():
        return None
    nums: list[int] = []
    for p in summaries_dir.glob("ch*.md"):
        m = re.match(r"ch(\d{4})\.md$", p.name)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) if nums else None


def _max_chapter_from_chapter_files(project_root: Path) -> int | None:
    body_dir = project_root / "正文"
    if not body_dir.is_dir():
        return None
    nums: list[int] = []
    for p in body_dir.glob("第*章*.md"):
        m = re.match(r"第(\d+)章", p.name)
        if m:
            try:
                nums.append(int(m.group(1)))
            except ValueError:
                continue
    return max(nums) if nums else None


def detect_truth(project_root: Path) -> tuple[int | None, dict[str, int | None]]:
    """探测项目里"实际写到第几章"。返回 (truth, sources_dict)。

    策略（v2，2026-04-30）：**章节文件最大数 = 权威**。
    理由：
      - Step 2A 起草成功 → 章节文件落盘（最直接的"已完成"证据）
      - Step 3-5 可能中断 → db 表 / summaries 滞后
      - 章节文件不会无故消失，是最稳定的真相源
    回退顺序（章节文件不可用时）：summaries → chapters → appearances。

    历史教训（v1 bug）：v1 取最小值导致 chapters 表只有 ch1 但章节文件 ch1-4
    齐全时把 state.current 改回 1，ink-auto 重写 ch2/3/4 循环。
    """
    db_path = project_root / ".ink" / "index.db"
    sources = {
        "chapters_table": _max_chapter_from_chapters_table(db_path),
        "appearances": _max_chapter_from_appearances(db_path),
        "summaries": _max_chapter_from_summaries(project_root),
        "chapter_files": _max_chapter_from_chapter_files(project_root),
    }
    # 按权威性优先级递减选取——章节文件最权威
    for key in ("chapter_files", "summaries", "chapters_table", "appearances"):
        if sources[key] is not None:
            return sources[key], sources
    return None, sources


def repair_state(project_root: Path, *, dry_run: bool = False) -> tuple[bool, str]:
    """检测 state.json 与 db 真相是否一致；不一致就修。

    Returns:
        (changed, message)
    """
    state_path = project_root / ".ink" / "state.json"
    if not state_path.exists():
        return False, f"state.json 不存在: {state_path}"

    truth, sources = detect_truth(project_root)
    if truth is None:
        return False, "无任何章节产物（新项目），跳过一致性检查"

    try:
        with state_path.open(encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"state.json 读取失败: {exc}"

    progress = state.get("progress") or {}
    current = progress.get("current_chapter")
    if current is None:
        current = 0

    # 来源细节诊断行
    src_detail = ", ".join(
        f"{k}={v}" for k, v in sources.items() if v is not None
    )

    if current == truth:
        return False, f"✓ state ↔ db 一致 (current_chapter={current}, sources: {src_detail})"

    # 不一致 → 修
    msg_diff = (
        f"⚠️  不一致：state.current_chapter={current}, db 真相={truth}（{src_detail}）"
    )
    if dry_run:
        return False, f"{msg_diff} [dry-run，未修改]"

    progress["current_chapter"] = truth
    state["progress"] = progress

    # 备份原 state.json
    backup = state_path.parent / "backups" / f"state.before_consistency_fix_{truth}.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    try:
        backup.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # 备份失败不阻断

    try:
        with state_path.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        return False, f"state.json 写入失败: {exc}"

    return True, f"🔧 已修复：current_chapter {current} → {truth}（备份在 {backup.name}）"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="state-db 一致性自动修复")
    parser.add_argument(
        "--project-root", required=True, help="书项目根目录（含 .ink/）"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="只检测不修改，输出诊断信息"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="一致时不输出（只在不一致或错误时打印）"
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).expanduser()
    if not project_root.is_dir():
        print(f"❌ project_root 不存在: {project_root}", file=sys.stderr)
        return 1

    changed, msg = repair_state(project_root, dry_run=args.dry_run)
    if args.quiet and msg.startswith("✓"):
        return 0
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
