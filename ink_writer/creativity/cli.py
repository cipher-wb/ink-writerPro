"""v16 US-013 / v18 US-010：creativity validator CLI 入口。

Quick Mode Step 1.5/1.6/1.7 通过 ``python -m ink_writer.creativity`` 调用本模块，
一次性跑 book_title / character_names / golden_finger / sensitive_lexicon 全校验。

用法::

    # Scheme-level 校验（原 US-013 路径）
    python -m ink_writer.creativity validate --input draft.json --output validation.json
    python -m ink_writer.creativity validate --input draft.json    # 默认输出 stdout

    # 单一书名硬校验（v18 US-010）
    python -m ink_writer.creativity.cli validate --book-title '山风穿门' --strict
    # exit 0 → 通过；exit 1 → 命中黑名单/空串，--strict 下转换为 shell 失败信号。

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

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio
_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    '../../ink-writer/scripts',
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass
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


def _validate_book_title_only(title: str) -> dict:
    """v18 US-010：仅跑 book_title 校验，返回与 --input 同 schema 的 payload。"""
    r_title = validate_book_title(title or "")
    suggestion = f"[book_title] {r_title.suggestion}" if r_title.suggestion else ""
    return {
        "all_passed": bool(r_title.passed),
        "results": [
            {
                "scheme_id": "(book_title_only)",
                "passed": bool(r_title.passed),
                "checks": {"book_title": r_title.to_dict()},
                "suggestion": suggestion,
            }
        ],
    }


def cmd_validate(args: argparse.Namespace) -> int:
    # v18 US-010: --book-title 单项快校验路径（ink-init Quick Mode 每次重抽后调用）。
    if getattr(args, "book_title", None) is not None:
        if args.input:
            print(
                "ERROR: --book-title 与 --input 互斥，请只传一个。",
                file=sys.stderr,
            )
            return 2
        output = _validate_book_title_only(args.book_title)
    else:
        if not args.input:
            print("ERROR: 必须提供 --input 或 --book-title 之一。", file=sys.stderr)
            return 2
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

    # v18 US-010: --strict 把业务 fail 转换为 shell exit 1，便于 bash 层 `|| 降档重抽`。
    # 缺省模式（无 --strict）保持 US-013 行为：exit 0 always，由 all_passed 字段驱动。
    if getattr(args, "strict", False) and not output["all_passed"]:
        return 1
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
    # --input 与 --book-title 必选其一（运行时互斥校验，避免 argparse 对 required 配置过严）
    p_validate.add_argument("--input", default=None, help="draft.json 路径（scheme 模式）")
    p_validate.add_argument(
        "--book-title",
        default=None,
        help="v18 US-010：直接单书名校验，用于 ink-init Quick Mode 每次重抽",
    )
    p_validate.add_argument(
        "--output", default=None, help="validation.json 路径（缺省则 stdout）"
    )
    p_validate.add_argument(
        "--strict",
        action="store_true",
        help="v18 US-010：业务 fail 时 exit 1（缺省 exit 0 + all_passed=false）",
    )
    p_validate.set_defaults(func=cmd_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
