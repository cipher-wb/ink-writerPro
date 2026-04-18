"""v16 US-013：creativity validator CLI 入口。

Quick Mode Step 1.5/1.6/1.7 通过 ``python -m ink_writer.creativity`` 调用本模块，
一次性跑 book_title / character_names / golden_finger / sensitive_lexicon 全校验。

用法::

    python -m ink_writer.creativity validate --input draft.json --output validation.json
    python -m ink_writer.creativity validate --input draft.json    # 默认输出 stdout

draft.json schema::

    {
      "schemes": [
        {
          "id": "scheme_1",
          "book_title": "山风穿门",
          "character_names": [
            {"name": "卫砚之", "role": "main"},
            {"name": "陆云", "role": "side"}
          ],
          "golden_finger": {
            "dimension": "信息",
            "cost": "每次使用扣减 1 年寿命，触发即被对手同步定位。",
            "one_liner": "我能听见死人的谎话，但每次少一年。"
          },
          "voice": "V1",
          "aggression": 2,
          "sample_chapter_text": "..."
        }
      ]
    }

输出 validation.json::

    {
      "all_passed": false,
      "results": [
        {
          "scheme_id": "scheme_1",
          "passed": false,
          "checks": {
            "book_title": {...},
            "character_names": [{"name": "...", ...}],
            "golden_finger": {...},
            "sensitive_lexicon": {...}
          },
          "suggestion": "（聚合 4 个子校验的 suggestion）"
        }
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ink_writer.creativity.gf_validator import validate_golden_finger
from ink_writer.creativity.name_validator import (
    ValidationResult,
    validate_book_title,
    validate_character_name,
)
from ink_writer.creativity.sensitive_lexicon_validator import validate_density


def _validate_scheme(scheme: dict) -> dict:
    """单套方案的四维综合校验。"""
    checks: dict[str, Any] = {}
    suggestions: list[str] = []
    passed = True

    # book_title
    title = scheme.get("book_title") or ""
    r_title = validate_book_title(title)
    checks["book_title"] = r_title.to_dict()
    if not r_title.passed:
        passed = False
    if r_title.suggestion:
        suggestions.append(f"[book_title] {r_title.suggestion}")

    # character_names
    name_results: list[dict] = []
    for entry in scheme.get("character_names", []) or []:
        name = entry.get("name", "")
        role = entry.get("role", "main")
        r_name = validate_character_name(name, role=role)
        item = r_name.to_dict()
        item["name"] = name
        item["role"] = role
        name_results.append(item)
        if not r_name.passed:
            passed = False
        if r_name.suggestion:
            suggestions.append(f"[name:{name}] {r_name.suggestion}")
    checks["character_names"] = name_results

    # golden_finger（可选）
    gf_spec = scheme.get("golden_finger")
    if gf_spec:
        r_gf = validate_golden_finger(gf_spec)
        checks["golden_finger"] = r_gf.to_dict()
        if not r_gf.passed:
            passed = False
        if r_gf.suggestion:
            suggestions.append(f"[golden_finger] {r_gf.suggestion}")

    # sensitive_lexicon（可选：需 voice + aggression + sample_chapter_text）
    text = scheme.get("sample_chapter_text") or ""
    voice = scheme.get("voice")
    agg = scheme.get("aggression")
    if text and voice and isinstance(agg, int):
        r_lex = validate_density(text, voice=voice, aggression=agg)
        checks["sensitive_lexicon"] = r_lex.to_dict()
        if not r_lex.passed:
            passed = False
        if r_lex.suggestion:
            suggestions.append(f"[lexicon] {r_lex.suggestion}")

    return {
        "scheme_id": scheme.get("id", "(unknown)"),
        "passed": passed,
        "checks": checks,
        "suggestion": "\n".join(suggestions),
    }


def cmd_validate(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: input 文件不存在: {input_path}", file=sys.stderr)
        return 2
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: input 非法 JSON: {exc}", file=sys.stderr)
        return 2

    schemes = data.get("schemes") or []
    results = [_validate_scheme(s) for s in schemes]
    all_passed = bool(results) and all(r["passed"] for r in results)

    output = {"all_passed": all_passed, "results": results}
    payload = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    else:
        print(payload)

    # exit 0 always（HARD 违规不走 shell exit，而靠 all_passed 字段）
    # 方便 skill 层决定"拦下重抽"还是"仅警告"。
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ink_writer.creativity",
        description="creativity validator CLI（US-013）",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_validate = sub.add_parser(
        "validate", help="一次性跑 book_title/name/gf/lexicon 全校验"
    )
    p_validate.add_argument("--input", required=True, help="draft.json 路径")
    p_validate.add_argument(
        "--output", default=None, help="validation.json 路径（缺省则 stdout）"
    )
    p_validate.set_defaults(func=cmd_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
