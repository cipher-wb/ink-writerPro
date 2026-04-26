#!/usr/bin/env python3
"""US-LR-005: 批量校验 live-review jsonl 一致性 + 输出 markdown 报告。

Usage:
    python scripts/live-review/validate_jsonl_batch.py \
        --jsonl-dir reports/live-review/

退出码:
    0  全部 jsonl 通过 schema 校验
    1  任一行违反 schema（stderr 列 BVID + 行号 + 字段）/ 输入目录不存在
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
import sys  # noqa: E402
from collections import Counter  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

from jsonschema import Draft202012Validator  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCHEMA_PATH = _REPO_ROOT / "schemas" / "live_review_extracted.schema.json"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Validate live-review jsonl batch and write markdown report."
    )
    p.add_argument("--jsonl-dir", dest="jsonl_dir", required=True, help="jsonl 所在目录")
    p.add_argument(
        "--report-out",
        dest="report_out",
        help="markdown 报告输出路径（默认 reports/live-review-validation-<TS>.md）",
    )
    return p


def _default_report_path() -> Path:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return _REPO_ROOT / "reports" / f"live-review-validation-{ts}.md"


def _validate_file(
    path: Path, validator: Draft202012Validator
) -> tuple[list[dict], list[dict]]:
    """Return (valid_records, issues) where issues=[{line, field, message, ...}]."""
    records: list[dict] = []
    issues: list[dict] = []
    text = path.read_text(encoding="utf-8")
    for idx, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(
                {
                    "line": idx,
                    "field": "<json>",
                    "message": f"not valid JSON: {exc}",
                    "bvid": None,
                }
            )
            continue
        errors = list(validator.iter_errors(record))
        if errors:
            for err in errors:
                field = ".".join(str(x) for x in err.absolute_path) or "<root>"
                issues.append(
                    {
                        "line": idx,
                        "field": field,
                        "message": err.message,
                        "bvid": record.get("bvid"),
                    }
                )
            continue
        records.append(record)
    return records, issues


def _per_file_stats(records: list[dict]) -> dict:
    if not records:
        return {
            "novel_count": 0,
            "score_signal": Counter(),
            "score_present_ratio": 0.0,
            "verdict": Counter(),
        }
    score_signal = Counter(r["score_signal"] for r in records)
    verdict = Counter(r["verdict"] for r in records)
    score_present = sum(1 for r in records if r.get("score") is not None)
    return {
        "novel_count": len(records),
        "score_signal": score_signal,
        "score_present_ratio": score_present / len(records),
        "verdict": verdict,
    }


def _render_report(
    *,
    jsonl_dir: Path,
    file_stats: dict[str, dict],
    file_issues: dict[str, list[dict]],
) -> str:
    lines: list[str] = []
    lines.append("# Live-Review JSONL Batch Validation Report")
    lines.append("")
    lines.append(f"- Generated: {datetime.now(UTC).isoformat(timespec='seconds')}")
    lines.append(f"- jsonl-dir: `{jsonl_dir}`")
    total_files = len(file_stats)
    total_records = sum(s["novel_count"] for s in file_stats.values())
    total_issues = sum(len(v) for v in file_issues.values())
    lines.append(f"- Files: {total_files}")
    lines.append(f"- Records: {total_records}")
    lines.append(f"- Issues: {total_issues}")
    lines.append("")

    if total_issues == 0:
        lines.append("✅ All files passed schema validation.")
    else:
        lines.append("⚠️ Some files have validation issues. See **Validation Issues** below.")
    lines.append("")

    lines.append("## Per-file Statistics")
    lines.append("")
    lines.append("| File | Novels | Score present | Top signal | Top verdict | Issues |")
    lines.append("| --- | ---: | ---: | --- | --- | ---: |")
    for name in sorted(file_stats):
        st = file_stats[name]
        n_issues = len(file_issues.get(name, []))
        top_signal = st["score_signal"].most_common(1)
        top_signal_text = (
            f"{top_signal[0][0]} ({top_signal[0][1]})" if top_signal else "—"
        )
        top_verdict = st["verdict"].most_common(1)
        top_verdict_text = (
            f"{top_verdict[0][0]} ({top_verdict[0][1]})" if top_verdict else "—"
        )
        ratio = f"{st['score_present_ratio']:.0%}"
        lines.append(
            f"| {name} | {st['novel_count']} | {ratio} | {top_signal_text} "
            f"| {top_verdict_text} | {n_issues} |"
        )
    lines.append("")

    lines.append("## Score Signal Distribution")
    lines.append("")
    overall_signal: Counter = Counter()
    for st in file_stats.values():
        overall_signal.update(st["score_signal"])
    lines.append("| Signal | Count |")
    lines.append("| --- | ---: |")
    for signal in ["explicit_number", "sign_phrase", "fuzzy", "unknown"]:
        lines.append(f"| {signal} | {overall_signal.get(signal, 0)} |")
    lines.append("")

    lines.append("## Validation Issues")
    lines.append("")
    if total_issues == 0:
        lines.append("(none)")
    else:
        lines.append("| File | Line | BVID | Field | Message |")
        lines.append("| --- | ---: | --- | --- | --- |")
        for name in sorted(file_issues):
            for issue in file_issues[name]:
                msg = issue["message"].replace("|", "\\|").replace("\n", " ")
                bvid = issue.get("bvid") or "—"
                lines.append(
                    f"| {name} | {issue['line']} | {bvid} | {issue['field']} | {msg} |"
                )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    jsonl_dir = Path(args.jsonl_dir)
    if not jsonl_dir.is_dir():
        print(f"[validate_jsonl_batch] jsonl-dir not found: {jsonl_dir}", file=sys.stderr)
        return 1

    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    file_stats: dict[str, dict] = {}
    file_issues: dict[str, list[dict]] = {}
    for path in sorted(jsonl_dir.glob("*.jsonl")):
        records, issues = _validate_file(path, validator)
        file_stats[path.name] = _per_file_stats(records)
        if issues:
            file_issues[path.name] = issues

    report = _render_report(
        jsonl_dir=jsonl_dir, file_stats=file_stats, file_issues=file_issues
    )
    out_path = Path(args.report_out) if args.report_out else _default_report_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")

    if file_issues:
        for name in sorted(file_issues):
            for issue in file_issues[name]:
                bvid = issue.get("bvid") or "<unknown>"
                print(
                    f"[validate_jsonl_batch] FAIL {name} "
                    f"line={issue['line']} bvid={bvid} field={issue['field']} "
                    f"msg={issue['message']}",
                    file=sys.stderr,
                )
        print(f"[validate_jsonl_batch] report → {out_path}", file=sys.stderr)
        return 1

    print(f"[validate_jsonl_batch] OK {len(file_stats)} files → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
