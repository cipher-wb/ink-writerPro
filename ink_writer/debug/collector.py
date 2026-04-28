"""Collector — single write entry point. Failure-soft by design."""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from ink_writer.debug.config import DebugConfig
from ink_writer.debug.schema import Incident, validate_kind


class Collector:
    """Writes incidents to events.jsonl. Never raises in production paths."""

    def __init__(self, config: DebugConfig) -> None:
        self.config = config

    def _events_path(self) -> Path:
        return self.config.base_path() / "events.jsonl"

    def _error_log_path(self) -> Path:
        return self.config.base_path() / "collector.error.log"

    def _ensure_dir(self) -> None:
        self.config.base_path().mkdir(parents=True, exist_ok=True)

    def _write_jsonl(self, line: str) -> None:
        self._ensure_dir()
        path = self._events_path()
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
        # Best-effort rotation check (cheap stat call).
        try:
            from ink_writer.debug.rotate import rotate_if_needed
            rotate_if_needed(
                path,
                max_bytes=self.config.storage.events_max_mb * 1024 * 1024,
                archive_keep=self.config.storage.archive_keep,
            )
        except Exception as e:
            self._log_error(e)

    def _log_error(self, exc: BaseException) -> None:
        try:
            self._ensure_dir()
            with self._error_log_path().open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now(timezone.utc).isoformat()} {type(exc).__name__}: {exc}\n")
                f.write(traceback.format_exc() + "\n")
        except Exception:
            # Last resort: write to stderr, swallow.
            print(f"[debug.collector] internal error: {exc}", file=sys.stderr)

    def _stderr_print(self, incident: Incident) -> None:
        msg = f"[debug:{incident.severity}] {incident.kind} {incident.message}"
        # ANSI red only if tty AND NO_COLOR is unset (CLAUDE.md / spec §6).
        if sys.stderr.isatty() and not os.environ.get("NO_COLOR"):
            msg = f"\033[31m{msg}\033[0m"
        print(msg, file=sys.stderr)

    def record(self, incident: Incident) -> None:
        # 1. Master switch (covers INK_DEBUG_OFF env via config.load).
        if not self.config.master_enabled:
            return

        # 2. Layer gating.
        # Note: source="meta" is intentionally ungated — meta events report on the
        # debug system itself and must surface even if all layer switches are off.
        # source="layer_d_adversarial" is gated below (default-off until v1.0).
        if incident.source == "layer_c_invariant" and not self.config.layers.layer_c_invariants:
            return
        if incident.source == "layer_b_checker" and not self.config.layers.layer_b_checker_router:
            return
        if incident.source == "layer_a_hook" and not self.config.layers.layer_a_hooks:
            return
        if incident.source == "layer_d_adversarial" and not self.config.layers.layer_d_adversarial:
            return

        # Kind validation.
        if not validate_kind(incident.kind):
            if self.config.strict_mode:
                raise ValueError(f"unknown kind: {incident.kind}")
            # Re-emit as meta.unknown_kind synthetic event; original incident is dropped.
            # Direct _write_jsonl bypasses validate_kind, preventing infinite recursion
            # even if meta.unknown_kind is later removed from KIND_WHITELIST.
            try:
                meta = Incident(
                    ts=incident.ts,
                    run_id=incident.run_id,
                    source="meta",
                    skill=incident.skill,
                    kind="meta.unknown_kind",
                    severity="info",
                    message=f"unknown kind: {incident.kind}",
                    evidence={"original_kind": incident.kind},
                )
                self._write_jsonl(meta.to_jsonl_line())
            except Exception as e:
                self._log_error(e)
            return

        # 4. Severity threshold for JSONL.
        if not self.config.passes_threshold(incident.severity, "jsonl_threshold"):
            return

        # 5. Write JSONL (best-effort).
        try:
            self._write_jsonl(incident.to_jsonl_line())
        except Exception as e:
            self._log_error(e)
            return

        # 6. stderr passthrough at error severity.
        if self.config.passes_threshold(incident.severity, "stderr_threshold"):
            try:
                self._stderr_print(incident)
            except Exception as e:
                self._log_error(e)
