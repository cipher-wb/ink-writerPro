#!/usr/bin/env python3
"""US-LR-010: 规则候选交互式审核 CLI。

读取 US-LR-009 输出的 ``rule_candidates.json``，逐条展示候选给用户判断；
y/n/s/q 写回 ``approved`` 字段，s 跳过保留 None，q 立即退出（保存当前进度）。

CLI:
    python3 scripts/live-review/review_rule_candidates.py \\
        --candidates data/live-review/rule_candidates.json

按键说明:
    y / yes      → 标 approved=True，下一条
    n / no       → 标 approved=False，下一条
    s / skip     → 不修改 approved（保留 null），下一条
    q / quit     → 立即退出（保存当前已处理的项）

退出码:
    0  正常完成或用户主动 q 退出
    1  candidates 文件不存在或解析失败
"""
from __future__ import annotations

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio

_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    "../../ink-writer/scripts",
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_CANDIDATES = _REPO_ROOT / "data" / "live-review" / "rule_candidates.json"

_VALID_RESPONSES = {"y", "yes", "n", "no", "s", "skip", "q", "quit"}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Interactively review live-review rule candidates (y/n/s/q).",
    )
    p.add_argument(
        "--candidates",
        default=str(_DEFAULT_CANDIDATES),
        help="rule_candidates.json 路径（US-LR-009 产出）",
    )
    return p


def _load_candidates(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"candidates file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"candidates root must be array, got {type(data).__name__}")
    return data


def _save_candidates(path: Path, data: list[dict]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _format_card(idx: int, total: int, cand: dict) -> str:
    dup = cand.get("dup_with")
    dup_str = ", ".join(dup) if dup else "(none)"
    bvids = cand.get("source_bvids", [])
    return (
        f"\n[{idx + 1}/{total}] {cand.get('id', '?')}  category={cand.get('category')}"
        f"  severity={cand.get('severity')}  applies_to={cand.get('applies_to')}\n"
        f"  rule: {cand.get('rule')}\n"
        f"  why : {cand.get('why')}\n"
        f"  dup_with    : {dup_str}\n"
        f"  source_bvids: {bvids}\n"
        f"  >> [y]es / [n]o / [s]kip / [q]uit ? "
    )


def _read_response(prompt: str) -> str:
    """读 stdin 一行；EOF 视为 quit。"""
    sys.stdout.write(prompt)
    sys.stdout.flush()
    line = sys.stdin.readline()
    if line == "":  # EOF
        return "q"
    return line.strip().lower()


def review(
    candidates: list[dict],
    *,
    save_callback,
) -> tuple[int, int, int]:
    """主循环；返回 (approved_count, rejected_count, skipped_count)。

    每条响应后立即调 save_callback(candidates) 写盘，确保 q/异常时不丢进度。
    已有 approved!=None 的项跳过（resume 友好）。
    """
    total = len(candidates)
    approved_count = rejected_count = skipped_count = 0

    for i, cand in enumerate(candidates):
        if cand.get("approved") is not None:
            continue
        while True:
            resp = _read_response(_format_card(i, total, cand))
            if resp in _VALID_RESPONSES:
                break
            sys.stdout.write(
                f"  ! invalid input {resp!r}; expected one of "
                f"y/yes/n/no/s/skip/q/quit\n"
            )
            sys.stdout.flush()
        if resp in {"y", "yes"}:
            cand["approved"] = True
            approved_count += 1
            save_callback(candidates)
        elif resp in {"n", "no"}:
            cand["approved"] = False
            rejected_count += 1
            save_callback(candidates)
        elif resp in {"s", "skip"}:
            skipped_count += 1
        elif resp in {"q", "quit"}:
            sys.stdout.write("[review] quit — saving progress and exiting.\n")
            sys.stdout.flush()
            return approved_count, rejected_count, skipped_count
    return approved_count, rejected_count, skipped_count


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    cand_path = Path(args.candidates)
    try:
        candidates = _load_candidates(cand_path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"[review_rule_candidates] FAIL: {exc}", file=sys.stderr)
        return 1

    def _save(data: list[dict]) -> None:
        _save_candidates(cand_path, data)

    approved, rejected, skipped = review(candidates, save_callback=_save)
    # 全部跑完后再保存一次，确保末尾状态一定写盘。
    _save(candidates)
    print(
        f"[review_rule_candidates] done — approved={approved} "
        f"rejected={rejected} skipped={skipped} → {cand_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
