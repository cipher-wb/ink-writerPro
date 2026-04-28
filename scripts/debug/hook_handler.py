#!/usr/bin/env python3
"""Claude Code hook → ink_writer.debug.collector adapter.

Invoked by .claude/settings.json hooks. Reads the hook event JSON from stdin,
constructs an Incident, calls Collector.record(). Always exits 0 (never blocks
the host hook).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _project_root() -> Path:
    # Honor INK_PROJECT_ROOT env if set; else cwd.
    return Path(os.environ.get("INK_PROJECT_ROOT") or os.getcwd())


def _run_id() -> str:
    return os.environ.get("INK_DEBUG_RUN_ID") or f"cc-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"


def _hook_kind(event_name: str) -> str:
    mapping = {
        "PreToolUse": "hook.pre_tool_use",
        "PostToolUse": "hook.post_tool_use",
        "SubagentStop": "hook.subagent_stop",
        "Stop": "hook.stop",
        "SessionEnd": "hook.session_end",
    }
    return mapping.get(event_name, "hook.post_tool_use")


def _severity(event_name: str, payload: dict) -> str:
    if event_name == "PostToolUse":
        if payload.get("error") or (payload.get("exit_code") or 0) != 0:
            return "warn"
    if event_name == "SubagentStop":
        return "warn"
    return "info"


def main() -> int:
    try:
        from ink_writer.debug.collector import Collector
        from ink_writer.debug.config import load_config
        from ink_writer.debug.schema import Incident
    except Exception as e:
        print(f"[hook_handler] import failed: {e}", file=sys.stderr)
        return 0

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}

    event_name = payload.get("hook_event_name") or payload.get("event") or "PostToolUse"
    cfg = load_config(global_yaml_path=Path("config/debug.yaml"), project_root=_project_root())
    if not cfg.master_enabled or not cfg.layers.layer_a_hooks:
        return 0

    inc = Incident(
        ts=_now_iso(),
        run_id=_run_id(),
        source="layer_a_hook",
        skill=os.environ.get("INK_DEBUG_SKILL", "claude-code"),
        kind=_hook_kind(event_name),
        severity=_severity(event_name, payload),
        message=f"{event_name} {payload.get('tool_name','')}".strip(),
        evidence={k: payload.get(k) for k in ("tool_name", "duration_ms", "exit_code", "error")
                  if payload.get(k) is not None} or None,
    )

    try:
        Collector(cfg).record(inc)
    except Exception as e:
        print(f"[hook_handler] record failed: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
