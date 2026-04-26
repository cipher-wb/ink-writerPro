#!/usr/bin/env python3
"""US-LR-006: 全量批跑脚本 — 把 BV*_raw.txt 目录抽成 jsonl。

支持:
- ``--limit N``      仅处理排序后前 N 份
- ``--resume``       跳过 output_dir 已存在的 ``<bvid>.jsonl``
- ``--skip-failed``  失败时不退出，写 ``_failed.jsonl`` 后继续
- ``--workers N``    并发 worker 数（默认 1 = 单进程串行；> 1 用 multiprocessing.Pool）
- ``--mock-llm-dir`` 测试用，每 BV 取 ``<dir>/<bvid>.json``；缺 mock 视为该 BV 失败

退出码:
    0  全部成功；或有失败但传了 ``--skip-failed``
    1  有失败且未传 ``--skip-failed``
    2  参数错误 / ``--input-dir`` 不存在

实跑 174 份由用户按 spec §M-3 手动触发；本脚本由 ralph 用 4 mock 场景验证。
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
import time  # noqa: E402
import traceback  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ink_writer.live_review.extractor import (  # noqa: E402
    ExtractionError,
    extract_from_text,
)

_BVID_FILENAME_RE = re.compile(r"^(BV[\w]+)_raw\.txt$")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Batch-extract Bilibili live-review raw transcripts into jsonl."
    )
    p.add_argument("--input-dir", dest="input_dir", required=True,
                   help="raw.txt 所在目录 (扫 BV*_raw.txt)")
    p.add_argument("--output-dir", dest="output_dir", required=True,
                   help="jsonl 输出目录 (每 BV 写 <bvid>.jsonl)")
    p.add_argument("--limit", type=int, default=None,
                   help="仅处理排序后前 N 份")
    p.add_argument("--resume", action="store_true",
                   help="跳过 output_dir 已存在的 <bvid>.jsonl")
    p.add_argument("--skip-failed", dest="skip_failed", action="store_true",
                   help="失败时不退出，写 _failed.jsonl 后继续")
    p.add_argument("--workers", type=int, default=1,
                   help="并发 worker 数（默认 1 = 串行；> 1 用 multiprocessing.Pool）")
    p.add_argument("--model", default="claude-sonnet-4-6",
                   help="LLM 模型 (默认 claude-sonnet-4-6)")
    p.add_argument("--mock-llm-dir", dest="mock_llm_dir", default=None,
                   help="测试用 mock 目录，每 BV 取 <dir>/<bvid>.json")
    return p


def _list_inputs(input_dir: Path, limit: int | None) -> list[Path]:
    files = sorted(input_dir.glob("BV*_raw.txt"))
    if limit is not None and limit >= 0:
        files = files[:limit]
    return files


def _infer_bvid(raw_path: Path) -> str | None:
    m = _BVID_FILENAME_RE.match(raw_path.name)
    return m.group(1) if m else None


def _load_mock(mock_dir: Path | None, bvid: str) -> list[dict]:
    """返回 mock_response；mock_dir 为 None 时返回 None；缺文件抛 ExtractionError。"""
    if mock_dir is None:
        return None
    mock_path = mock_dir / f"{bvid}.json"
    if not mock_path.is_file():
        raise ExtractionError(f"mock not found for {bvid}: {mock_path}")
    return json.loads(mock_path.read_text(encoding="utf-8"))


def _write_jsonl(out_path: Path, records: list[dict]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _append_failed(failed_path: Path, failures: list[dict]) -> None:
    failed_path.parent.mkdir(parents=True, exist_ok=True)
    with open(failed_path, "a", encoding="utf-8") as f:
        for failure in failures:
            f.write(json.dumps(failure, ensure_ascii=False) + "\n")


@dataclass
class _BvJobResult:
    """单 BV 处理结果，可 pickle 跨进程传递。"""
    bvid: str
    success: bool
    elapsed_seconds: float
    error: str = ""
    traceback_str: str = ""


def _process_one_bv(job: tuple) -> _BvJobResult:
    """Module-level worker function for multiprocessing.Pool (must be picklable).

    Args:
        job: (raw_path_str, output_dir_str, model, mock_dir_str_or_none)
    """
    raw_path_str, output_dir_str, model, mock_dir_str = job
    raw_path = Path(raw_path_str)
    output_dir = Path(output_dir_str)
    mock_dir = Path(mock_dir_str) if mock_dir_str else None

    bvid = _infer_bvid(raw_path)
    if not bvid:
        return _BvJobResult(
            bvid=raw_path.stem,
            success=False,
            elapsed_seconds=0.0,
            error=f"cannot infer bvid from {raw_path.name!r}",
        )

    t0 = time.time()
    try:
        mock_response = _load_mock(mock_dir, bvid)
        raw_text = raw_path.read_text(encoding="utf-8")
        records = extract_from_text(
            raw_text,
            bvid=bvid,
            source_path=str(raw_path),
            model=model,
            mock_response=mock_response,
        )
        _write_jsonl(output_dir / f"{bvid}.jsonl", records)
        return _BvJobResult(
            bvid=bvid, success=True, elapsed_seconds=time.time() - t0
        )
    except Exception as exc:  # noqa: BLE001
        return _BvJobResult(
            bvid=bvid,
            success=False,
            elapsed_seconds=time.time() - t0,
            error=str(exc),
            traceback_str=traceback.format_exc(),
        )


def _run(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"[run_batch] input dir not found: {input_dir}", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = _list_inputs(input_dir, args.limit)
    if not files:
        print("[run_batch] no BV*_raw.txt found; nothing to do")
        return 0

    done_bvids: set[str] = set()
    if args.resume:
        done_bvids = {p.stem for p in output_dir.glob("BV*.jsonl")}

    files_to_process = []
    for raw_path in files:
        bvid = _infer_bvid(raw_path)
        if bvid and bvid in done_bvids:
            print(f"[skip] {bvid} skipped (resume)")
            continue
        files_to_process.append(raw_path)

    if not files_to_process:
        print("[run_batch] all done (resume); nothing to process")
        return 0

    mock_dir_str = str(args.mock_llm_dir) if args.mock_llm_dir else None
    jobs = [
        (str(raw_path), str(output_dir), args.model, mock_dir_str)
        for raw_path in files_to_process
    ]
    total = len(jobs)
    failures: list[dict] = []

    workers = max(1, int(args.workers))
    if workers == 1:
        # 串行路径（向后兼容；调试友好）
        for i, job in enumerate(jobs, 1):
            result = _process_one_bv(job)
            if result.success:
                print(f"[{i}/{total}] {result.bvid} done in {result.elapsed_seconds:.1f}s")
            else:
                failures.append({
                    "bvid": result.bvid,
                    "error": result.error,
                    "traceback": result.traceback_str,
                })
                print(
                    f"[{i}/{total}] {result.bvid} FAILED: {result.error}",
                    file=sys.stderr,
                )
                if not args.skip_failed:
                    break
    else:
        # 并发路径（multiprocessing.Pool + imap_unordered）
        from multiprocessing import get_context

        print(f"[run_batch] starting {workers} workers for {total} jobs")
        ctx = get_context("spawn")  # 跨平台一致；避免 fork copy 不稳定问题
        with ctx.Pool(processes=workers) as pool:
            done = 0
            try:
                for result in pool.imap_unordered(_process_one_bv, jobs):
                    done += 1
                    if result.success:
                        print(
                            f"[{done}/{total}] {result.bvid} done in "
                            f"{result.elapsed_seconds:.1f}s"
                        )
                    else:
                        failures.append({
                            "bvid": result.bvid,
                            "error": result.error,
                            "traceback": result.traceback_str,
                        })
                        print(
                            f"[{done}/{total}] {result.bvid} FAILED: {result.error}",
                            file=sys.stderr,
                        )
                        if not args.skip_failed:
                            pool.terminate()
                            break
            finally:
                pool.close()
                pool.join()

    if failures:
        _append_failed(output_dir / "_failed.jsonl", failures)
        print(
            f"[run_batch] {len(failures)} failure(s) written to "
            f"{output_dir / '_failed.jsonl'}",
            file=sys.stderr,
        )

    if failures and not args.skip_failed:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
