"""``ink meta-rule {list, approve, reject}`` — Layer 5 approval gate (US-004).

CLI surface
-----------
* ``meta-rule list [--status pending|approved|rejected]`` — print one line per
  proposal: ``MR-NNNN status=X sim=0.XX cases=N :: <merged_rule>``.
* ``meta-rule approve <proposal_id>`` — stamp ``meta_rule_id`` onto every
  ``covered_cases`` entry, flip the proposal yaml to ``status=approved`` +
  add ``approved_at`` (UTC date).
* ``meta-rule reject <proposal_id>`` — flip the proposal yaml to
  ``status=rejected`` + add ``rejected_at``.

Approve / reject only act on ``status=pending`` proposals. Re-approving an
already-approved proposal returns rc=1 (idempotent guard for batch workflows).
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import yaml

from ink_writer.case_library.errors import CaseNotFoundError
from ink_writer.case_library.store import CaseStore

DEFAULT_LIBRARY_ROOT = Path("data/case_library")
_STATUS_CHOICES = ("pending", "approved", "rejected")


def _meta_rules_dir(library_root: Path) -> Path:
    return Path(library_root) / "meta_rules"


def _load_proposal(library_root: Path, proposal_id: str) -> tuple[Path, dict]:
    path = _meta_rules_dir(library_root) / f"{proposal_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"meta-rule proposal not found: {proposal_id}")
    with open(path, encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    return path, data


def _save_proposal(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fp:
        yaml.safe_dump(
            data,
            fp,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _iter_proposals(library_root: Path) -> list[dict]:
    base = _meta_rules_dir(library_root)
    if not base.exists():
        return []
    out: list[dict] = []
    for path in sorted(base.glob("MR-*.yaml")):
        with open(path, encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
        out.append(data)
    return out


def cmd_list(*, library_root: Path, status: str | None = None) -> int:
    """Print one line per proposal; optionally filtered by status."""
    for data in _iter_proposals(library_root):
        if status is not None and data.get("status") != status:
            continue
        proposal_id = data.get("proposal_id", "MR-????")
        cur_status = data.get("status", "?")
        try:
            sim = float(data.get("similarity", 0.0))
        except (TypeError, ValueError):
            sim = 0.0
        covered = data.get("covered_cases") or []
        merged_rule = str(data.get("merged_rule") or "").strip()
        print(
            f"{proposal_id} status={cur_status} sim={sim:.2f} "
            f"cases={len(covered)} :: {merged_rule}"
        )
    return 0


def cmd_approve(*, library_root: Path, proposal_id: str) -> int:
    """Stamp meta_rule_id on covered cases + flip proposal to approved.

    幂等语义（review §二 P1#7 修复）：
      * status=pending → 正常 approve，rc=0。
      * status=approved → 真幂等返回 rc=0（不重写 yaml、不再调 store.save），
        批量脚本网络重试时不会刷日志噪声。
      * status=rejected → rc=1（拒绝跨状态 approve）。
    """
    try:
        path, data = _load_proposal(library_root, proposal_id)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    current_status = data.get("status")
    if current_status == "approved":
        # 真幂等：已 approved 直接返回成功，不重新写盘
        print(
            f"proposal {proposal_id} already approved; no-op (idempotent)",
        )
        return 0
    if current_status != "pending":
        print(
            f"proposal {proposal_id} is not pending (status="
            f"{current_status}); refusing to approve",
            file=sys.stderr,
        )
        return 1

    store = CaseStore(library_root)
    covered = data.get("covered_cases") or []
    failed: list[tuple[str, str]] = []
    updated = 0
    for case_id in covered:
        try:
            case = store.load(case_id)
        except CaseNotFoundError as exc:
            failed.append((case_id, str(exc)))
            continue
        if case.meta_rule_id == proposal_id:
            continue
        case.meta_rule_id = proposal_id
        store.save(case)
        updated += 1

    data["status"] = "approved"
    data["approved_at"] = _today()
    _save_proposal(path, data)

    print(
        f"approved {proposal_id}: stamped meta_rule_id on "
        f"{updated}/{len(covered)} covered cases"
    )
    if failed:
        print("first failures (up to 10):", file=sys.stderr)
        for case_id, err in failed[:10]:
            print(f"  {case_id}: {err}", file=sys.stderr)
        return 1
    return 0


def cmd_reject(*, library_root: Path, proposal_id: str) -> int:
    """Flip proposal to rejected + add rejected_at."""
    try:
        path, data = _load_proposal(library_root, proposal_id)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if data.get("status") != "pending":
        print(
            f"proposal {proposal_id} is not pending (status="
            f"{data.get('status')}); refusing to reject",
            file=sys.stderr,
        )
        return 1

    data["status"] = "rejected"
    data["rejected_at"] = _today()
    _save_proposal(path, data)
    print(f"rejected {proposal_id}")
    return 0


def register_subparsers(subparsers: argparse._SubParsersAction) -> None:
    """Wire ``meta-rule {list,approve,reject}`` into a parent ``ink case`` CLI."""
    meta = subparsers.add_parser(
        "meta-rule",
        help="Layer 5 meta-rule proposals: list / approve / reject",
    )
    meta_sub = meta.add_subparsers(dest="meta_rule_action", required=True)

    list_p = meta_sub.add_parser("list", help="List meta-rule proposals")
    list_p.add_argument(
        "--status",
        choices=list(_STATUS_CHOICES),
        default=None,
        help="Filter by proposal status (default: all).",
    )

    approve_p = meta_sub.add_parser(
        "approve",
        help="Approve a pending proposal (writes meta_rule_id to covered cases)",
    )
    approve_p.add_argument("proposal_id")

    reject_p = meta_sub.add_parser("reject", help="Reject a pending proposal")
    reject_p.add_argument("proposal_id")


def dispatch(args: argparse.Namespace) -> int:
    """Route a parsed ``meta-rule`` namespace to the matching cmd_*."""
    library_root = getattr(args, "library_root", DEFAULT_LIBRARY_ROOT)
    action = getattr(args, "meta_rule_action", None)
    if action == "list":
        return cmd_list(library_root=library_root, status=args.status)
    if action == "approve":
        return cmd_approve(library_root=library_root, proposal_id=args.proposal_id)
    if action == "reject":
        return cmd_reject(library_root=library_root, proposal_id=args.proposal_id)
    print(f"unknown meta-rule action: {action}", file=sys.stderr)
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ink-meta-rule",
        description="Approve/reject Layer 5 meta-rule proposals.",
    )
    parser.add_argument(
        "--library-root",
        type=Path,
        default=DEFAULT_LIBRARY_ROOT,
        help="Case library root (default: data/case_library)",
    )
    sub = parser.add_subparsers(dest="meta_rule_action", required=True)

    list_p = sub.add_parser("list", help="List meta-rule proposals")
    list_p.add_argument(
        "--status",
        choices=list(_STATUS_CHOICES),
        default=None,
    )

    approve_p = sub.add_parser("approve")
    approve_p.add_argument("proposal_id")

    reject_p = sub.add_parser("reject")
    reject_p.add_argument("proposal_id")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Standalone entry point — never raises; returns non-zero on failure."""
    try:
        from runtime_compat import enable_windows_utf8_stdio

        enable_windows_utf8_stdio()
    except Exception:  # pragma: no cover — Mac/Linux no-op
        pass

    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        return code

    try:
        return dispatch(args)
    except Exception as exc:  # noqa: BLE001 — CLI top-level guard
        print(f"unexpected error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
