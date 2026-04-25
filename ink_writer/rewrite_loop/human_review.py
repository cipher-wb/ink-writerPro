"""needs_human_review 兜底 + 4 版保留（M3 P1 / spec §5.5 + Q4）。

US-010 (2026-04-25 起)：

* ``save_rewrite_history``：把 ``run_rewrite_loop`` 返回的 ``history``（含初始 r0 与每轮重写
  产物）写到 ``<base_dir>/data/<book>/chapters/<chapter>.r{i}.txt``，每版独立文件，
  不删稿（人工 review 时可 diff 任意两版）。
* ``write_human_review_record``：把单次 needs_human_review 事件 append 到
  ``<base_dir>/data/<book>/needs_human_review.jsonl``，含 ``marked_at`` UTC ISO。

设计约定：

* ``base_dir`` 默认 ``Path(".")``（项目根），路径前缀 ``data/`` 来自 spec 文本，
  与 evidence_chain (默认 base_dir=Path("data")) 的语义不同——保持 spec 字面对齐。
* 全部 ``open()`` 带 ``encoding="utf-8"``（CLAUDE.md Windows 兼容守则）。
* JSONL 用 append (``"a"``) 模式：连续两次 write 后 jsonl 有 2 行，永不覆盖。
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DEFAULT_BASE_DIR = Path(".")


def _resolve_base(base_dir: Path | str | None) -> Path:
    return Path(base_dir) if base_dir is not None else _DEFAULT_BASE_DIR


def _chapters_dir(base_dir: Path | str | None, book: str) -> Path:
    return _resolve_base(base_dir) / "data" / book / "chapters"


def _human_review_path(base_dir: Path | str | None, book: str) -> Path:
    return _resolve_base(base_dir) / "data" / book / "needs_human_review.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _serialize_case(case: Any) -> Any:
    """把 case 对象/字符串规范成 JSON-friendly 形态。

    - str → 直接当 case_id 返回。
    - 含 ``case_id`` 属性 → 取出 case_id；若同时有 ``severity``（含 ``.value``）也一起带上。
    - dict → 浅拷贝。
    - 其它 → 用 ``repr`` 兜底，避免 json.dump 抛 TypeError。
    """
    if isinstance(case, str):
        return case
    if isinstance(case, dict):
        return dict(case)
    case_id = getattr(case, "case_id", None)
    if case_id is not None:
        payload: dict[str, Any] = {"case_id": case_id}
        severity = getattr(case, "severity", None)
        sev_value = getattr(severity, "value", severity)
        if sev_value is not None:
            payload["severity"] = sev_value
        return payload
    return repr(case)


def _atomic_write_text(path: Path, content: str) -> None:
    """temp file → fsync → os.replace 原子覆盖（review §二 P1#3）。

    避免进程在写入中途崩溃留下半截 .rN.txt 让人工 review 误判 r0..r3 完整。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def save_rewrite_history(
    *,
    book: str,
    chapter: str,
    history: Sequence[str],
    base_dir: Path | str | None = None,
) -> list[Path]:
    """把 history 每版**原子**写到 ``<base_dir>/data/<book>/chapters/<chapter>.r{i}.txt``。

    Args:
        book: 书 slug。
        chapter: 章节标识（不含扩展名）。
        history: 列表，``history[0]`` 是 r0 初稿，``history[i]`` 是第 i 轮重写产物。
        base_dir: 目录前缀，默认 ``Path(".")``（项目根）。

    Returns:
        每版写盘后的绝对/相对路径列表，顺序与 ``history`` 一致。每个文件用
        temp+os.replace 原子写，保证不会出现半截 .rN.txt。
    """
    chapters_dir = _chapters_dir(base_dir, book)
    chapters_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for i, text in enumerate(history):
        out_path = chapters_dir / f"{chapter}.r{i}.txt"
        _atomic_write_text(out_path, text)
        paths.append(out_path)
    return paths


def write_human_review_record(
    *,
    book: str,
    chapter: str,
    blocking_cases: Sequence[Any],
    rewrite_attempts: int,
    rewrite_history_paths: Sequence[Path | str],
    evidence_chain_path: Path | str,
    base_dir: Path | str | None = None,
) -> Path:
    """append 一行 JSON 到 ``<base_dir>/data/<book>/needs_human_review.jsonl``。

    Returns:
        写入的 jsonl 文件路径（多次 write 同一路径会 append，永不覆盖）。
    """
    out_path = _human_review_path(base_dir, book)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "book": book,
        "chapter": chapter,
        "marked_at": _utc_now_iso(),
        "blocking_cases": [_serialize_case(c) for c in blocking_cases],
        "rewrite_attempts": int(rewrite_attempts),
        "rewrite_history_paths": [str(p) for p in rewrite_history_paths],
        "evidence_chain_path": str(evidence_chain_path),
    }

    with open(out_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False))
        fh.write("\n")
    return out_path
