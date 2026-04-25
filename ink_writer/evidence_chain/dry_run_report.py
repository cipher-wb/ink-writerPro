"""generate_dry_run_report — 5 章 dry-run 后聚合 metrics 出 markdown 报告 (spec §6.3).

扫 ``<base_dir>/data/<book>/chapters/*.evidence.json``，统计 outcome 分布、
重写率、case 命中 top10、平均 rule_compliance，写 markdown 到
``<base_dir>/data/dry_run_report_<UTC_TS>.md``，供人工 review 后决定是否切真阻断。
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _iter_evidence(book: str, base_dir: Path) -> list[dict[str, Any]]:
    chapters_dir = base_dir / "data" / book / "chapters"
    if not chapters_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(chapters_dir.glob("*.evidence.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                out.append(json.load(fh))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def aggregate_dry_run_metrics(*, book: str, base_dir: Path) -> dict[str, Any]:
    """聚合 ``data/<book>/chapters/*.evidence.json`` 的 outcome / rewrite / case 命中分布。"""
    chapters = _iter_evidence(book, base_dir)
    outcomes = Counter(c.get("outcome", "?") for c in chapters)

    case_hit_counter: Counter[str] = Counter()
    rule_compliance_values: list[float] = []
    rewrite_count = 0
    for chapter in chapters:
        for upd in chapter.get("case_evidence_updates", []) or []:
            case_id = upd.get("case_id") or ""
            if case_id:
                case_hit_counter[case_id] += 1

        rounds = (
            chapter.get("phase_evidence", {})
            .get("writer_agent", {})
            .get("rounds", [])
            or []
        )
        if rounds:
            rc = rounds[0].get("compliance_report", {}).get("rule_compliance")
            if isinstance(rc, (int, float)):
                rule_compliance_values.append(float(rc))

        polish = chapter.get("phase_evidence", {}).get("polish_agent", {}) or {}
        rewrite_count += int(polish.get("rewrite_rounds", 0) or 0)

    total = len(chapters)
    return {
        "total_chapters": total,
        "delivered": outcomes.get("delivered", 0),
        "needs_human_review": outcomes.get("needs_human_review", 0),
        "rewrite_rounds_total": rewrite_count,
        "rewrite_rate": (rewrite_count / total) if total else 0.0,
        "human_review_rate": (
            outcomes.get("needs_human_review", 0) / total if total else 0.0
        ),
        "case_hit_top10": case_hit_counter.most_common(10),
        "rule_compliance_avg": (
            sum(rule_compliance_values) / len(rule_compliance_values)
            if rule_compliance_values
            else 0.0
        ),
    }


def generate_dry_run_report(*, book: str, base_dir: Path | str | None = None) -> Path:
    """聚合 metrics 并写 markdown 报告，返写盘路径。"""
    base = Path(base_dir) if base_dir is not None else Path(".")
    metrics = aggregate_dry_run_metrics(book=book, base_dir=base)
    now = datetime.now(UTC)
    ts = now.strftime("%Y%m%dT%H%M%S")
    report_path = base / "data" / f"dry_run_report_{ts}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "# M3 Dry-Run Report",
        "",
        f"**Book**: {book}",
        f"**Generated at**: {now.isoformat(timespec='seconds')}",
        f"**Total chapters**: {metrics['total_chapters']}",
        "",
        "## Outcomes",
        f"- delivered: {metrics['delivered']}",
        f"- needs_human_review: {metrics['needs_human_review']}",
        f"- rewrite rounds total: {metrics['rewrite_rounds_total']}",
        f"- rewrite rate: {metrics['rewrite_rate']:.1%}",
        f"- human review rate: {metrics['human_review_rate']:.1%}",
        f"- avg rule_compliance: {metrics['rule_compliance_avg']:.3f}",
        "",
        "## Top 10 Case Hits",
    ]
    if metrics["case_hit_top10"]:
        for cid, n in metrics["case_hit_top10"]:
            lines.append(f"- {cid}: {n}")
    else:
        lines.append("(no case hits)")

    if metrics["total_chapters"] == 0:
        lines.append("")
        lines.append("*0 chapters yet; run more chapters to populate this report.*")

    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return report_path
