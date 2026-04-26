#!/usr/bin/env python3
"""US-LR-010: promote 工具 — 把 approved=true 的候选写入 editor-wisdom rules.json。

剥除候选阶段的扩展字段 (id=RC- / dup_with / approved / source_bvids)，
分配下一个 EW-NNNN，新加 source='live_review' 标记来源；现有规则字节级保持不变。
写盘前用 schemas/editor-rules.schema.json 严格校验，失败则 raise 不动文件。

CLI:
    python3 scripts/live-review/promote_approved_rules.py \\
        --candidates data/live-review/rule_candidates.json \\
        --rules data/editor-wisdom/rules.json

退出码:
    0  成功 (含 0 条 approved 的 no-op 路径)
    1  schema 校验失败 / 文件解析失败
    2  candidates / rules 文件不存在
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

from jsonschema import Draft202012Validator  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_CANDIDATES = _REPO_ROOT / "data" / "live-review" / "rule_candidates.json"
_DEFAULT_RULES = _REPO_ROOT / "data" / "editor-wisdom" / "rules.json"
_SCHEMA_PATH = _REPO_ROOT / "schemas" / "editor-rules.schema.json"

_EW_ID_RE = re.compile(r"^EW-(\d{4})$")

# 候选阶段写入但 promote 时必须剥除的字段。
_CANDIDATE_ONLY_FIELDS = {"dup_with", "approved", "source_bvids"}

# 标准 EW 规则字段顺序（与 data/editor-wisdom/rules.json 对齐）。
_RULE_FIELD_ORDER = (
    "id",
    "category",
    "rule",
    "why",
    "severity",
    "applies_to",
    "source_files",
    "source",
)


class PromoteError(RuntimeError):
    """fail-loud：解析失败 / schema 违反 / IO 失败。"""


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Promote approved live-review candidates into editor-wisdom rules.json.",
    )
    p.add_argument(
        "--candidates",
        default=str(_DEFAULT_CANDIDATES),
        help="rule_candidates.json (US-LR-009 产物，含 approved 字段)",
    )
    p.add_argument(
        "--rules",
        default=str(_DEFAULT_RULES),
        help="editor-wisdom rules.json 目标文件 (in-place 追加)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印变更预览，不写盘",
    )
    return p


def _load_json(path: Path, *, label: str) -> object:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PromoteError(f"{label} parse failed: {exc}") from exc


def _next_ew_id(existing_rules: list[dict]) -> int:
    """从现有规则中取最大 EW 编号 +1；空列表返 1。"""
    max_n = 0
    for r in existing_rules:
        m = _EW_ID_RE.match(str(r.get("id", "")))
        if m:
            n = int(m.group(1))
            if n > max_n:
                max_n = n
    return max_n + 1


def _build_promoted_rule(cand: dict, ew_id: str) -> dict:
    """把候选转成严格 schema 兼容的 EW-NNNN 规则；剥除候选扩展字段。"""
    return {
        "id": ew_id,
        "category": cand["category"],
        "rule": cand["rule"],
        "why": cand["why"],
        "severity": cand["severity"],
        "applies_to": list(cand["applies_to"]),
        "source_files": list(cand.get("source_files") or []),
        "source": "live_review",
    }


def _ordered_rule(rule: dict) -> dict:
    """按 _RULE_FIELD_ORDER 重排字段（仅对新加规则；现有规则不动）。"""
    out: dict = {}
    for k in _RULE_FIELD_ORDER:
        if k in rule:
            out[k] = rule[k]
    for k, v in rule.items():
        if k not in out:
            out[k] = v
    return out


def _validate_strict(merged: list[dict], schema: dict) -> None:
    errs = list(Draft202012Validator(schema).iter_errors(merged))
    if errs:
        msgs = [
            f"  - [{list(e.absolute_path)[:3]}] {e.message[:120]}"
            for e in errs[:5]
        ]
        raise PromoteError(
            "promoted rules.json fails strict schema validation:\n" + "\n".join(msgs)
        )


def promote(
    *,
    candidates_path: Path,
    rules_path: Path,
    dry_run: bool = False,
) -> tuple[int, list[str]]:
    """主流程：返回 (新增条数, 新 EW-id 列表)。"""
    candidates = _load_json(candidates_path, label="candidates")
    if not isinstance(candidates, list):
        raise PromoteError("candidates root must be JSON array")
    existing = _load_json(rules_path, label="rules")
    if not isinstance(existing, list):
        raise PromoteError("rules.json root must be JSON array")
    schema = _load_json(_SCHEMA_PATH, label="schema")
    if not isinstance(schema, dict):
        raise PromoteError("editor-rules schema must be JSON object")
    Draft202012Validator.check_schema(schema)

    approved = [c for c in candidates if c.get("approved") is True]
    if not approved:
        return 0, []

    next_n = _next_ew_id(existing)
    new_ids: list[str] = []
    new_rules: list[dict] = []
    for cand in approved:
        ew_id = f"EW-{next_n:04d}"
        new_rule = _build_promoted_rule(cand, ew_id)
        leftover = _CANDIDATE_ONLY_FIELDS & set(new_rule.keys())
        if leftover:  # paranoia: _build_promoted_rule must drop these.
            raise PromoteError(
                f"internal: candidate-only fields leaked into promoted rule: {leftover}"
            )
        new_rules.append(_ordered_rule(new_rule))
        new_ids.append(ew_id)
        next_n += 1

    merged = existing + new_rules
    _validate_strict(merged, schema)

    if not dry_run:
        rules_path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return len(new_rules), new_ids


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        added, new_ids = promote(
            candidates_path=Path(args.candidates),
            rules_path=Path(args.rules),
            dry_run=args.dry_run,
        )
    except FileNotFoundError as exc:
        print(f"[promote_approved_rules] not found: {exc}", file=sys.stderr)
        return 2
    except PromoteError as exc:
        print(f"[promote_approved_rules] FAIL: {exc}", file=sys.stderr)
        return 1

    mode = "(dry-run) " if args.dry_run else ""
    print(
        f"[promote_approved_rules] {mode}OK +{added} rule(s) "
        f"({', '.join(new_ids) if new_ids else 'none'}) → {args.rules}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
