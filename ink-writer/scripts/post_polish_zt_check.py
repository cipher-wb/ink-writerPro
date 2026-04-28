#!/usr/bin/env python3
"""Post-polish zero-tolerance check.

Used by ink-write Step 4.5.5 to catch AI fingerprints that polish-agent may
have re-introduced (e.g. ——, 不仅而且, 与此同时). Reads the same
zero_tolerance list from config/anti-detection.yaml as the in-flight Step 3.8
gate, but runs *after* polish so it covers the final on-disk text.

Exit codes:
  0  no violations
  1  zero-tolerance hit (one or more rule IDs reported on stderr with line numbers)
  2  config or chapter file missing / unreadable
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def _try_load_yaml(path: Path) -> dict | None:
    try:
        import yaml
    except ImportError:
        try:
            from ruamel.yaml import YAML
            return YAML(typ="safe").load(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _check_regex(rule: dict, text: str, lines: list[str]) -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    rule_id = rule.get("id", "?")
    patterns = rule.get("patterns", [])
    is_first_line_only = rule_id == "ZT_TIME_OPENING"

    if is_first_line_only:
        first_non_empty = next((ln for ln in lines if ln.strip()), "")
        for pat in patterns:
            try:
                if re.search(pat, first_non_empty.strip()):
                    hits.append((rule_id, 1, first_non_empty.strip()[:60]))
                    break
            except re.error:
                continue
        return hits

    for pat in patterns:
        try:
            for ln_no, ln in enumerate(lines, 1):
                if re.search(pat, ln):
                    hits.append((rule_id, ln_no, ln.strip()[:60]))
                    break
            if hits and hits[-1][0] == rule_id:
                break
        except re.error:
            continue
    return hits


def _check_density(rule: dict, text: str) -> list[tuple[str, int, str]]:
    rule_id = rule.get("id", "?")
    patterns = rule.get("patterns", [])
    threshold = rule.get("density_threshold", 0)
    char_count = len(text)
    if char_count == 0:
        return []
    total_hits = 0
    for pat in patterns:
        try:
            total_hits += len(re.findall(pat, text))
        except re.error:
            continue
    density = (total_hits / char_count) * 1000.0
    if density > threshold:
        return [(rule_id, 0, f"density={density:.2f}/千字 > {threshold}")]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--chapter", required=True, help="Path to polished chapter .md")
    parser.add_argument("--config", required=True, help="Path to anti-detection.yaml")
    args = parser.parse_args()

    chapter_path = Path(args.chapter)
    config_path = Path(args.config)

    if not chapter_path.exists():
        print(f"POST_POLISH_ZT: chapter file not found: {chapter_path}", file=sys.stderr)
        return 2
    if not config_path.exists():
        print(f"POST_POLISH_ZT: config file not found: {config_path}", file=sys.stderr)
        return 2

    cfg = _try_load_yaml(config_path)
    if cfg is None:
        print(f"POST_POLISH_ZT: failed to parse {config_path}", file=sys.stderr)
        return 2

    if not cfg.get("enabled", True):
        return 0
    if not cfg.get("prose_overhaul_enabled", True):
        return 0

    rules = cfg.get("zero_tolerance", []) or []
    if not rules:
        return 0

    try:
        text = chapter_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"POST_POLISH_ZT: cannot read chapter: {e}", file=sys.stderr)
        return 2

    lines = text.splitlines()
    all_hits: list[tuple[str, int, str]] = []

    for rule in rules:
        kind = rule.get("kind", "regex")
        if kind == "density":
            all_hits.extend(_check_density(rule, text))
        else:
            all_hits.extend(_check_regex(rule, text, lines))

    if not all_hits:
        return 0

    print("POST_POLISH_ZT: zero-tolerance violations after polish:", file=sys.stderr)
    for rid, ln, snippet in all_hits:
        loc = f"line {ln}" if ln else "whole text"
        print(f"  [{rid}] {loc}: {snippet}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        import sys as _sys
        from pathlib import Path as _Path
        _sys.path.insert(0, str(_Path(__file__).resolve().parent))
        from runtime_compat import enable_windows_utf8_stdio
        enable_windows_utf8_stdio()
    except Exception:
        pass
    sys.exit(main())
