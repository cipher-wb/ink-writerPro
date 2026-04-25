"""evidence_chain.json 写盘 + 强制必带门禁（spec §6.2）。

ink-write 章节交付前必调 ``require_evidence_chain``；缺则
``EvidenceChainMissingError``，让 ink-write 直接退出（消灭 v22 黑盒状态）。
"""

from __future__ import annotations

import json
from pathlib import Path

from ink_writer.evidence_chain.models import EvidenceChain

DEFAULT_BASE_DIR = Path("data")


class EvidenceChainMissingError(RuntimeError):
    """章节缺 evidence_chain.json：ink-write 必须立即终止。"""


def _evidence_path(*, book: str, chapter: str, base_dir: Path | None) -> Path:
    base = Path(base_dir) if base_dir is not None else DEFAULT_BASE_DIR
    return base / book / "chapters" / f"{chapter}.evidence.json"


def write_evidence_chain(
    *,
    book: str,
    chapter: str,
    evidence: EvidenceChain,
    base_dir: Path | str | None = None,
) -> Path:
    """把 evidence dataclass 写到 ``<base_dir>/<book>/chapters/<chapter>.evidence.json``。"""
    out_path = _evidence_path(book=book, chapter=chapter, base_dir=Path(base_dir) if base_dir else None)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(evidence.to_dict(), fh, ensure_ascii=False, indent=2)
    return out_path


def require_evidence_chain(
    *,
    book: str,
    chapter: str,
    base_dir: Path | str | None = None,
) -> Path:
    """门禁：章节交付前调；缺则 raise EvidenceChainMissingError。"""
    out_path = _evidence_path(book=book, chapter=chapter, base_dir=Path(base_dir) if base_dir else None)
    if not out_path.exists():
        raise EvidenceChainMissingError(
            f"evidence_chain.json missing for {book}/{chapter}: {out_path}"
        )
    return out_path
