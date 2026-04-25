"""planning_evidence_chain.json 写盘 + 强制必带门禁（M4 P0 spec §6.2 扩展）。

ink-init 与 ink-plan Step 99 各自跑完后调 ``write_planning_evidence_chain``
把当次评审结果作为一个 stage 合并到 ``<base_dir>/<book>/planning_evidence_chain.json``；
同书 ink-init 与 ink-plan 写出的两次会聚合成 stages 列表 + overall_passed。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ink_writer.evidence_chain.models import EvidenceChain
from ink_writer.evidence_chain.writer import DEFAULT_BASE_DIR

PLANNING_SCHEMA_VERSION = "1.0"


class PlanningEvidenceChainMissingError(RuntimeError):
    """书 planning_evidence_chain.json 缺失：策划期审查必须立即终止。"""


def _planning_path(*, book: str, base_dir: Path | None) -> Path:
    base = Path(base_dir) if base_dir is not None else DEFAULT_BASE_DIR
    return base / book / "planning_evidence_chain.json"


def _stage_passed(stage: dict[str, Any]) -> bool:
    """单个 stage 是否通过：outcome != 'blocked' 即视作通过。"""
    return stage.get("outcome") != "blocked"


def write_planning_evidence_chain(
    *,
    book: str,
    evidence: EvidenceChain,
    base_dir: Path | str | None = None,
) -> Path:
    """把 planning evidence dataclass 合并到 ``<base_dir>/<book>/planning_evidence_chain.json``。

    - 文件不存在：新建 ``{schema_version, phase, book, stages: [stage], overall_passed}``。
    - 文件已存在：剔除同 ``stage`` 名的旧条目（重跑覆盖），追加新 stage。
    - ``overall_passed = all(stage 未 blocked)``。

    若 ``evidence.phase != 'planning'`` 直接 raise ``ValueError``，避免误把章节级
    evidence 写到策划期文件。
    """
    if evidence.phase != "planning":
        raise ValueError(
            "write_planning_evidence_chain requires phase='planning', "
            f"got phase={evidence.phase!r}"
        )

    out_path = _planning_path(
        book=book,
        base_dir=Path(base_dir) if base_dir is not None else None,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        with open(out_path, encoding="utf-8") as fh:
            doc = json.load(fh)
    else:
        doc = {
            "schema_version": PLANNING_SCHEMA_VERSION,
            "phase": "planning",
            "book": book,
            "stages": [],
            "overall_passed": True,
        }

    new_stage = evidence.to_dict()
    existing_stages = [
        s for s in doc.get("stages", []) if s.get("stage") != evidence.stage
    ]
    existing_stages.append(new_stage)
    doc["stages"] = existing_stages
    doc["overall_passed"] = all(_stage_passed(s) for s in existing_stages)

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    return out_path


def require_planning_evidence_chain(
    *,
    book: str,
    base_dir: Path | str | None = None,
) -> dict[str, Any]:
    """门禁：策划期评审完成前调；缺则 raise PlanningEvidenceChainMissingError。"""
    out_path = _planning_path(
        book=book,
        base_dir=Path(base_dir) if base_dir is not None else None,
    )
    if not out_path.exists():
        raise PlanningEvidenceChainMissingError(
            f"planning_evidence_chain.json missing for {book}: {out_path}"
        )
    with open(out_path, encoding="utf-8") as fh:
        return json.load(fh)
