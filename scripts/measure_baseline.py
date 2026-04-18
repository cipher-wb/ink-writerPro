#!/usr/bin/env python3
"""
measure_baseline.py - 质量基线测量脚本

从项目的 index.db 聚合所有质量/性能指标，输出 JSON 到 benchmark/baseline_v12.json。
可在每个 Phase 结束后重新运行以对比变化。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, stdev, variance
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
INK_SCRIPTS_DIR = SCRIPT_DIR.parent / "ink-writer" / "scripts"
sys.path.insert(0, str(INK_SCRIPTS_DIR))

from ink_writer.core.infra.config import DataModulesConfig
from ink_writer.core.index.index_manager import IndexManager
from project_locator import resolve_project_root


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _compute_hook_density(manager: IndexManager, max_chapter: int) -> dict[str, Any]:
    """Compute hook density from chapter_reading_power table."""
    with manager._get_conn() as conn:
        rows = conn.execute(
            "SELECT chapter, hook_type, hook_strength, coolpoint_patterns, "
            "micropayoffs, hard_violations, is_transition, debt_balance "
            "FROM chapter_reading_power ORDER BY chapter"
        ).fetchall()

    if not rows:
        return {"hook_density": 0.0, "strong_hook_ratio": 0.0, "avg_micropayoffs": 0.0,
                "avg_debt_balance": 0.0, "sample_count": 0}

    chapters = [dict(r) for r in rows]
    hooks_present = sum(1 for c in chapters if c.get("hook_type"))
    strong_hooks = sum(1 for c in chapters if c.get("hook_strength") == "strong")
    micropayoff_counts = []
    debt_balances = []
    for c in chapters:
        mp = c.get("micropayoffs")
        if isinstance(mp, str):
            try:
                mp = json.loads(mp)
            except (json.JSONDecodeError, TypeError):
                mp = []
        micropayoff_counts.append(len(mp) if isinstance(mp, list) else 0)
        debt_balances.append(_safe_float(c.get("debt_balance")))

    total = len(chapters)
    return {
        "hook_density": hooks_present / total if total else 0.0,
        "strong_hook_ratio": strong_hooks / total if total else 0.0,
        "avg_micropayoffs": mean(micropayoff_counts) if micropayoff_counts else 0.0,
        "avg_debt_balance": mean(debt_balances) if debt_balances else 0.0,
        "sample_count": total,
    }


def _compute_high_point_density(manager: IndexManager) -> dict[str, Any]:
    """Compute high-point density from review_metrics dimension_scores."""
    records = manager.get_recent_review_metrics(limit=9999)
    if not records:
        return {"high_point_density": 0.0, "sample_count": 0}

    scores = []
    for r in records:
        dims = r.get("dimension_scores") or {}
        hp = dims.get("high-point-checker") or dims.get("high_point_checker")
        if hp is not None:
            scores.append(_safe_float(hp))

    return {
        "high_point_density": mean(scores) if scores else 0.0,
        "high_point_stdev": stdev(scores) if len(scores) > 1 else 0.0,
        "sample_count": len(scores),
    }


def _compute_emotion_variance(manager: IndexManager) -> dict[str, Any]:
    """Compute emotion variance from reader-simulator scores in review_metrics."""
    records = manager.get_recent_review_metrics(limit=9999)
    if not records:
        return {"emotion_variance": 0.0, "avg_immersion": 0.0, "sample_count": 0}

    immersion_scores = []
    for r in records:
        payload = r.get("review_payload_json") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = {}
        reader_sim = payload.get("reader-simulator") or {}
        metrics = reader_sim.get("metrics") or {}
        imm = metrics.get("immersion_score")
        if imm is not None:
            immersion_scores.append(_safe_float(imm))

    all_dim_scores = []
    for r in records:
        d = r.get("dimension_scores") or {}
        for v in d.values():
            all_dim_scores.append(_safe_float(v))

    return {
        "emotion_variance": variance(immersion_scores) if len(immersion_scores) > 1 else 0.0,
        "avg_immersion": mean(immersion_scores) if immersion_scores else 0.0,
        "dimension_score_variance": variance(all_dim_scores) if len(all_dim_scores) > 1 else 0.0,
        "sample_count": len(immersion_scores),
    }


def _compute_ai_taste_score(manager: IndexManager) -> dict[str, Any]:
    """Compute AI taste score from anti-detection-checker in review_metrics."""
    records = manager.get_recent_review_metrics(limit=9999)
    if not records:
        return {"ai_taste_score": 0.0, "sample_count": 0}

    scores = []
    for r in records:
        dims = r.get("dimension_scores") or {}
        ad = dims.get("anti-detection-checker") or dims.get("anti_detection_checker")
        if ad is not None:
            scores.append(_safe_float(ad))

    return {
        "ai_taste_score": mean(scores) if scores else 0.0,
        "ai_taste_stdev": stdev(scores) if len(scores) > 1 else 0.0,
        "sample_count": len(scores),
    }


def _compute_ooc_score(manager: IndexManager) -> dict[str, Any]:
    """Compute OOC score from ooc-checker in review_metrics."""
    records = manager.get_recent_review_metrics(limit=9999)
    if not records:
        return {"ooc_score": 0.0, "sample_count": 0}

    scores = []
    for r in records:
        dims = r.get("dimension_scores") or {}
        ooc = dims.get("ooc-checker") or dims.get("ooc_checker")
        if ooc is not None:
            scores.append(_safe_float(ooc))

    return {
        "ooc_score": mean(scores) if scores else 0.0,
        "ooc_stdev": stdev(scores) if len(scores) > 1 else 0.0,
        "sample_count": len(scores),
    }


def _compute_consistency_score(manager: IndexManager) -> dict[str, Any]:
    """Compute consistency score from consistency-checker in review_metrics."""
    records = manager.get_recent_review_metrics(limit=9999)
    if not records:
        return {"consistency_score": 0.0, "sample_count": 0}

    scores = []
    for r in records:
        dims = r.get("dimension_scores") or {}
        cs = dims.get("consistency-checker") or dims.get("consistency_checker")
        if cs is not None:
            scores.append(_safe_float(cs))

    return {
        "consistency_score": mean(scores) if scores else 0.0,
        "consistency_stdev": stdev(scores) if len(scores) > 1 else 0.0,
        "sample_count": len(scores),
    }


def _compute_perf_metrics(manager: IndexManager) -> dict[str, Any]:
    """Compute performance metrics from review_metrics timestamps."""
    with manager._get_conn() as conn:
        try:
            rows = conn.execute(
                "SELECT created_at, updated_at FROM review_metrics "
                "WHERE created_at IS NOT NULL AND updated_at IS NOT NULL "
                "ORDER BY end_chapter DESC LIMIT 50"
            ).fetchall()
        except Exception:
            rows = []

    if not rows:
        return {"avg_chapter_seconds": 0.0, "sample_count": 0}

    durations = []
    for r in rows:
        row = dict(r)
        created = row.get("created_at")
        updated = row.get("updated_at")
        if created and updated and created != updated:
            try:
                from datetime import datetime as dt
                t0 = dt.fromisoformat(str(created).replace("Z", "+00:00"))
                t1 = dt.fromisoformat(str(updated).replace("Z", "+00:00"))
                diff = abs((t1 - t0).total_seconds())
                if 0 < diff < 7200:
                    durations.append(diff)
            except (ValueError, TypeError):
                pass

    return {
        "avg_chapter_seconds": mean(durations) if durations else 0.0,
        "sample_count": len(durations),
    }


def _compute_token_metrics(manager: IndexManager) -> dict[str, Any]:
    """Estimate token usage from chapter word counts."""
    with manager._get_conn() as conn:
        try:
            rows = conn.execute(
                "SELECT word_count FROM chapters "
                "WHERE word_count IS NOT NULL AND word_count > 0 "
                "ORDER BY chapter DESC LIMIT 50"
            ).fetchall()
        except Exception:
            rows = []

    if not rows:
        return {"avg_chapter_tokens": 0.0, "sample_count": 0}

    word_counts = [_safe_int(dict(r).get("word_count")) for r in rows]
    word_counts = [w for w in word_counts if w > 0]
    token_estimates = [int(w * 1.5) for w in word_counts]

    return {
        "avg_chapter_tokens": mean(token_estimates) if token_estimates else 0.0,
        "sample_count": len(token_estimates),
    }


def _compute_review_aggregate(manager: IndexManager) -> dict[str, Any]:
    """Compute aggregate review stats."""
    trend = manager.get_review_trend_stats(last_n=9999)
    return {
        "review_count": trend.get("count", 0),
        "overall_avg": _safe_float(trend.get("overall_avg")),
        "dimension_avg": trend.get("dimension_avg", {}),
        "severity_totals": trend.get("severity_totals", {}),
    }


def measure_baseline(project_root: Path | None = None) -> dict[str, Any]:
    """Run all baseline measurements and return a structured dict."""
    if project_root is None:
        project_root = resolve_project_root()

    cfg = DataModulesConfig.from_project_root(project_root)
    manager = IndexManager(cfg)
    stats = manager.get_stats()
    max_chapter = stats.get("max_chapter", 0)

    hook_data = _compute_hook_density(manager, max_chapter)
    hp_data = _compute_high_point_density(manager)
    emotion_data = _compute_emotion_variance(manager)
    ai_data = _compute_ai_taste_score(manager)
    ooc_data = _compute_ooc_score(manager)
    consistency_data = _compute_consistency_score(manager)
    perf_data = _compute_perf_metrics(manager)
    token_data = _compute_token_metrics(manager)
    review_agg = _compute_review_aggregate(manager)

    baseline = {
        "version": "v12",
        "timestamp": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "project_root": str(project_root),
        "chapter_count": max_chapter,
        "entity_count": stats.get("entities", 0),
        "metrics": {
            "hook_density": hook_data["hook_density"],
            "strong_hook_ratio": hook_data["strong_hook_ratio"],
            "avg_micropayoffs": hook_data["avg_micropayoffs"],
            "avg_debt_balance": hook_data["avg_debt_balance"],
            "high_point_density": hp_data["high_point_density"],
            "high_point_stdev": hp_data.get("high_point_stdev", 0.0),
            "emotion_variance": emotion_data["emotion_variance"],
            "avg_immersion": emotion_data["avg_immersion"],
            "ai_taste_score": ai_data["ai_taste_score"],
            "ai_taste_stdev": ai_data.get("ai_taste_stdev", 0.0),
            "ooc_score": ooc_data["ooc_score"],
            "ooc_stdev": ooc_data.get("ooc_stdev", 0.0),
            "consistency_score": consistency_data["consistency_score"],
            "consistency_stdev": consistency_data.get("consistency_stdev", 0.0),
            "avg_chapter_seconds": perf_data["avg_chapter_seconds"],
            "avg_chapter_tokens": token_data["avg_chapter_tokens"],
        },
        "detail": {
            "hook": hook_data,
            "high_point": hp_data,
            "emotion": emotion_data,
            "ai_taste": ai_data,
            "ooc": ooc_data,
            "consistency": consistency_data,
            "performance": perf_data,
            "tokens": token_data,
            "review_aggregate": review_agg,
        },
        "sample_counts": {
            "hook": hook_data["sample_count"],
            "high_point": hp_data["sample_count"],
            "emotion": emotion_data["sample_count"],
            "ai_taste": ai_data["sample_count"],
            "ooc": ooc_data["sample_count"],
            "consistency": consistency_data["sample_count"],
            "performance": perf_data["sample_count"],
            "tokens": token_data["sample_count"],
        },
    }
    return baseline


def main() -> None:
    parser = argparse.ArgumentParser(description="测量 ink-writer 质量基线指标")
    parser.add_argument("--project-root", type=str, help="项目根目录")
    parser.add_argument("--output", type=str, help="输出 JSON 路径（默认 benchmark/baseline_v12.json）")
    args = parser.parse_args()

    if args.project_root:
        project_root = resolve_project_root(args.project_root)
    else:
        project_root = resolve_project_root()

    baseline = measure_baseline(project_root)

    repo_root = SCRIPT_DIR.parent
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else repo_root / "benchmark" / "baseline_v12.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Baseline written to {output_path}")
    print(f"  chapters: {baseline['chapter_count']}")
    print(f"  hook_density: {baseline['metrics']['hook_density']:.3f}")
    print(f"  high_point_density: {baseline['metrics']['high_point_density']:.1f}")
    print(f"  ai_taste_score: {baseline['metrics']['ai_taste_score']:.1f}")
    print(f"  ooc_score: {baseline['metrics']['ooc_score']:.1f}")
    print(f"  consistency_score: {baseline['metrics']['consistency_score']:.1f}")


if __name__ == "__main__":
    main()
