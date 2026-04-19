#!/usr/bin/env python3
"""Build human-readable knowledge base from classified entries."""

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
import json
import sys
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "editor-wisdom"
DEFAULT_DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "editor-wisdom"

CATEGORIES = [
    "opening",
    "hook",
    "golden_finger",
    "character",
    "pacing",
    "highpoint",
    "taboo",
    "genre",
    "ops",
    "misc",
]

CATEGORY_NAMES: dict[str, str] = {
    "opening": "开篇写法",
    "hook": "钩子与悬念设计",
    "golden_finger": "金手指与主角能力设定",
    "character": "人物塑造与角色设计",
    "pacing": "节奏与结构安排",
    "highpoint": "爽点与情绪高潮",
    "taboo": "禁忌与常见雷区",
    "genre": "题材与市场趋势",
    "ops": "运营与签约技巧",
    "misc": "综合建议",
}

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "opening": "如何写出抓人的开篇，让读者在前几段就被吸引",
    "hook": "悬念钩子的设计技巧，提升追读率",
    "golden_finger": "金手指与主角能力的合理设定，避免过强或过弱",
    "character": "人物塑造方法论，让角色立体有魅力",
    "pacing": "章节节奏与全书结构的把控技巧",
    "highpoint": "爽点设计与情绪高潮的安排策略",
    "taboo": "网文写作常见雷区与禁忌，避免踩坑",
    "genre": "各类题材的市场趋势与写作要点",
    "ops": "签约、推荐、稿费等运营相关的实用建议",
    "misc": "其他综合性的写作建议",
}


def _read_body(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""


def _extract_quote(body: str, max_len: int = 200) -> str:
    lines = [l.strip() for l in body.split("\n") if l.strip() and not l.strip().startswith("#")]
    for line in lines:
        if len(line) >= 20:
            return line[:max_len] + ("…" if len(line) > max_len else "")
    if lines:
        return lines[0][:max_len]
    return ""


def build_kb(data_dir: Path, docs_dir: Path) -> dict[str, int]:
    classified_path = data_dir / "classified.json"
    entries: list[dict] = json.loads(classified_path.read_text(encoding="utf-8"))

    cat_entries: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    for entry in entries:
        for cat in entry.get("categories", []):
            if cat in cat_entries:
                cat_entries[cat].append(entry)

    docs_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    for cat in CATEGORIES:
        items = cat_entries[cat]
        counts[cat] = len(items)
        _write_category_file(docs_dir, cat, items)

    _write_readme(docs_dir, counts)
    return counts


def _write_category_file(docs_dir: Path, cat: str, items: list[dict]) -> None:
    name = CATEGORY_NAMES[cat]
    lines: list[str] = [f"# {name}\n"]

    summaries = [e["summary"] for e in items if e.get("summary")]
    unique_summaries = list(dict.fromkeys(summaries))
    principles = unique_summaries[:10]

    lines.append("## 核心原则\n")
    if principles:
        for p in principles:
            lines.append(f"- {p}")
    else:
        lines.append("- （暂无条目）")
    lines.append("")

    lines.append("## 详细建议\n")
    if items:
        for entry in items:
            title = entry.get("title", entry.get("filename", "未知"))
            source = entry.get("filename", "")
            platform = entry.get("platform", "")
            platform_label = "小红书" if platform == "xhs" else "抖音" if platform == "douyin" else platform

            body = _read_body(entry.get("path", ""))
            quote = _extract_quote(body) if body else entry.get("summary", "")

            lines.append(f"### {title}\n")
            if quote:
                lines.append(f"> {quote}\n")
            lines.append(f"来源：{source}（{platform_label}）\n")
    else:
        lines.append("（暂无条目）\n")

    path = docs_dir / f"{cat}.md"
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_readme(docs_dir: Path, counts: dict[str, int]) -> None:
    lines = [
        "# 编辑星河写作智慧知识库\n",
        "基于编辑星河在小红书/抖音发布的写作建议，按主题整理的结构化知识库。\n",
        "## 目录\n",
    ]

    for cat in CATEGORIES:
        name = CATEGORY_NAMES[cat]
        desc = CATEGORY_DESCRIPTIONS[cat]
        count = counts.get(cat, 0)
        lines.append(f"- [{name}]({cat}.md) — {desc}（{count} 篇）")

    lines.append("")
    total = sum(counts.values())
    lines.append(f"共计 {total} 条建议条目（含多分类重复计数）。\n")

    path = docs_dir / "README.md"
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA_DIR
    docs_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_DOCS_DIR

    if not (data_dir / "classified.json").exists():
        print("Error: classified.json not found. Run 03_classify.py first.", file=sys.stderr)
        sys.exit(1)

    counts = build_kb(data_dir, docs_dir)
    total = sum(counts.values())
    print(f"Built knowledge base: {total} entries across {len(CATEGORIES)} categories")
    print(f"Output: {docs_dir}/")


if __name__ == "__main__":
    main()
