#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
编码校验工具 - 检测章节文件中的 U+FFFD 替换字符（乱码）

LLM 流式输出时，多字节 UTF-8 字符偶尔在 chunk 边界被截断，
导致单个中文字符（3 字节）被替换为 3 个 U+FFFD（共 9 字节）。
本工具扫描文件并输出乱码位置及上下文，供 LLM 推断修复。

使用方法：
  python encoding_validator.py --file <path>
  python encoding_validator.py --project-root <path> --chapter <num>

退出码：
  0 = 无乱码
  1 = 检测到乱码
  2 = 参数/文件错误
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from runtime_compat import enable_windows_utf8_stdio, normalize_windows_path

if sys.platform == "win32":
    enable_windows_utf8_stdio()

REPLACEMENT_CHAR = "\ufffd"
CONTEXT_RADIUS = 20


def find_mojibake(text: str) -> List[dict]:
    """扫描文本中的 U+FFFD 替换字符，合并连续出现的为一组。

    Returns:
        列表，每个元素为一处乱码的信息字典：
        {
            "line": 行号（从1开始），
            "column": 列号（从1开始），
            "count": 连续 U+FFFD 数量，
            "context_before": 乱码前的上下文文本,
            "context_after": 乱码后的上下文文本
        }
    """
    if REPLACEMENT_CHAR not in text:
        return []

    results: list[dict] = []
    lines = text.split("\n")

    for line_idx, line in enumerate(lines):
        col = 0
        while col < len(line):
            if line[col] != REPLACEMENT_CHAR:
                col += 1
                continue

            start_col = col
            count = 0
            while col < len(line) and line[col] == REPLACEMENT_CHAR:
                count += 1
                col += 1

            before = line[max(0, start_col - CONTEXT_RADIUS) : start_col]
            after = line[col : col + CONTEXT_RADIUS]

            results.append(
                {
                    "line": line_idx + 1,
                    "column": start_col + 1,
                    "count": count,
                    "context_before": before,
                    "context_after": after,
                }
            )

    return results


def resolve_file_path(args: argparse.Namespace) -> Path:
    """从命令行参数解析目标文件路径。"""
    if args.file:
        return normalize_windows_path(args.file)

    if args.project_root and args.chapter is not None:
        root = normalize_windows_path(args.project_root)
        chapter_padded = str(args.chapter).zfill(4)
        chapter_dir = root / "正文"

        if not chapter_dir.is_dir():
            print(f"错误: 正文目录不存在: {chapter_dir}", file=sys.stderr)
            sys.exit(2)

        # 尝试带标题和不带标题的文件名
        for p in sorted(chapter_dir.glob(f"第{chapter_padded}章*.md")):
            return p

        print(
            f"错误: 未找到第{chapter_padded}章的文件",
            file=sys.stderr,
        )
        sys.exit(2)

    print("错误: 需要 --file 或 --project-root + --chapter", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    parser = argparse.ArgumentParser(description="检测章节文件中的 U+FFFD 乱码")
    parser.add_argument("--file", type=str, help="直接指定文件路径")
    parser.add_argument("--project-root", type=str, help="项目根目录")
    parser.add_argument("--chapter", type=int, help="章节号")
    parser.add_argument(
        "--json", action="store_true", default=True, help="JSON 格式输出（默认）"
    )
    args = parser.parse_args()

    file_path = resolve_file_path(args)

    if not file_path.is_file():
        print(f"错误: 文件不存在: {file_path}", file=sys.stderr)
        sys.exit(2)

    text = file_path.read_text(encoding="utf-8")
    issues = find_mojibake(text)

    output = {
        "file": str(file_path),
        "has_mojibake": len(issues) > 0,
        "count": len(issues),
        "issues": issues,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
