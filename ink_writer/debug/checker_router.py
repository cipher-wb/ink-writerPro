"""Layer B: route existing checker reports → incident schema."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ink_writer.debug.schema import Incident

SUPPORTED_CHECKERS = frozenset({
    "consistency",
    "continuity",
    "live-review",
    "ooc",
    "reader-simulator",
})

SEVERITY_MAP = {"red": "error", "yellow": "warn", "green": "info"}


def _normalize_kind(checker_name: str, raw_kind: str) -> str:
    """Normalize to checker.<name>.<problem>; both segments snake_case."""
    name = checker_name.replace("-", "_")
    problem = raw_kind.replace("-", "_").replace(" ", "_").lower()
    return f"checker.{name}.{problem}"


def route(
    checker_name: str,
    report: dict[str, Any],
    *,
    run_id: str,
    chapter: int | None,
    skill: str,
) -> list[Incident]:
    """Convert a single checker report to a list of Incidents.

    Returns empty list if checker is unsupported or no warn+ violations.
    """
    if checker_name not in SUPPORTED_CHECKERS:
        return []

    violations = report.get("violations") or []
    out: list[Incident] = []
    for v in violations:
        sev = SEVERITY_MAP.get(v.get("severity", "green"), "info")
        if sev == "info":
            continue
        out.append(Incident(
            ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            run_id=run_id,
            source="layer_b_checker",
            skill=skill,
            step="review",
            kind=_normalize_kind(checker_name, v.get("kind", "unknown")),
            severity=sev,
            message=v.get("message", ""),
            chapter=chapter,
            evidence={k: v[k] for k in v if k not in {"severity", "kind", "message"}} or None,
        ))
    return out
