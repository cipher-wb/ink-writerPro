#!/usr/bin/env python3
"""US-LR-004: 单文件冒烟脚本 — 把 1 份直播稿原始文本抽成 jsonl。

Usage:
    python scripts/live-review/extract_one.py \
        --input ~/Desktop/星河审稿/BV12yBoBAEEn_raw.txt \
        --out reports/live-review/BV12yBoBAEEn.jsonl

退出码:
    0  成功
    1  ExtractionError（LLM 输出不合法 / schema 违反）
    2  输入文件不存在 / bvid 无法从文件名提取且未传 --bvid
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
import re  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ink_writer.live_review.extractor import (  # noqa: E402
    ExtractionError,
    extract_from_text,
)

_BVID_FILENAME_RE = re.compile(r"^(BV[\w]+)_raw\.txt$")


def _infer_bvid(input_path: Path) -> str | None:
    m = _BVID_FILENAME_RE.match(input_path.name)
    return m.group(1) if m else None


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Extract one Bilibili live-review raw transcript into jsonl."
    )
    p.add_argument("--bvid", help="BV id；未传时从 --input 文件名自动提取")
    p.add_argument("--input", required=True, help="原始 raw.txt 路径")
    p.add_argument("--out", required=True, help="输出 jsonl 路径")
    p.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="LLM 模型 (默认 claude-sonnet-4-6)",
    )
    p.add_argument(
        "--mock-llm",
        dest="mock_llm",
        help="测试用 mock LLM 输出 fixture json 路径",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"[extract_one] input not found: {input_path}", file=sys.stderr)
        return 2

    bvid = args.bvid or _infer_bvid(input_path)
    if not bvid:
        print(
            f"[extract_one] cannot infer bvid from filename {input_path.name!r}; "
            "pass --bvid explicitly",
            file=sys.stderr,
        )
        return 2

    raw_text = input_path.read_text(encoding="utf-8")
    mock_response = None
    if args.mock_llm:
        mock_response = json.loads(Path(args.mock_llm).read_text(encoding="utf-8"))

    try:
        records = extract_from_text(
            raw_text,
            bvid=bvid,
            source_path=str(input_path),
            model=args.model,
            mock_response=mock_response,
        )
    except ExtractionError as exc:
        print(f"[extract_one] extraction failed: {exc}", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"[extract_one] {bvid}: {len(records)} novels → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
