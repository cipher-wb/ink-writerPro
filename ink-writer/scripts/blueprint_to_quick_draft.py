#!/usr/bin/env python3
"""Parse blueprint .md file → Quick mode draft.json input.

Plugin-internal copy of ink_writer.core.auto.blueprint_to_quick_draft so it
runs without depending on the outer Python package (which is not bundled with
the plugin). Keep logic in lockstep with the source module:
  ink_writer/core/auto/blueprint_to_quick_draft.py

Public API:
- parse_blueprint(path) -> dict[str, str | None]
- validate(parsed) -> None  (raises BlueprintValidationError)
- to_quick_draft(parsed) -> dict
- BlueprintValidationError
"""
from __future__ import annotations

import re
from pathlib import Path

REQUIRED_FIELDS = ("题材方向", "核心冲突", "主角人设", "金手指类型", "能力一句话")

GF_BLACKLIST = (
    "修为暴涨",
    "无限金币",
    "系统签到",
    "作弊器",
    "外挂",
    "全能系统",
    "签到系统",
)

_PLATFORM_DEFAULTS = {
    "qidian": {"target_chapters": 600, "target_words": 1_800_000, "chapter_words": 3000},
    "fanqie": {"target_chapters": 800, "target_words": 1_200_000, "chapter_words": 1500},
}

OPTIONAL_FIELDS_TRACKED = (
    "书名", "核心卖点", "主角姓名", "主代价", "第一章爽点预览",
    "女主姓名", "女主人设", "钩子1", "钩子2", "钩子3",
)


class BlueprintValidationError(Exception):
    """Raised when blueprint .md fails parse or value-level validation."""


_SECTION_RE = re.compile(r"^###\s+(?:[一二三四五六七八九十]+、)?\s*(.+?)\s*$")


def parse_blueprint(path):
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    sections = {}
    current = None
    for line in lines:
        m = _SECTION_RE.match(line)
        if m:
            name = _normalise_field_name(m.group(1).strip())
            current = name
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)

    return {name: _clean_body(body) for name, body in sections.items()}


def _normalise_field_name(raw):
    raw = raw.strip()
    m = re.match(r"^第\s*([123])\s*章钩子$", raw)
    if m:
        return f"钩子{m.group(1)}"
    raw = re.sub(r"[\(（].*?[\)）]\s*$", "", raw).strip()
    raw = re.sub(r"【[^】]*】\s*$", "", raw).strip()
    aliases = {
        "女主/核心配角姓名": "女主姓名",
        "女主/核心配角人设": "女主人设",
    }
    return aliases.get(raw, raw)


def _clean_body(body_lines):
    cleaned = []
    for ln in body_lines:
        ln = re.sub(r"<!--.*?-->", "", ln).strip()
        if ln.startswith("##") or ln.startswith("---"):
            continue
        if not ln:
            continue
        cleaned.append(ln)
    if not cleaned:
        return None
    return "\n".join(cleaned)


def validate(parsed):
    missing = [f for f in REQUIRED_FIELDS if not (parsed.get(f) or "").strip()]
    if missing:
        raise BlueprintValidationError(f"蓝本缺少必填字段: {', '.join(missing)}")

    gf_text = (parsed.get("能力一句话") or "") + (parsed.get("金手指类型") or "")
    for word in GF_BLACKLIST:
        if word in gf_text:
            raise BlueprintValidationError(
                f"金手指描述命中禁词 '{word}'。请避免：{', '.join(GF_BLACKLIST)}"
            )


def to_quick_draft(parsed):
    platform_raw = (parsed.get("平台") or "qidian").strip().lower()
    platform = "fanqie" if platform_raw in ("fanqie", "番茄", "番茄小说") else "qidian"
    defaults = _PLATFORM_DEFAULTS[platform]

    aggression_raw = (parsed.get("激进度档位") or "2").strip()
    aggression = _coerce_aggression(aggression_raw)

    target_chapters = _coerce_int(parsed.get("目标章数"), defaults["target_chapters"])
    target_words = _coerce_int(parsed.get("目标字数"), defaults["target_words"])
    chapter_words = defaults["chapter_words"]

    draft = {
        "platform": platform,
        "aggression_level": aggression,
        "target_chapters": target_chapters,
        "target_words": target_words,
        "chapter_words": chapter_words,
        "题材方向": parsed.get("题材方向"),
        "核心冲突": parsed.get("核心冲突"),
        "主角人设": parsed.get("主角人设"),
        "金手指类型": parsed.get("金手指类型"),
        "能力一句话": parsed.get("能力一句话"),
    }

    optional_pass_through = ("书名", "核心卖点", "主角姓名", "主代价", "第一章爽点预览",
                             "女主姓名", "女主人设", "钩子1", "钩子2", "钩子3",
                             "元规则倾向", "商业安全边界打破", "语言风格档位",
                             "禁忌/避坑提示", "自由备注", "主角职业/身份")
    for field in optional_pass_through:
        val = parsed.get(field)
        if val and val.strip().upper() != "AUTO":
            draft[field] = val

    missing = []
    for field in OPTIONAL_FIELDS_TRACKED:
        v = parsed.get(field)
        if not v or v.strip().upper() == "AUTO":
            missing.append(field)
    draft["__missing__"] = missing

    return draft


def _coerce_aggression(raw):
    raw = raw.strip().lower()
    mapping = {"1": 1, "保守": 1, "conservative": 1,
               "2": 2, "平衡": 2, "balanced": 2,
               "3": 3, "激进": 3, "aggressive": 3,
               "4": 4, "疯批": 4, "wild": 4, "crazy": 4}
    return mapping.get(raw, 2)


def _coerce_int(raw, default):
    if not raw:
        return default
    try:
        return int(raw.strip())
    except (ValueError, AttributeError):
        return default


def _main():
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Convert blueprint .md to Quick draft.json")
    parser.add_argument("--input", required=True, help="Blueprint .md path")
    parser.add_argument("--output", required=True, help="Output draft.json path")
    args = parser.parse_args()

    try:
        parsed = parse_blueprint(args.input)
        validate(parsed)
        draft = to_quick_draft(parsed)
    except BlueprintValidationError as e:
        print(f"BLUEPRINT_INVALID: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"BLUEPRINT_IO_ERROR: {e}", file=sys.stderr)
        return 3

    Path(args.output).write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"BLUEPRINT_OK: {args.output}")
    return 0


if __name__ == "__main__":
    try:
        import sys as _sys
        from pathlib import Path as _Path
        _sys.path.insert(0, str(_Path(__file__).resolve().parent))
        from runtime_compat import enable_windows_utf8_stdio
        enable_windows_utf8_stdio()
    except Exception:
        pass
    raise SystemExit(_main())
