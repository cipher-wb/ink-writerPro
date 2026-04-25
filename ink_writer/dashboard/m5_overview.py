"""M5 Case 治理 overview JSON — 服务 ``/api/m5-overview`` 与周报 CLI。

Bundles the four headline metrics + dry-run state + pending meta-rule
proposals + recurrent cases into a single dict consumed by both the React
panel (``ink-writer/dashboard/frontend``) and ``ink dashboard report --week N``
(see :mod:`ink_writer.dashboard.weekly_report`, US-006).

Lazy / defensive: missing case_store, missing meta_rules dir, fresh project
all fall back to empty lists / 0.0 metrics so the dashboard renders even on
day one.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ink_writer.case_library.store import CaseStore
from ink_writer.dashboard.aggregator import (
    compute_checker_accuracy,
    compute_editor_score_trend,
    compute_m3_dry_run_pass_rate,
    compute_m4_dry_run_pass_rate,
    compute_recurrence_rate,
    compute_repair_speed,
    recommend_dry_run_switch,
)

_DEFAULT_META_RULES_DIRNAME = Path("case_library/meta_rules")
_DEFAULT_LIBRARY_DIRNAME = Path("case_library")
_DEFAULT_EDITOR_REVIEWS_DIRNAME = Path("editor_reviews")


def _load_pending_meta_rules(meta_rules_dir: Path) -> list[dict[str, Any]]:
    if not meta_rules_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(meta_rules_dir.glob("MR-*.yaml")):
        try:
            with open(path, encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(doc, dict):
            continue
        if doc.get("status") != "pending":
            continue
        out.append(
            {
                "proposal_id": doc.get("proposal_id") or path.stem,
                "similarity": doc.get("similarity"),
                "merged_rule": doc.get("merged_rule"),
                "covered_cases": doc.get("covered_cases") or [],
                "reason": doc.get("reason"),
            }
        )
    return out


def _collect_recurrent_cases(case_store: CaseStore) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for case in case_store.iter_all():
        if not case.recurrence_history:
            continue
        out.append(
            {
                "case_id": case.case_id,
                "title": case.title,
                "status": case.status.value,
                "severity": case.severity.value,
                "recurrence_count": len(case.recurrence_history),
                "last_regressed_at": case.recurrence_history[-1].get("regressed_at"),
            }
        )
    return out


def get_m5_overview(
    *,
    base_dir: Path,
    case_store: CaseStore | None = None,
) -> dict[str, Any]:
    """Return the bundled M5 治理 overview payload.

    Args:
        base_dir: ``data/`` root (counters live here, books are subdirs,
            ``case_library/`` and ``editor_reviews/`` are subdirs).
        case_store: optional pre-built store; falls back to
            ``CaseStore(base_dir / 'case_library')``.

    Returns a dict with keys ``metrics``, ``dry_run``, ``pending_meta_rules``,
    ``recurrent_cases``.
    """
    base = Path(base_dir)
    if case_store is None:
        case_store = CaseStore(base / _DEFAULT_LIBRARY_DIRNAME)

    cases_for_recurrence = list(case_store.iter_all())

    recurrence_rate = compute_recurrence_rate(case_store_iter=iter(cases_for_recurrence))
    repair_speed = compute_repair_speed(case_store_iter=iter(cases_for_recurrence))
    editor_trend = compute_editor_score_trend(
        base_dir=base / _DEFAULT_EDITOR_REVIEWS_DIRNAME
    )
    checker_accuracy = compute_checker_accuracy()

    m3_counter, m3_pass = compute_m3_dry_run_pass_rate(base_dir=base)
    m4_counter, m4_pass = compute_m4_dry_run_pass_rate(base_dir=base)

    m3_recommendation = recommend_dry_run_switch(
        counter=m3_counter, pass_rate=m3_pass
    )
    m4_recommendation = recommend_dry_run_switch(
        counter=m4_counter, pass_rate=m4_pass
    )

    pending_meta_rules = _load_pending_meta_rules(
        base / _DEFAULT_META_RULES_DIRNAME
    )
    recurrent_cases = _collect_recurrent_cases(case_store)

    return {
        "metrics": {
            "recurrence_rate": recurrence_rate,
            "repair_speed_days": repair_speed,
            "editor_score_trend": editor_trend,
            "checker_accuracy": checker_accuracy,
        },
        "dry_run": {
            "m3": {
                "counter": m3_counter,
                "pass_rate": m3_pass,
                "recommendation": m3_recommendation,
            },
            "m4": {
                "counter": m4_counter,
                "pass_rate": m4_pass,
                "recommendation": m4_recommendation,
            },
        },
        "pending_meta_rules": pending_meta_rules,
        "recurrent_cases": recurrent_cases,
    }
