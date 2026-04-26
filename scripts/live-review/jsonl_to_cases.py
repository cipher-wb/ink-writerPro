#!/usr/bin/env python3
"""US-LR-007: jsonl → CASE-LR-*.yaml 转换器。

把 ``scripts/live-review/run_batch.py`` 产出的每行 jsonl 转成符合
``schemas/case_schema.json`` 的 CASE-LR yaml 病例，存入
``data/case_library/cases/live_review/``。

severity 推导:
    score is None → P3 / score < 55 → P0 / score < 60 → P1 /
    score < 65 → P2 / score >= 65 → P3

layer 推导:
    opening / hook / golden_finger / genre / taboo / character / ops / misc → [upstream]
    pacing / highpoint → [upstream, downstream]
    simplicity → [downstream]
    取所有 comments dimension 的并集；空 comments 兜底 [upstream]。

CLI:
    python3 scripts/live-review/jsonl_to_cases.py \\
        --jsonl-dir data/live-review/extracted \\
        --cases-dir data/case_library/cases/live_review

退出码:
    0  转换全部成功（或 --dry-run 检查通过）
    1  jsonl 解析失败 / case_schema 校验失败
    2  目录参数错误
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
from pathlib import Path  # noqa: E402

import yaml  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ink_writer.case_library.errors import CaseValidationError  # noqa: E402
from ink_writer.case_library.schema import validate_case_dict  # noqa: E402
from ink_writer.live_review.case_id import allocate_live_review_id  # noqa: E402

_DEFAULT_CASES_DIR = _REPO_ROOT / "data" / "case_library" / "cases" / "live_review"
_DEFAULT_YEAR = 2026
_RAW_TEXT_TRUNCATE = 1000

DIMENSION_TO_LAYER: dict[str, list[str]] = {
    "opening": ["upstream"],
    "hook": ["upstream"],
    "golden_finger": ["upstream"],
    "genre": ["upstream"],
    "taboo": ["upstream"],
    "character": ["upstream"],
    "pacing": ["upstream", "downstream"],
    "highpoint": ["upstream", "downstream"],
    "simplicity": ["downstream"],
    "ops": ["upstream"],
    "misc": ["upstream"],
}


def derive_severity(score: int | None) -> str:
    if score is None:
        return "P3"
    if score < 55:
        return "P0"
    if score < 60:
        return "P1"
    if score < 65:
        return "P2"
    return "P3"


def derive_layers(comments: list[dict]) -> list[str]:
    layers: set[str] = set()
    for c in comments:
        layers.update(DIMENSION_TO_LAYER.get(c.get("dimension", ""), ["upstream"]))
    return sorted(layers) or ["upstream"]


def derive_title(title_guess: str, verdict: str, score: int | None) -> str:
    if score is None:
        return f"{title_guess} ({verdict})"
    return f"{title_guess} ({verdict} / {score}分)"


def derive_failure_pattern(
    overall_comment: str,
    comments: list[dict],
    verdict: str,
) -> tuple[str, list[str]]:
    negatives = [c for c in comments if c.get("severity") == "negative"]
    if negatives:
        first_three = negatives[:3]
        joined = ";".join(c["content"] for c in first_three)
        description = f"{overall_comment} | {joined}"
        observable = [f"{c['dimension']}维度: {c['content']}" for c in negatives]
    else:
        description = overall_comment
        observable = [f"整体被星河直播判定为 {verdict}"]
    return description, observable


def _strip_raw_line_range(comment: dict) -> dict:
    return {k: v for k, v in comment.items() if k != "raw_line_range"}


def derive_live_review_meta(record: dict) -> dict:
    return {
        "source_bvid": record["bvid"],
        "source_line_range": [record["line_start"], record["line_end"]],
        "score": record.get("score"),
        "score_raw": record["score_raw"],
        "score_signal": record["score_signal"],
        "verdict": record["verdict"],
        "title_guess": record["title_guess"],
        "genre_guess": record["genre_guess"],
        "overall_comment": record["overall_comment"],
        "comments": [_strip_raw_line_range(c) for c in record["comments"]],
    }


def _ingested_from(jsonl_path: Path) -> str:
    try:
        return str(jsonl_path.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return jsonl_path.name


def record_to_case_dict(record: dict, case_id: str, jsonl_path: Path) -> dict:
    score = record.get("score")
    description, observable = derive_failure_pattern(
        record["overall_comment"],
        record["comments"],
        record["verdict"],
    )
    raw_text = f"{record['score_raw']} | {record['overall_comment']}"[:_RAW_TEXT_TRUNCATE]
    extracted_at = record["extracted_at"]
    ingested_at = extracted_at[:10]  # YYYY-MM-DD from ISO 8601
    return {
        "case_id": case_id,
        "title": derive_title(record["title_guess"], record["verdict"], score),
        "status": "pending",
        "severity": derive_severity(score),
        "domain": "live_review",
        "layer": derive_layers(record["comments"]),
        "tags": ["live_review", f"bvid:{record['bvid']}"],
        "scope": {
            "genre": list(record["genre_guess"]),
            "chapter": ["all_chapters"],
        },
        "source": {
            "type": "editor_review",
            "raw_text": raw_text,
            "ingested_at": ingested_at,
            "ingested_from": _ingested_from(jsonl_path),
            "reviewer": record["model"],
        },
        "failure_pattern": {
            "description": description,
            "observable": observable,
        },
        "live_review_meta": derive_live_review_meta(record),
    }


def _iter_jsonl_files(jsonl_dir: Path):
    """生产 jsonl 输入文件，跳过 _failed.jsonl 等下划线开头文件。"""
    for path in sorted(jsonl_dir.glob("*.jsonl")):
        if path.name.startswith("_"):
            continue
        yield path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Convert live-review jsonl records to CASE-LR-*.yaml case files."
    )
    p.add_argument(
        "--jsonl-dir",
        dest="jsonl_dir",
        required=True,
        help="jsonl 输入目录（扫 *.jsonl，跳过 _failed.jsonl）",
    )
    p.add_argument(
        "--cases-dir",
        dest="cases_dir",
        default=str(_DEFAULT_CASES_DIR),
        help=f"yaml 输出目录 (默认 {_DEFAULT_CASES_DIR})",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="不写盘，仅校验 + 打印汇总",
    )
    p.add_argument(
        "--year",
        type=int,
        default=_DEFAULT_YEAR,
        help=f"case_id 年份 (默认 {_DEFAULT_YEAR})",
    )
    return p


def _run(args: argparse.Namespace) -> int:
    jsonl_dir = Path(args.jsonl_dir)
    if not jsonl_dir.is_dir():
        print(f"[jsonl_to_cases] jsonl-dir not found: {jsonl_dir}", file=sys.stderr)
        return 2

    cases_dir = Path(args.cases_dir)
    if not args.dry_run:
        cases_dir.mkdir(parents=True, exist_ok=True)

    converted: list[str] = []
    seen_pairs: set[tuple[str, int]] = set()  # (bvid, novel_idx) for dup detection

    for jsonl_path in _iter_jsonl_files(jsonl_dir):
        with open(jsonl_path, encoding="utf-8") as f:
            for line_no, raw_line in enumerate(f, 1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(
                        f"[jsonl_to_cases] FAIL {jsonl_path.name} line={line_no}: "
                        f"invalid JSON ({exc})",
                        file=sys.stderr,
                    )
                    return 1

                pair = (record.get("bvid", ""), record.get("novel_idx", -1))
                seen_pairs.add(pair)

                if args.dry_run:
                    placeholder_id = f"CASE-LR-{args.year}-DRYRUN-{len(converted) + 1:04d}"
                    case_dict = record_to_case_dict(record, placeholder_id, jsonl_path)
                else:
                    case_id = allocate_live_review_id(cases_dir, year=args.year)
                    case_dict = record_to_case_dict(record, case_id, jsonl_path)

                # Validate before write (always, even dry-run).
                # Skip for dry-run placeholder IDs (case_id pattern won't match).
                if not args.dry_run:
                    try:
                        validate_case_dict(case_dict)
                    except CaseValidationError as exc:
                        print(
                            f"[jsonl_to_cases] FAIL {jsonl_path.name} line={line_no} "
                            f"bvid={record.get('bvid')}: {exc}",
                            file=sys.stderr,
                        )
                        return 1
                    yaml_path = cases_dir / f"{case_dict['case_id']}.yaml"
                    with open(yaml_path, "w", encoding="utf-8") as out:
                        yaml.safe_dump(
                            case_dict,
                            out,
                            allow_unicode=True,
                            sort_keys=False,
                            default_flow_style=False,
                        )

                converted.append(case_dict["case_id"])

    mode = "dry-run" if args.dry_run else "wrote"
    print(
        f"[jsonl_to_cases] {mode} {len(converted)} case(s) "
        f"({len(seen_pairs)} unique bvid/novel pair(s)) → {cases_dir}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
