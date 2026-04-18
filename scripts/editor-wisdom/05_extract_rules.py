#!/usr/bin/env python3
"""Extract atomic machine-consumable rules from classified editor wisdom content.

v13 US-007 修复：入口 API Key 校验 + 连续 5 次失败 abort（v5 审计 Critical）。
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from ink_writer.editor_wisdom.llm_backend import call_llm
from ink_writer.editor_wisdom.models import SONNET_MODEL

MAX_CONSECUTIVE_FAILURES = 5  # v13 US-007

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "editor-wisdom"

CATEGORIES = [
    "opening", "hook", "golden_finger", "character", "pacing",
    "highpoint", "taboo", "genre", "ops", "misc",
]

GOLDEN_THREE_CATEGORIES = frozenset({"opening", "hook", "golden_finger", "character"})

SEVERITY_VALUES = ["hard", "soft", "info"]

VALID_APPLIES_TO = frozenset({"all_chapters", "golden_three", "opening_only"})

SYSTEM_PROMPT = """\
你是一名网文写作规则提取器。给定一篇编辑建议文章及其分类，你需要提取出具体的、可执行的写作规则。

每条规则必须：
1. rule字段用祈使句中文表达，不超过120个字符
2. 包含why字段解释原因
3. 标注severity: hard(必须遵守)、soft(建议遵守)、info(了解即可)
4. 标注applies_to: 规则适用场景列表，如 ["all_chapters"]、["golden_three"]、["opening"]、["dialogue"]等

请以JSON数组格式回复，不要包含任何其他文字：
[
  {
    "rule": "祈使句规则文本",
    "why": "原因说明",
    "severity": "hard|soft|info",
    "applies_to": ["场景1", "场景2"]
  }
]

注意：
- 只提取具体可操作的规则，不要泛泛而谈
- 每篇文章提取1-5条规则
- 如果文章内容不包含可操作建议（如纯运营/数据类），返回空数组 []
"""


def _read_body(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""


def _load_cache(data_dir: Path) -> dict[str, list[dict]]:
    cache_path = data_dir / "rules_cache.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    return {}


def _save_cache(data_dir: Path, cache: dict[str, list[dict]]) -> None:
    cache_path = data_dir / "rules_cache.json"
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_from_one(body: str, title: str, categories: list[str]) -> list[dict]:
    user_text = (
        f"文章标题：{title}\n"
        f"已分类主题：{', '.join(categories)}\n\n"
        f"文章内容：\n{body[:4000]}"
    )

    text = call_llm(SONNET_MODEL, SYSTEM_PROMPT, user_text, max_tokens=1024).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]

    raw_rules = json.loads(text)
    if not isinstance(raw_rules, list):
        return []

    valid_rules = []
    for r in raw_rules:
        if not isinstance(r, dict):
            continue
        rule_text = r.get("rule", "")
        if not rule_text or len(rule_text) > 120:
            continue
        severity = r.get("severity", "info")
        if severity not in SEVERITY_VALUES:
            severity = "info"
        applies_to = r.get("applies_to", ["all_chapters"])
        if not isinstance(applies_to, list) or not applies_to:
            applies_to = ["all_chapters"]
        applies_to = [v for v in applies_to if v in VALID_APPLIES_TO]
        if not applies_to:
            applies_to = ["all_chapters"]
        valid_rules.append({
            "rule": rule_text,
            "why": r.get("why", ""),
            "severity": severity,
            "applies_to": applies_to,
        })

    return valid_rules


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


def extract_rules(data_dir: Path) -> dict[str, int]:
    classified_path = data_dir / "classified.json"
    entries: list[dict] = json.loads(classified_path.read_text(encoding="utf-8"))

    cache = _load_cache(data_dir)

    all_rules: list[dict] = []
    rule_counter = 1
    cached_count = 0
    api_count = 0
    unflushed = 0
    last_flush = time.monotonic()

    consecutive_failures = 0  # v13 US-007

    try:
        for idx, entry in enumerate(entries, 1):
            file_hash = entry["file_hash"]
            categories = entry.get("categories", ["misc"])

            if file_hash in cache:
                raw_rules = cache[file_hash]
                cached_count += 1
            else:
                body = _read_body(entry["path"])
                if not body:
                    raw_rules = []
                else:
                    try:
                        print(f"[{idx}/{len(entries)}] {entry['filename'][:50]}", flush=True)
                        raw_rules = _extract_from_one(body, entry["title"], categories)
                        consecutive_failures = 0
                    except Exception as exc:
                        print(f"  ERR: {type(exc).__name__}: {str(exc)[:100]}", flush=True)
                        _append_error(data_dir, file_hash, entry.get("filename", ""), exc)
                        consecutive_failures += 1
                        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                            sys.exit(
                                f"ERROR: {consecutive_failures} consecutive API failures, "
                                f"aborting to preserve cost. Check errors.log for details. "
                                f"Last error: {type(exc).__name__}: {exc}"
                            )
                        continue
                cache[file_hash] = raw_rules
                api_count += 1
                unflushed += 1

                if unflushed >= 10 or (time.monotonic() - last_flush) >= 60:
                    _save_cache(data_dir, cache)
                    unflushed = 0
                    last_flush = time.monotonic()

            primary_cat = categories[0] if categories else "misc"
            for r in raw_rules:
                all_rules.append({
                    "id": f"EW-{rule_counter:04d}",
                    "category": primary_cat,
                    "rule": r["rule"],
                    "why": r["why"],
                    "severity": r["severity"],
                    "applies_to": r["applies_to"],
                    "source_files": [entry["filename"]],
                })
                rule_counter += 1
    finally:
        _save_cache(data_dir, cache)

    _deduplicate_rules(all_rules)
    _apply_golden_three_tag(all_rules)

    out_path = data_dir / "rules.json"
    out_path.write_text(json.dumps(all_rules, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"total": len(all_rules), "cached": cached_count, "api_calls": api_count}


def _apply_golden_three_tag(rules: list[dict]) -> None:
    for rule in rules:
        if rule.get("category") in GOLDEN_THREE_CATEGORIES:
            if "golden_three" not in rule.get("applies_to", []):
                rule["applies_to"].append("golden_three")


def _deduplicate_rules(rules: list[dict]) -> None:
    seen: dict[str, int] = {}
    to_remove: list[int] = []

    for i, rule in enumerate(rules):
        key = rule["rule"]
        if key in seen:
            orig_idx = seen[key]
            orig = rules[orig_idx]
            for sf in rule["source_files"]:
                if sf not in orig["source_files"]:
                    orig["source_files"].append(sf)
            to_remove.append(i)
        else:
            seen[key] = i

    for idx in reversed(to_remove):
        rules.pop(idx)

    for i, rule in enumerate(rules):
        rule["id"] = f"EW-{i + 1:04d}"


def main() -> None:
    # v13 US-007 / US-026：入口 API_KEY 校验。exit=2 作为 "missing credentials" 约定
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ERROR: ANTHROPIC_API_KEY not set. "
            "This script requires a valid key to extract rules via Claude Sonnet. "
            "Set it via `export ANTHROPIC_API_KEY=sk-...` and retry.",
            file=sys.stderr,
        )
        sys.exit(2)

    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA_DIR

    if not (data_dir / "classified.json").exists():
        print("Error: classified.json not found. Run 03_classify.py first.", file=sys.stderr)
        sys.exit(1)

    stats = extract_rules(data_dir)
    print(f"Extracted: {stats['total']} rules (cached: {stats['cached']}, API calls: {stats['api_calls']})")
    print(f"Output: {data_dir / 'rules.json'}")


if __name__ == "__main__":
    main()
