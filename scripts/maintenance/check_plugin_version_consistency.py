#!/usr/bin/env python3
"""Release self-check: plugin.json ↔ marketplace.json version consistency.

Background
----------
The repo carries two source-of-truth version declarations that must stay in
lock-step:

* ``ink-writer/.claude-plugin/plugin.json`` — the plugin's own version.
* ``.claude-plugin/marketplace.json`` — the marketplace entry advertising that
  same plugin.

Claude Code's plugin manager reads ``marketplace.json`` to decide whether a
new version is available. If only ``plugin.json`` is bumped on release, the
manager keeps serving the old version from cache — which is exactly how
v26.3.0 shipped without ``ink-debug-status`` reaching users (CASE recorded
2026-04-28).

This script is meant to be wired into a release pre-flight (manual run, CI,
or pre-commit). Exits 0 on PASS, 1 on MISMATCH.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_JSON = REPO_ROOT / "ink-writer" / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"missing required manifest: {path}")
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def _find_plugin_entry(marketplace: dict, plugin_name: str) -> dict:
    for entry in marketplace.get("plugins", []):
        if entry.get("name") == plugin_name:
            return entry
    raise KeyError(
        f"plugin {plugin_name!r} not declared in marketplace.json — add an entry"
    )


def check(plugin_path: Path = PLUGIN_JSON, marketplace_path: Path = MARKETPLACE_JSON) -> int:
    plugin = _load_json(plugin_path)
    marketplace = _load_json(marketplace_path)

    plugin_name = plugin["name"]
    plugin_version = plugin["version"]
    market_entry = _find_plugin_entry(marketplace, plugin_name)
    market_version = market_entry.get("version")

    if plugin_version == market_version:
        print(
            f"PASS  {plugin_name} version aligned: "
            f"plugin.json={plugin_version} marketplace.json={market_version}"
        )
        return 0

    print(
        f"FAIL  {plugin_name} version mismatch:\n"
        f"        plugin.json      = {plugin_version}   ({plugin_path})\n"
        f"        marketplace.json = {market_version}   ({marketplace_path})\n"
        f"      → bump marketplace.json to {plugin_version} before releasing.",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    try:
        from runtime_compat import enable_windows_utf8_stdio

        enable_windows_utf8_stdio()
    except Exception:  # Mac/Linux no-op when helper not on sys.path
        pass

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--plugin-json",
        type=Path,
        default=PLUGIN_JSON,
        help=f"Path to plugin.json (default: {PLUGIN_JSON})",
    )
    parser.add_argument(
        "--marketplace-json",
        type=Path,
        default=MARKETPLACE_JSON,
        help=f"Path to marketplace.json (default: {MARKETPLACE_JSON})",
    )
    args = parser.parse_args(argv)
    return check(args.plugin_json, args.marketplace_json)


if __name__ == "__main__":
    raise SystemExit(main())
