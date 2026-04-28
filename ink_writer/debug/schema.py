"""Incident schema + kind whitelist + serialization."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

VALID_SOURCES = frozenset({
    "layer_a_hook",
    "layer_b_checker",
    "layer_c_invariant",
    "layer_d_adversarial",
    "meta",
})

VALID_SEVERITIES = frozenset({"info", "warn", "error"})

# Static reserved kinds (Section 3.1 of spec).
KIND_WHITELIST: frozenset[str] = frozenset({
    "writer.short_word_count",
    "polish.diff_too_small",
    "review.missing_dimensions",
    "context.missing_required_skill_file",
    "auto.skill_step_skipped",
    "hook.pre_tool_use",
    "hook.post_tool_use",
    "hook.subagent_stop",
    "hook.stop",
    "hook.session_end",
    "meta.invariant_crashed",
    "meta.unknown_kind",
    "meta.collector_error",
})


def validate_kind(kind: str) -> bool:
    """Return True if kind is a known reserved kind or matches checker.<name>.<problem>."""
    if kind in KIND_WHITELIST:
        return True
    parts = kind.split(".")
    if len(parts) >= 3 and parts[0] == "checker":
        return all(p and p.replace("_", "").isalnum() for p in parts[1:])
    return False


@dataclass
class Incident:
    ts: str                                 # ISO8601 UTC
    run_id: str
    source: str                             # one of VALID_SOURCES
    skill: str
    kind: str
    severity: str                           # one of VALID_SEVERITIES
    message: str
    session_id: str | None = None
    project: str | None = None
    chapter: int | None = None
    step: str | None = None
    evidence: dict[str, Any] | None = None
    trace: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(
                f"severity must be one of {sorted(VALID_SEVERITIES)}, got {self.severity!r}"
            )
        if self.source not in VALID_SOURCES:
            raise ValueError(
                f"source must be one of {sorted(VALID_SOURCES)}, got {self.source!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}

    def to_jsonl_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n"
