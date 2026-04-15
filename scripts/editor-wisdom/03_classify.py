#!/usr/bin/env python3
"""Classify cleaned files into 10 fixed topic categories via Claude Haiku."""

from __future__ import annotations

import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from ink_writer.editor_wisdom.llm_backend import call_llm
from ink_writer.editor_wisdom.models import HAIKU_MODEL

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "editor-wisdom"

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

SYSTEM_PROMPT = """\
你是一名网文编辑建议分类器。给定一篇编辑建议文章，你需要：
1. 判断它属于以下哪些主题分类（可以多选）
2. 用一句话总结其核心建议

主题分类列表：
- opening: 开篇/开头写法
- hook: 钩子/吸引力/悬念设计
- golden_finger: 金手指/主角能力设定
- character: 人物塑造/角色设计
- pacing: 节奏/结构/章节安排
- highpoint: 爽点/高潮/情绪高点
- taboo: 禁忌/常见错误/雷区
- genre: 题材/类型/市场趋势
- ops: 运营/签约/稿费/推荐
- misc: 其他/综合建议

请以JSON格式回复，不要包含任何其他文字：
{"categories": ["category1", "category2"], "summary": "一句话总结"}
"""


def _read_body(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""


def _load_cache(data_dir: Path) -> dict[str, dict]:
    cache_path = data_dir / "classify_cache.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    return {}


def _save_cache(data_dir: Path, cache: dict[str, dict]) -> None:
    cache_path = data_dir / "classify_cache.json"
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _classify_one(body: str, title: str) -> dict:
    user_text = f"文章标题：{title}\n\n文章内容：\n{body[:3000]}"

    text = call_llm(HAIKU_MODEL, SYSTEM_PROMPT, user_text, max_tokens=256).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    result = json.loads(text)

    cats = [c for c in result.get("categories", []) if c in CATEGORIES]
    if not cats:
        cats = ["misc"]

    return {
        "categories": cats,
        "summary": result.get("summary", ""),
    }


def _append_error(data_dir: Path, file_hash: str, filename: str, error: Exception) -> None:
    error_entry = {
        "file_hash": file_hash,
        "filename": filename,
        "error_type": type(error).__name__,
        "error_msg": str(error),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    error_path = data_dir / "errors.log"
    with open(error_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(error_entry, ensure_ascii=False) + "\n")


def classify(data_dir: Path) -> dict[str, int]:
    clean_path = data_dir / "clean_index.json"
    entries: list[dict] = json.loads(clean_path.read_text(encoding="utf-8"))

    cache = _load_cache(data_dir)

    classified: list[dict] = []
    cached_count = 0
    api_count = 0
    unflushed = 0
    last_flush = time.monotonic()

    try:
        for entry in entries:
            file_hash = entry["file_hash"]

            if file_hash in cache:
                result = cache[file_hash]
                cached_count += 1
            else:
                body = _read_body(entry["path"])
                if not body:
                    result = {"categories": ["misc"], "summary": ""}
                else:
                    try:
                        result = _classify_one(body, entry["title"])
                    except Exception as exc:
                        _append_error(data_dir, file_hash, entry.get("filename", ""), exc)
                        continue
                cache[file_hash] = result
                api_count += 1
                unflushed += 1

                if unflushed >= 10 or (time.monotonic() - last_flush) >= 60:
                    _save_cache(data_dir, cache)
                    unflushed = 0
                    last_flush = time.monotonic()

            classified.append({
                **entry,
                "categories": result["categories"],
                "summary": result["summary"],
            })
    finally:
        _save_cache(data_dir, cache)

    out_path = data_dir / "classified.json"
    out_path.write_text(json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8")

    _build_report(data_dir, classified)

    return {"total": len(classified), "cached": cached_count, "api_calls": api_count}


def _build_report(data_dir: Path, classified: list[dict]) -> None:
    cat_counts: dict[str, int] = {c: 0 for c in CATEGORIES}
    for entry in classified:
        for c in entry["categories"]:
            if c in cat_counts:
                cat_counts[c] += 1

    lines = [
        "# Classification Report\n",
        "## Category Distribution\n",
        "| Category | Count |",
        "|----------|-------|",
    ]
    for cat in CATEGORIES:
        lines.append(f"| {cat} | {cat_counts[cat]} |")
    lines.append("")
    lines.append(f"Total files: {len(classified)}\n")

    lines.append("## Random Samples (20)\n")
    samples = random.sample(classified, min(20, len(classified)))
    for i, s in enumerate(samples, 1):
        cats = ", ".join(s["categories"])
        lines.append(f"{i}. **{s['title']}** [{cats}]")
        lines.append(f"   > {s['summary']}")
        lines.append("")

    report_path = data_dir / "classify_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA_DIR

    if not (data_dir / "clean_index.json").exists():
        print("Error: clean_index.json not found. Run 02_clean.py first.", file=sys.stderr)
        sys.exit(1)

    stats = classify(data_dir)
    print(f"Classified: {stats['total']} (cached: {stats['cached']}, API calls: {stats['api_calls']})")
    print(f"Output: {data_dir / 'classified.json'}")


if __name__ == "__main__":
    main()
