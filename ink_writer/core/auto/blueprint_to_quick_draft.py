# ink_writer/core/auto/blueprint_to_quick_draft.py
"""Parse blueprint .md file → Quick mode draft.json input.

Public API:
- parse_blueprint(path) -> dict[str, str | None]
- validate(parsed) -> None  (raises BlueprintValidationError)
- to_quick_draft(parsed) -> dict
- BlueprintValidationError
"""
from __future__ import annotations

import re
from pathlib import Path

# Required fields — blueprint must have non-empty values for these or validation fails
REQUIRED_FIELDS = ("题材方向", "核心冲突", "主角人设", "金手指类型", "能力一句话")

# Golden-finger禁词（命中即失败）
GF_BLACKLIST = (
    "修为暴涨",
    "无限金币",
    "系统签到",
    "作弊器",
    "外挂",
    "全能系统",
    "签到系统",
)

# Platform defaults — sourced from ink-init SKILL.md Quick Step 0.4 v26.2 (line 91-104)
_PLATFORM_DEFAULTS = {
    "qidian": {"target_chapters": 600, "target_words": 1_800_000, "chapter_words": 3000},
    "fanqie": {"target_chapters": 800, "target_words": 1_200_000, "chapter_words": 1500},
}

# Optional fields tracked in __missing__ so Quick engine knows to auto-fill
OPTIONAL_FIELDS_TRACKED = (
    "书名", "核心卖点", "主角姓名", "主代价", "第一章爽点预览",
    "女主姓名", "女主人设", "钩子1", "钩子2", "钩子3",
)


class BlueprintValidationError(Exception):
    """Raised when blueprint .md fails parse or value-level validation."""


# Section header pattern: "### 字段名" → captures field name; allows trailing spaces / 全角
_SECTION_RE = re.compile(r"^###\s+(?:[一二三四五六七八九十]+、)?\s*(.+?)\s*$")


def parse_blueprint(path: Path | str) -> dict[str, str | None]:
    """Parse blueprint .md → flat dict {字段名: 值 or None}.

    HTML comments (<!-- ... -->) within section body are stripped.
    Empty sections map to None.
    """
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        m = _SECTION_RE.match(line)
        if m:
            # Normalise: strip variants like "第 1 章钩子" → "钩子1"
            name = _normalise_field_name(m.group(1).strip())
            current = name
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)

    return {name: _clean_body(body) for name, body in sections.items()}


def _normalise_field_name(raw: str) -> str:
    raw = raw.strip()
    # Map "第 N 章钩子" → "钩子N"
    m = re.match(r"^第\s*([123])\s*章钩子$", raw)
    if m:
        return f"钩子{m.group(1)}"
    # Strip trailing parenthetical hints like "(选填)"
    raw = re.sub(r"[\(（].*?[\)）]\s*$", "", raw).strip()
    aliases = {
        "女主/核心配角姓名": "女主姓名",
        "女主/核心配角人设": "女主人设",
    }
    return aliases.get(raw, raw)


def _clean_body(body_lines: list[str]) -> str | None:
    cleaned: list[str] = []
    for ln in body_lines:
        # Drop HTML comments (single-line)
        ln = re.sub(r"<!--.*?-->", "", ln).strip()
        # Drop subsection markers and empty
        if ln.startswith("##") or ln.startswith("---"):
            continue
        if not ln:
            continue
        cleaned.append(ln)
    if not cleaned:
        return None
    return "\n".join(cleaned)


def validate(parsed: dict[str, str | None]) -> None:
    missing = [f for f in REQUIRED_FIELDS if not (parsed.get(f) or "").strip()]
    if missing:
        raise BlueprintValidationError(f"蓝本缺少必填字段: {', '.join(missing)}")

    gf_text = (parsed.get("能力一句话") or "") + (parsed.get("金手指类型") or "")
    for word in GF_BLACKLIST:
        if word in gf_text:
            raise BlueprintValidationError(
                f"金手指描述命中禁词 '{word}'。请避免：{', '.join(GF_BLACKLIST)}"
            )


def to_quick_draft(parsed: dict[str, str | None]) -> dict:
    platform_raw = (parsed.get("平台") or "qidian").strip().lower()
    platform = "fanqie" if platform_raw in ("fanqie", "番茄", "番茄小说") else "qidian"
    defaults = _PLATFORM_DEFAULTS[platform]

    aggression_raw = (parsed.get("激进度档位") or "2").strip()
    aggression = _coerce_aggression(aggression_raw)

    target_chapters = _coerce_int(parsed.get("目标章数"), defaults["target_chapters"])
    target_words = _coerce_int(parsed.get("目标字数"), defaults["target_words"])
    chapter_words = defaults["chapter_words"]

    draft: dict = {
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

    missing: list[str] = []
    for field in OPTIONAL_FIELDS_TRACKED:
        v = parsed.get(field)
        if not v or v.strip().upper() == "AUTO":
            missing.append(field)
    draft["__missing__"] = missing

    return draft


def _coerce_aggression(raw: str) -> int:
    raw = raw.strip().lower()
    mapping = {"1": 1, "保守": 1, "conservative": 1,
               "2": 2, "平衡": 2, "balanced": 2,
               "3": 3, "激进": 3, "aggressive": 3,
               "4": 4, "疯批": 4, "wild": 4, "crazy": 4}
    return mapping.get(raw, 2)


def _coerce_int(raw: str | None, default: int) -> int:
    if not raw:
        return default
    try:
        return int(raw.strip())
    except (ValueError, AttributeError):
        return default


def _main() -> int:
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
    # CLAUDE.md mandate: Python entry points must enable UTF-8 stdio on Windows
    try:
        import sys as _sys
        from pathlib import Path as _Path
        _scripts_dir = _Path(__file__).resolve().parent.parent.parent.parent / "ink-writer" / "scripts"
        _sys.path.insert(0, str(_scripts_dir))
        from runtime_compat import enable_windows_utf8_stdio  # type: ignore
        enable_windows_utf8_stdio()
    except Exception:
        pass  # Best-effort; -X utf8 flag in shell invocation is the primary path
    raise SystemExit(_main())
