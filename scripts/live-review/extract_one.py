#!/usr/bin/env python3
"""US-LR-004 / US-LR-005: 单文件 + 多份模式冒烟脚本 — 把 raw 直播稿抽成 jsonl。

Single-file mode (US-LR-004):
    python scripts/live-review/extract_one.py \
        --input ~/Desktop/星河审稿/BV12yBoBAEEn_raw.txt \
        --out reports/live-review/BV12yBoBAEEn.jsonl

Multi-file mode (US-LR-005):
    python scripts/live-review/extract_one.py \
        --bvids BV1aaa,BV1bbb \
        --input-dir ~/Desktop/星河审稿 \
        --output-dir reports/live-review \
        --mock-llm-dir tests/live_review/fixtures/mock_extract_5_files

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
        description="Extract one or many Bilibili live-review raw transcripts into jsonl."
    )
    p.add_argument("--bvid", help="单文件模式：BV id；未传时从 --input 文件名自动提取")
    p.add_argument("--input", help="单文件模式：原始 raw.txt 路径")
    p.add_argument("--out", help="单文件模式：输出 jsonl 路径")
    p.add_argument(
        "--bvids",
        help="多份模式：逗号分隔 BV id 列表；与 --input-dir / --output-dir 配合",
    )
    p.add_argument(
        "--input-dir",
        dest="input_dir",
        help="多份模式：raw.txt 所在目录（按 BV<id>_raw.txt 寻找）",
    )
    p.add_argument(
        "--output-dir",
        dest="output_dir",
        help="多份模式：jsonl 输出目录（每 BV 写入 <bvid>.jsonl）",
    )
    p.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="LLM 模型 (默认 claude-sonnet-4-6)",
    )
    p.add_argument(
        "--mock-llm",
        dest="mock_llm",
        help="单文件模式测试用 mock LLM 输出 fixture json 路径",
    )
    p.add_argument(
        "--mock-llm-dir",
        dest="mock_llm_dir",
        help="多份模式测试用 mock 目录，每 BV 取 <bvid>.json",
    )
    return p


def _load_mock(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_to_jsonl(
    raw_text: str,
    *,
    bvid: str,
    source_path: Path,
    out_path: Path,
    model: str,
    mock_response: list[dict] | None,
) -> int:
    """Run extractor and write jsonl. Returns record count."""
    records = extract_from_text(
        raw_text,
        bvid=bvid,
        source_path=str(source_path),
        model=model,
        mock_response=mock_response,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(records)


def _run_single(args: argparse.Namespace) -> int:
    if not args.input:
        print("[extract_one] single-file mode requires --input", file=sys.stderr)
        return 2
    if not args.out:
        print("[extract_one] single-file mode requires --out", file=sys.stderr)
        return 2

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
    mock_response = _load_mock(Path(args.mock_llm)) if args.mock_llm else None

    try:
        n = _extract_to_jsonl(
            raw_text,
            bvid=bvid,
            source_path=input_path,
            out_path=Path(args.out),
            model=args.model,
            mock_response=mock_response,
        )
    except ExtractionError as exc:
        print(f"[extract_one] extraction failed: {exc}", file=sys.stderr)
        return 1

    print(f"[extract_one] {bvid}: {n} novels → {args.out}")
    return 0


def _run_many(args: argparse.Namespace) -> int:
    if not args.input_dir or not args.output_dir:
        print(
            "[extract_one] multi-file mode requires --input-dir and --output-dir",
            file=sys.stderr,
        )
        return 2

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"[extract_one] input dir not found: {input_dir}", file=sys.stderr)
        return 2

    bvids = [b.strip() for b in args.bvids.split(",") if b.strip()]
    if not bvids:
        print("[extract_one] --bvids list is empty", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    mock_dir = Path(args.mock_llm_dir) if args.mock_llm_dir else None

    total = 0
    for bvid in bvids:
        input_path = input_dir / f"{bvid}_raw.txt"
        if not input_path.is_file():
            print(
                f"[extract_one] input not found for {bvid}: {input_path}",
                file=sys.stderr,
            )
            return 2

        mock_response = None
        if mock_dir is not None:
            mock_path = mock_dir / f"{bvid}.json"
            if not mock_path.is_file():
                print(
                    f"[extract_one] mock not found for {bvid}: {mock_path}",
                    file=sys.stderr,
                )
                return 2
            mock_response = _load_mock(mock_path)

        raw_text = input_path.read_text(encoding="utf-8")
        out_path = output_dir / f"{bvid}.jsonl"
        try:
            n = _extract_to_jsonl(
                raw_text,
                bvid=bvid,
                source_path=input_path,
                out_path=out_path,
                model=args.model,
                mock_response=mock_response,
            )
        except ExtractionError as exc:
            print(f"[extract_one] {bvid} extraction failed: {exc}", file=sys.stderr)
            return 1

        total += n
        print(f"[extract_one] {bvid}: {n} novels → {out_path}")

    print(f"[extract_one] done: {len(bvids)} BVs, {total} novels total")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.bvids:
        return _run_many(args)
    return _run_single(args)


if __name__ == "__main__":
    sys.exit(main())
