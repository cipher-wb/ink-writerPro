"""evidence_chain.json 写盘 + 强制必带门禁（spec §6.2）。

ink-write 章节交付前必调 ``require_evidence_chain``；缺则
``EvidenceChainMissingError``，让 ink-write 直接退出（消灭 v22 黑盒状态）。

写盘走"临时文件 + os.replace"原子模式（review §二 P1#3）：进程在写一半时崩溃
也不会留下半截 JSON 让下游 require_evidence_chain 取到坏数据。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ink_writer.evidence_chain.models import EvidenceChain

DEFAULT_BASE_DIR = Path("data")


class EvidenceChainMissingError(RuntimeError):
    """章节缺 evidence_chain.json：ink-write 必须立即终止。"""


def _evidence_path(*, book: str, chapter: str, base_dir: Path | None) -> Path:
    base = Path(base_dir) if base_dir is not None else DEFAULT_BASE_DIR
    return base / book / "chapters" / f"{chapter}.evidence.json"


def _atomic_write_text(path: Path, content: str) -> None:
    """temp file → fsync → os.replace 原子覆盖（POSIX 与 Windows 都原子）。"""
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


def write_evidence_chain(
    *,
    book: str,
    chapter: str,
    evidence: EvidenceChain,
    base_dir: Path | str | None = None,
) -> Path:
    """把 evidence dataclass 原子写到 ``<base_dir>/<book>/chapters/<chapter>.evidence.json``。"""
    out_path = _evidence_path(
        book=book, chapter=chapter, base_dir=Path(base_dir) if base_dir else None
    )
    payload = json.dumps(evidence.to_dict(), ensure_ascii=False, indent=2)
    _atomic_write_text(out_path, payload)
    return out_path


def require_evidence_chain(
    *,
    book: str,
    chapter: str,
    base_dir: Path | str | None = None,
) -> Path:
    """门禁：章节交付前调；缺则 raise EvidenceChainMissingError。"""
    out_path = _evidence_path(
        book=book, chapter=chapter, base_dir=Path(base_dir) if base_dir else None
    )
    if not out_path.exists():
        raise EvidenceChainMissingError(
            f"evidence_chain.json missing for {book}/{chapter}: {out_path}"
        )
    return out_path
