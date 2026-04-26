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

    # Snapshot proposal yaml mtime + bytes (review §二 P1#7：真幂等不应重写盘)
    proposal_path = library_root / "meta_rules" / "MR-0007.yaml"
    mtime_before = proposal_path.stat().st_mtime
    bytes_before = proposal_path.read_bytes()

    # Second approve on already-approved must be true idempotent: rc=0, no yaml mutation.
    rc2 = cmd_approve(library_root=library_root, proposal_id="MR-0007")
    assert rc2 == 0
    captured = capsys.readouterr()
    assert "already approved" in captured.out
    assert captured.err == ""

    # yaml file 未被改写
    assert proposal_path.stat().st_mtime == mtime_before
    assert proposal_path.read_bytes() == bytes_before

    # Cases still carry the meta_rule_id from the first approve.
    for cid in case_ids:
        case = store.load(cid)
        assert case.meta_rule_id == "MR-0007"


def test_approve_backfills_unstamped_cases_on_retry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """review §三 #1 修复：首次 partial fail 后 retry，幂等分支补刀未 stamp 的 case。

    场景：covered=[A,B,C]；首次 approve 时 C 缺失 → A/B 已 stamp + status=approved
    + rc=1。运维补好 C 的 yaml 后再次 approve（retry）：旧实现走"真幂等 rc=0"，
    C 永远不会被 stamp；新实现进入幂等分支后扫一遍 covered，发现 C 未 stamp →
    补刀写盘 + rc=0；同时 yaml 不被重写（status/approved_at 不动）。
    """
    library_root = tmp_path / "lib"
    store = CaseStore(library_root)
    # 首次只 save A、B；C 缺失模拟 schema 损坏 / 文件未到位
    case_ids = ["CASE-2026-3001", "CASE-2026-3002", "CASE-2026-3003"]
    for cid in case_ids[:2]:
        store.save(_make_case(cid))

    _write_proposal(
        library_root,
        proposal_id="MR-0010",
        covered_cases=case_ids,
    )

    rc1 = cmd_approve(library_root=library_root, proposal_id="MR-0010")
    assert rc1 == 1  # C 缺失 → partial fail
    capsys.readouterr()

    # A/B 已 stamp，C 仍未 save 进 store
    assert store.load("CASE-2026-3001").meta_rule_id == "MR-0010"
    assert store.load("CASE-2026-3002").meta_rule_id == "MR-0010"

    # proposal 已被翻成 approved
    proposal_path = library_root / "meta_rules" / "MR-0010.yaml"
    with open(proposal_path, encoding="utf-8") as fp:
        first_data = yaml.safe_load(fp)
    assert first_data["status"] == "approved"
    mtime_before = proposal_path.stat().st_mtime
    bytes_before = proposal_path.read_bytes()

    # 运维补好 C
    store.save(_make_case("CASE-2026-3003"))

    # retry：新实现应补刀 C 的 stamp，且 yaml 不动
    rc2 = cmd_approve(library_root=library_root, proposal_id="MR-0010")
    assert rc2 == 0
    out = capsys.readouterr().out
    assert "backfilled" in out
    assert "1/3" in out  # 只补 1 个（C）

    # C 现在被 stamp
    assert store.load("CASE-2026-3003").meta_rule_id == "MR-0010"
    # yaml 文件未被重写（真幂等承诺：status/approved_at 已正确就别动）
    assert proposal_path.stat().st_mtime == mtime_before
    assert proposal_path.read_bytes() == bytes_before


def test_approve_idempotent_when_all_stamped_after_retry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """补完后第三次 approve：所有 case 全 stamp、无 failed → 真幂等 rc=0 不写盘。"""
    library_root = tmp_path / "lib"
    store = CaseStore(library_root)
    case_ids = ["CASE-2026-3101", "CASE-2026-3102"]
    for cid in case_ids:
        store.save(_make_case(cid))
    _write_proposal(library_root, proposal_id="MR-0011", covered_cases=case_ids)

    cmd_approve(library_root=library_root, proposal_id="MR-0011")
    capsys.readouterr()

    # 二次：进入幂等分支，无补刀对象 → 真幂等
    rc = cmd_approve(library_root=library_root, proposal_id="MR-0011")
    assert rc == 0
    out = capsys.readouterr().out
    assert "no-op (idempotent)" in out
    assert "backfilled" not in out


def test_approve_rejected_proposal_returns_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """approve 一个 rejected proposal 应当 rc=1（review §二 P1#7：跨状态拒绝）。"""
    library_root = tmp_path / "lib"
    library_root.mkdir()
    _write_proposal(
        library_root,
        proposal_id="MR-0099",
        status="rejected",
        covered_cases=["CASE-Z"],
    )

    rc = cmd_approve(library_root=library_root, proposal_id="MR-0099")
    assert rc == 1
    err = capsys.readouterr().err
    assert "not pending" in err
    assert "rejected" in err


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
