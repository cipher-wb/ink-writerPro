#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大纲钩子契约回填脚本

扫描已有大纲文件，为缺少 `钩子契约` 字段的章节自动补充 best-guess 值。
基于现有 `钩子` 字段推断类型，锚点默认设为下一章，兑现摘要从钩子描述缩写。

用法:
    python scripts/patch_outline_hook_contract.py --project-root <path> [--dry-run]
"""

from __future__ import annotations

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio
_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    '../ink-writer/scripts',
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass
import argparse
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ink-writer" / "scripts"))

from hook_contract import (
    VALID_HOOK_TYPES,
    _CONTRACT_LINE_RE,
    extract_hook_contract_from_outline,
)

_HOOK_LINE_RE = re.compile(
    r"([·\-\*]\s*钩子\s*[:：]\s*)(.+)", re.UNICODE
)

_CHAPTER_SPLIT_RE = re.compile(r"(?=###\s*第\s*\d+\s*章[：:])")

_CHAPTER_NUM_RE = re.compile(r"###\s*第\s*(\d+)\s*章[：:]")

HOOK_KEYWORD_MAP = {
    "悬念": "mystery",
    "危机": "crisis",
    "承诺": "emotion",
    "情绪": "emotion",
    "选择": "choice",
    "渴望": "desire",
    "mystery": "mystery",
    "crisis": "crisis",
    "emotion": "emotion",
    "choice": "choice",
    "desire": "desire",
}


def guess_hook_type(hook_text: str) -> str:
    """Guess hook type from the existing 钩子 field text."""
    hook_lower = hook_text.lower()
    for keyword, hook_type in HOOK_KEYWORD_MAP.items():
        if keyword in hook_lower:
            return hook_type
    return "mystery"


def guess_payoff_summary(hook_text: str) -> str:
    """Extract a ≤20 char summary from hook text."""
    cleaned = re.sub(r"^(悬念钩|危机钩|承诺钩|情绪钩|选择钩|渴望钩)\s*[-—]\s*", "", hook_text).strip()
    if len(cleaned) > 20:
        cleaned = cleaned[:18] + "…"
    return cleaned or "待补充"


def patch_chapter_block(block: str, chapter_num: int, total_chapters: int) -> tuple[str, bool]:
    """Add hook_contract line to a chapter block if missing.

    Returns (patched_block, was_modified).
    """
    if extract_hook_contract_from_outline(block) is not None:
        return block, False

    hook_match = _HOOK_LINE_RE.search(block)
    if not hook_match:
        anchor = min(chapter_num + 1, total_chapters)
        contract_line = (
            f"- 钩子契约: 类型=mystery | 兑现锚点=第{anchor}章 | 兑现摘要=待补充"
        )
    else:
        hook_text = hook_match.group(2).strip()
        hook_type = guess_hook_type(hook_text)
        anchor = min(chapter_num + 1, total_chapters)
        summary = guess_payoff_summary(hook_text)
        contract_line = (
            f"- 钩子契约: 类型={hook_type} | 兑现锚点=第{anchor}章 | 兑现摘要={summary}"
        )

    insert_pos = _find_insert_position(block)
    patched = block[:insert_pos] + contract_line + "\n" + block[insert_pos:]
    return patched, True


def _find_insert_position(block: str) -> int:
    """Find position to insert hook_contract (after 钩子 line, or end of block)."""
    hook_match = _HOOK_LINE_RE.search(block)
    if hook_match:
        line_end = block.find("\n", hook_match.end())
        if line_end == -1:
            return len(block)
        return line_end + 1

    return len(block.rstrip()) + 1


def patch_outline_file(filepath: Path, dry_run: bool = False) -> int:
    """Patch a single outline file. Returns number of chapters modified."""
    content = filepath.read_text(encoding="utf-8")
    blocks = _CHAPTER_SPLIT_RE.split(content)

    all_chapter_nums = []
    for b in blocks:
        m = _CHAPTER_NUM_RE.match(b.strip())
        if m:
            all_chapter_nums.append(int(m.group(1)))
    total_chapters = max(all_chapter_nums) if all_chapter_nums else 999

    modified_count = 0
    new_blocks = []
    for block in blocks:
        header = _CHAPTER_NUM_RE.match(block.strip())
        if not header:
            new_blocks.append(block)
            continue

        chapter_num = int(header.group(1))
        patched, was_modified = patch_chapter_block(block, chapter_num, total_chapters)
        new_blocks.append(patched)
        if was_modified:
            modified_count += 1

    if modified_count > 0 and not dry_run:
        backup = filepath.with_suffix(".md.bak.pre_hook_contract")
        shutil.copy2(filepath, backup)
        filepath.write_text("".join(new_blocks), encoding="utf-8")

    return modified_count


def patch_project(project_root: Path, dry_run: bool = False) -> dict:
    """Patch all outline files in a project."""
    outline_dir = project_root / "大纲"
    results = {"files_scanned": 0, "files_modified": 0, "chapters_patched": 0}

    if not outline_dir.exists():
        return results

    for filepath in sorted(outline_dir.glob("*详细大纲*.md")):
        results["files_scanned"] += 1
        count = patch_outline_file(filepath, dry_run=dry_run)
        if count > 0:
            results["files_modified"] += 1
            results["chapters_patched"] += count
            action = "would patch" if dry_run else "patched"
            print(f"  📝 {filepath.name}: {action} {count} chapters")

    return results


def main():
    parser = argparse.ArgumentParser(description="大纲钩子契约回填")
    parser.add_argument("--project-root", type=str, required=True)
    parser.add_argument("--dry-run", action="store_true", help="只预览不修改")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    print(f"🔍 扫描项目: {project_root}")

    results = patch_project(project_root, dry_run=args.dry_run)
    print(f"\n{'🔎 预览' if args.dry_run else '✅ 完成'}: "
          f"扫描 {results['files_scanned']} 文件, "
          f"修改 {results['files_modified']} 文件, "
          f"补充 {results['chapters_patched']} 章钩子契约")


if __name__ == "__main__":
    main()
