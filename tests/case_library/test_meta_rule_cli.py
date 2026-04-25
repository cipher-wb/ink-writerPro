"""US-004 — ``ink meta-rule {list, approve, reject}`` CLI tests."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ink_writer.case_library.cli import main as case_main
from ink_writer.case_library.meta_rule_cli import (
    cmd_approve,
    cmd_list,
    cmd_reject,
)
from ink_writer.case_library.models import (
    Case,
    CaseDomain,
    CaseLayer,
    CaseSeverity,
    CaseStatus,
    FailurePattern,
    Scope,
    Source,
    SourceType,
)
from ink_writer.case_library.store import CaseStore


def _make_case(case_id: str, *, meta_rule_id: str | None = None) -> Case:
    return Case(
        case_id=case_id,
        title=f"Test {case_id}",
        status=CaseStatus.ACTIVE,
        severity=CaseSeverity.P2,
        domain=CaseDomain.WRITING_QUALITY,
        layer=[CaseLayer.DOWNSTREAM],
        tags=["dialogue-flat"],
        scope=Scope(genre=["all"], chapter=["all"]),
        source=Source(
            type=SourceType.SELF_AUDIT,
            raw_text="seed",
            ingested_at="2026-04-25",
        ),
        failure_pattern=FailurePattern(
            description="对话过于平面",
            observable=["缺乏潜台词"],
        ),
        meta_rule_id=meta_rule_id,
    )


def _write_proposal(
    library_root: Path,
    *,
    proposal_id: str,
    status: str = "pending",
    similarity: float = 0.88,
    merged_rule: str = "对话过于平面",
    covered_cases: list[str] | None = None,
    reason: str = "都缺少潜台词",
) -> Path:
    base = library_root / "meta_rules"
    base.mkdir(parents=True, exist_ok=True)
    payload = {
        "proposal_id": proposal_id,
        "status": status,
        "similarity": similarity,
        "merged_rule": merged_rule,
        "covered_cases": list(covered_cases or []),
        "reason": reason,
    }
    path = base / f"{proposal_id}.yaml"
    with open(path, "w", encoding="utf-8") as fp:
        yaml.safe_dump(payload, fp, allow_unicode=True, sort_keys=False)
    return path


def test_list_pending(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library_root = tmp_path / "lib"
    library_root.mkdir()
    _write_proposal(
        library_root,
        proposal_id="MR-0001",
        status="pending",
        similarity=0.91,
        merged_rule="对话过于平面",
        covered_cases=["CASE-A", "CASE-B", "CASE-C", "CASE-D", "CASE-E"],
    )
    _write_proposal(
        library_root,
        proposal_id="MR-0002",
        status="approved",
        similarity=0.82,
        merged_rule="节奏失衡",
        covered_cases=["CASE-X", "CASE-Y", "CASE-Z"],
    )

    rc = cmd_list(library_root=library_root, status="pending")
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 1
    assert "MR-0001" in out[0]
    assert "status=pending" in out[0]
    assert "sim=0.91" in out[0]
    assert "cases=5" in out[0]
    assert "对话过于平面" in out[0]


def test_approve_writes_meta_rule_id_to_cases(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library_root = tmp_path / "lib"
    store = CaseStore(library_root)
    case_ids = [f"CASE-2026-100{i}" for i in range(5)]
    for cid in case_ids:
        store.save(_make_case(cid))

    _write_proposal(
        library_root,
        proposal_id="MR-0001",
        covered_cases=case_ids,
    )

    rc = cmd_approve(library_root=library_root, proposal_id="MR-0001")
    assert rc == 0
    capsys.readouterr()  # drain stdout

    # Each covered case now has meta_rule_id stamped.
    for cid in case_ids:
        case = store.load(cid)
        assert case.meta_rule_id == "MR-0001"

    # Proposal flipped to approved + carries approved_at.
    proposal_path = library_root / "meta_rules" / "MR-0001.yaml"
    with open(proposal_path, encoding="utf-8") as fp:
        data = yaml.safe_load(fp)
    assert data["status"] == "approved"
    assert "approved_at" in data
    assert data["approved_at"]  # non-empty


def test_approve_idempotent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library_root = tmp_path / "lib"
    store = CaseStore(library_root)
    case_ids = [f"CASE-2026-200{i}" for i in range(3)]
    for cid in case_ids:
        store.save(_make_case(cid))

    _write_proposal(
        library_root,
        proposal_id="MR-0007",
        covered_cases=case_ids,
    )

    rc1 = cmd_approve(library_root=library_root, proposal_id="MR-0007")
    assert rc1 == 0
    capsys.readouterr()

    # Second approve must NOT re-approve — proposal is no longer pending.
    rc2 = cmd_approve(library_root=library_root, proposal_id="MR-0007")
    assert rc2 == 1
    err = capsys.readouterr().err
    assert "not pending" in err

    # Cases still carry the meta_rule_id from the first approve.
    for cid in case_ids:
        case = store.load(cid)
        assert case.meta_rule_id == "MR-0007"


def test_reject(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library_root = tmp_path / "lib"
    library_root.mkdir()
    _write_proposal(
        library_root,
        proposal_id="MR-0042",
        covered_cases=["CASE-A", "CASE-B"],
    )

    rc = cmd_reject(library_root=library_root, proposal_id="MR-0042")
    assert rc == 0
    capsys.readouterr()

    proposal_path = library_root / "meta_rules" / "MR-0042.yaml"
    with open(proposal_path, encoding="utf-8") as fp:
        data = yaml.safe_load(fp)
    assert data["status"] == "rejected"
    assert "rejected_at" in data
    assert data["rejected_at"]


def test_parent_cli_dispatches_meta_rule_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The ``ink case meta-rule list`` route is wired through the parent CLI."""
    library_root = tmp_path / "lib"
    library_root.mkdir()
    _write_proposal(
        library_root,
        proposal_id="MR-0001",
        status="pending",
        merged_rule="风格漂移",
        covered_cases=["CASE-A"] * 5,
    )

    rc = case_main([
        "--library-root",
        str(library_root),
        "meta-rule",
        "list",
        "--status",
        "pending",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "MR-0001" in out
    assert "风格漂移" in out
