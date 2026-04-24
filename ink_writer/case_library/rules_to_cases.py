"""editor-wisdom rules.json → case_library cases 转换器.

按 rule.severity 分流（spec §5.3）：
  hard → active P1
  soft → pending P2
  info → pending P3 + info_only tag

observable 用占位文本（spec §5.4）：
  ["待 M3 dry-run 后基于实际触发样本细化（rule_id: EW-XXXX）"]

幂等性：基于 raw_text = rule + " | " + why 的 sha256 dedup（M1 ingest_case 已实现）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ink_writer.case_library.ingest import ingest_case
from ink_writer.case_library.store import CaseStore

_SEVERITY_MAP: dict[str, tuple[str, str]] = {
    "hard": ("P1", "active"),
    "soft": ("P2", "pending"),
    "info": ("P3", "pending"),
}


@dataclass
class ConvertReport:
    created: int = 0
    skipped: int = 0  # already existed (sha256 dedup)
    failed: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)
    by_category: dict[str, int] = field(default_factory=dict)
    failures: list[tuple[str, str]] = field(default_factory=list)


def map_rule_to_case_kwargs(
    rule: dict[str, Any], *, ingested_at: str
) -> dict[str, Any]:
    """Map one rule dict to ingest_case() kwargs."""
    severity_str = rule.get("severity", "soft")
    case_severity, initial_status = _SEVERITY_MAP.get(severity_str, ("P2", "pending"))

    tags = ["from_editor_wisdom", rule.get("category", "misc")]
    if severity_str == "info":
        tags.append("info_only")

    rule_text = rule.get("rule", "")
    why_text = rule.get("why", "")
    description = f"{rule_text} — 理由：{why_text}" if why_text else rule_text

    raw_text = f"{rule_text} | {why_text}"

    applies_to = rule.get("applies_to", [])
    scope_chapter = list(applies_to) if applies_to else ["all"]

    source_files = rule.get("source_files", [])
    ingested_from = source_files[0] if source_files else None

    rule_id = rule.get("id", "unknown")
    observable = [
        f"待 M3 dry-run 后基于实际触发样本细化（rule_id: {rule_id}）"
    ]

    return {
        "title": rule_text[:80] if rule_text else f"rule {rule_id}",
        "raw_text": raw_text,
        "domain": "writing_quality",
        "layer": ["downstream"],
        "severity": case_severity,
        "tags": tags,
        "source_type": "editor_review",
        "ingested_at": ingested_at,
        "reviewer": "星河编辑",
        "ingested_from": ingested_from,
        "scope_chapter": scope_chapter,
        "scope_genre": ["all"],
        "failure_description": description,
        "observable": observable,
        "initial_status": initial_status,
    }


def convert_rules_to_cases(
    *,
    rules_path: Path,
    library_root: Path,
    dry_run: bool = False,
    ingested_at: str | None = None,
) -> ConvertReport:
    """Convert every rule in ``rules_path`` into a case under ``library_root``.

    Idempotent: relies on ``ingest_case`` SHA-256 dedup of ``raw_text``.

    Args:
        rules_path: path to editor-wisdom rules.json (list of rule dicts).
        library_root: case library root; ``cases/`` dir auto-created.
        dry_run: when True, count "would-create" but do not mutate store.
        ingested_at: ISO date string; defaults to today (UTC).

    Returns:
        ConvertReport with created / skipped / failed / by_severity /
        by_category / failures.
    """
    if ingested_at is None:
        ingested_at = datetime.now(UTC).date().isoformat()

    with open(rules_path, encoding="utf-8") as fp:
        rules = json.load(fp)

    report = ConvertReport()
    store = CaseStore(library_root)

    for rule in rules:
        sev = rule.get("severity", "soft")
        cat = rule.get("category", "misc")
        report.by_severity[sev] = report.by_severity.get(sev, 0) + 1
        report.by_category[cat] = report.by_category.get(cat, 0) + 1

        try:
            kw = map_rule_to_case_kwargs(rule, ingested_at=ingested_at)
            if dry_run:
                report.created += 1
                continue
            result = ingest_case(store, **kw)
            if result.created:
                report.created += 1
            else:
                report.skipped += 1
        except Exception as err:  # noqa: BLE001 — convert-time guard
            report.failed += 1
            report.failures.append((rule.get("id", "?"), str(err)))

    return report
