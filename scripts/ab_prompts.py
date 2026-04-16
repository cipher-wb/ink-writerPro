#!/usr/bin/env python3
"""
ab_prompts.py — A/B test harness for prompt templates.

Compares two versions of a prompt template by:
  1. Resolving template references in agent specs for both versions
  2. Computing diff statistics (token count, changed sections)
  3. Optionally running both resolved agents through a fixture chapter
     and comparing checker outputs.

Usage:
    python3 scripts/ab_prompts.py --template checker-input-rules.md \
        --version-a 1.0.0 --version-b 1.1.0

    python3 scripts/ab_prompts.py --diff-all   # compare current vs previous

    python3 scripts/ab_prompts.py --list        # list all templates + versions
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
TEMPLATES_DIR = PROJECT_ROOT / "ink-writer" / "templates" / "prompts"
AGENTS_DIR = PROJECT_ROOT / "ink-writer" / "agents"
MANIFEST_PATH = TEMPLATES_DIR / "_manifest.json"

TEMPLATE_REF_PATTERN = re.compile(r"\{\{PROMPT_TEMPLATE:([^}]+)\}\}")
TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+")


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        print(f"Error: manifest not found at {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_template(name: str) -> str:
    path = TEMPLATES_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return path.read_text(encoding="utf-8")


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def resolve_agent(agent_path: Path) -> str:
    text = agent_path.read_text(encoding="utf-8")

    def _replace(m: re.Match) -> str:
        tpl_name = m.group(1).strip()
        try:
            return load_template(tpl_name)
        except FileNotFoundError:
            return m.group(0)

    return TEMPLATE_REF_PATTERN.sub(_replace, text)


def list_templates() -> list[dict[str, Any]]:
    manifest = load_manifest()
    results = []
    for name, info in manifest.get("templates", {}).items():
        tpl_path = TEMPLATES_DIR / info["file"]
        tpl_text = tpl_path.read_text(encoding="utf-8") if tpl_path.exists() else ""
        results.append({
            "name": name,
            "file": info["file"],
            "version": info["version"],
            "consumers": info.get("consumers", []),
            "token_count": len(tokenize(tpl_text)),
            "hash": content_hash(tpl_text),
        })
    return results


def diff_template(template_a: str, template_b: str) -> dict[str, Any]:
    tokens_a = tokenize(template_a)
    tokens_b = tokenize(template_b)
    lines_a = template_a.strip().splitlines()
    lines_b = template_b.strip().splitlines()
    added = [l for l in lines_b if l not in lines_a]
    removed = [l for l in lines_a if l not in lines_b]
    return {
        "tokens_a": len(tokens_a),
        "tokens_b": len(tokens_b),
        "token_delta": len(tokens_b) - len(tokens_a),
        "lines_a": len(lines_a),
        "lines_b": len(lines_b),
        "lines_added": len(added),
        "lines_removed": len(removed),
        "hash_a": content_hash(template_a),
        "hash_b": content_hash(template_b),
        "identical": template_a.strip() == template_b.strip(),
    }


def diff_all_agents() -> list[dict[str, Any]]:
    results = []
    for agent_path in sorted(AGENTS_DIR.glob("*.md")):
        original = agent_path.read_text(encoding="utf-8")
        resolved = resolve_agent(agent_path)
        refs = TEMPLATE_REF_PATTERN.findall(original)
        results.append({
            "agent": agent_path.stem,
            "template_refs": refs,
            "original_tokens": len(tokenize(original)),
            "resolved_tokens": len(tokenize(resolved)),
            "token_delta": len(tokenize(resolved)) - len(tokenize(original)),
            "ref_count": len(refs),
        })
    return results


def cmd_list(args: argparse.Namespace) -> None:
    templates = list_templates()
    print(f"{'Template':<30} {'Version':<10} {'Tokens':<8} {'Hash':<14} {'Consumers'}")
    print("-" * 90)
    for t in templates:
        consumers_str = ", ".join(t["consumers"][:3])
        if len(t["consumers"]) > 3:
            consumers_str += f" +{len(t['consumers']) - 3}"
        print(f"{t['name']:<30} {t['version']:<10} {t['token_count']:<8} {t['hash']:<14} {consumers_str}")


def cmd_diff_all(args: argparse.Namespace) -> None:
    results = diff_all_agents()
    print(f"{'Agent':<30} {'Refs':<6} {'Orig Tok':<10} {'Resolved':<10} {'Delta':<8}")
    print("-" * 70)
    for r in results:
        print(f"{r['agent']:<30} {r['ref_count']:<6} {r['original_tokens']:<10} {r['resolved_tokens']:<10} {r['token_delta']:+<8}")
    total_refs = sum(r["ref_count"] for r in results)
    print(f"\nTotal template references: {total_refs}")
    print(f"Agents with refs: {sum(1 for r in results if r['ref_count'] > 0)}/{len(results)}")


def cmd_template(args: argparse.Namespace) -> None:
    tpl_name = args.template
    try:
        content = load_template(tpl_name)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    tokens = tokenize(content)
    h = content_hash(content)
    manifest = load_manifest()
    tpl_info = manifest.get("templates", {}).get(tpl_name.replace(".md", ""), {})
    print(f"Template: {tpl_name}")
    print(f"Version:  {tpl_info.get('version', 'unknown')}")
    print(f"Tokens:   {len(tokens)}")
    print(f"Hash:     {h}")
    print(f"Consumers: {', '.join(tpl_info.get('consumers', []))}")
    print(f"\n--- Content ---\n{content}")


def cmd_compare(args: argparse.Namespace) -> None:
    tpl_a_path = TEMPLATES_DIR / args.file_a
    tpl_b_path = TEMPLATES_DIR / args.file_b
    if not tpl_a_path.exists():
        print(f"Error: {tpl_a_path} not found", file=sys.stderr)
        sys.exit(1)
    if not tpl_b_path.exists():
        print(f"Error: {tpl_b_path} not found", file=sys.stderr)
        sys.exit(1)
    text_a = tpl_a_path.read_text(encoding="utf-8")
    text_b = tpl_b_path.read_text(encoding="utf-8")
    result = diff_template(text_a, text_b)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="A/B test harness for prompt templates"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List all prompt templates with metadata")

    sub.add_parser("diff-all", help="Show template reference stats for all agents")

    tpl_parser = sub.add_parser("show", help="Show a single template's details")
    tpl_parser.add_argument("template", help="Template filename (e.g. checker-input-rules.md)")

    cmp_parser = sub.add_parser("compare", help="Compare two template files")
    cmp_parser.add_argument("file_a", help="First template file")
    cmp_parser.add_argument("file_b", help="Second template file")

    args = parser.parse_args()
    if args.command == "list":
        cmd_list(args)
    elif args.command == "diff-all":
        cmd_diff_all(args)
    elif args.command == "show":
        cmd_template(args)
    elif args.command == "compare":
        cmd_compare(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
