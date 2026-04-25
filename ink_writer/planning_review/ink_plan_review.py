"""ink-plan Step 99 编排（M4 P0 spec §5.2）。

串行跑 3 个策划期 checker：
1. ``golden-finger-timing`` — 金手指必须在前 3 章 summary 出现（regex + LLM 双层）
2. ``protagonist-agency-skeleton`` — 卷骨架级主角能动性
3. ``chapter-hook-density`` — 卷骨架级钩子密度

outline JSON schema（最小集）::

    {
      "volume_skeleton": [{"chapter_idx": 1, "summary": "..."}, ...],
      "golden_finger_keywords": ["万道归一", "融合"]
    }

写入 stage='ink-plan' 段；同书已有 ink-init evidence 时按 stage 名合并。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ink_writer.checker_pipeline.thresholds_loader import load_thresholds
from ink_writer.checkers.chapter_hook_density import check_chapter_hook_density
from ink_writer.checkers.golden_finger_timing import check_golden_finger_timing
from ink_writer.checkers.protagonist_agency_skeleton import (
    check_protagonist_agency_skeleton,
)
from ink_writer.evidence_chain import EvidenceChain, write_planning_evidence_chain
from ink_writer.planning_review.dry_run import (
    DEFAULT_COUNTER_PATH,
    increment_counter,
    is_dry_run_active,
)

SKIP_REASON = "--skip-planning-review"


def _resolve_dry_run_path(path: Path | str | None, cfg: dict[str, Any]) -> Path:
    if path is not None:
        return Path(path)
    cfg_path = cfg.get("counter_path")
    return Path(cfg_path) if cfg_path else DEFAULT_COUNTER_PATH


def _inject_cases(report_dict: dict[str, Any], section: dict[str, Any]) -> None:
    if not report_dict.get("blocked"):
        return
    case_ids = list(section.get("case_ids", []) or [])
    if case_ids:
        report_dict["cases_hit"] = case_ids


def run_ink_plan_review(
    *,
    book: str,
    outline: dict[str, Any],
    llm_client: Any,
    base_dir: Path | str | None = None,
    skip: bool = False,
    dry_run_counter_path: Path | str | None = None,
    thresholds_path: Path | str | None = None,
) -> dict[str, Any]:
    """ink-plan Step 99 入口。"""
    thresholds = load_thresholds(thresholds_path)
    dry_run_cfg = thresholds.get("planning_dry_run", {}) or {}
    counter_path = _resolve_dry_run_path(dry_run_counter_path, dry_run_cfg)
    dry_run = is_dry_run_active(
        counter_path,
        observation_runs=int(dry_run_cfg.get("observation_runs", 5)),
        enabled=bool(dry_run_cfg.get("enabled", True)),
        switch_to_block_after=bool(dry_run_cfg.get("switch_to_block_after", True)),
    )

    evidence = EvidenceChain(
        book=book,
        chapter="",
        phase="planning",
        stage="ink-plan",
        dry_run=dry_run,
    )

    if skip:
        evidence.outcome = "skipped"
        evidence.human_overrides.append(
            {"action": "skip", "reason": SKIP_REASON, "stage": "ink-plan"}
        )
        path = write_planning_evidence_chain(
            book=book, evidence=evidence, base_dir=base_dir
        )
        return {
            "stage": "ink-plan",
            "skipped": True,
            "skip_reason": SKIP_REASON,
            "blocked_any": False,
            "effective_blocked": False,
            "dry_run": dry_run,
            "evidence_path": str(path),
            "checkers": [],
        }

    skeleton = list(outline.get("volume_skeleton", []) or [])
    keywords = list(outline.get("golden_finger_keywords", []) or [])

    outcomes: list[dict[str, Any]] = []
    blocked_any = False

    # 1. golden-finger-timing
    section = thresholds.get("golden_finger_timing", {}) or {}
    timing_report = check_golden_finger_timing(
        outline_volume_skeleton=skeleton,
        golden_finger_keywords=keywords,
        llm_client=llm_client,
        block_threshold=float(section.get("block_threshold", 1.0)),
    )
    t_dict = timing_report.to_dict()
    _inject_cases(t_dict, section)
    blocked_any = blocked_any or bool(t_dict.get("blocked"))
    outcomes.append({
        "id": "golden-finger-timing",
        "score": t_dict["score"],
        "blocked": t_dict["blocked"],
        "cases_hit": t_dict.get("cases_hit", []),
        "notes": t_dict.get("notes"),
        "details": t_dict,
    })

    # 2. protagonist-agency-skeleton
    section = thresholds.get("protagonist_agency_skeleton", {}) or {}
    agency_report = check_protagonist_agency_skeleton(
        outline_volume_skeleton=skeleton,
        llm_client=llm_client,
        block_threshold=float(section.get("block_threshold", 0.55)),
    )
    a_dict = agency_report.to_dict()
    _inject_cases(a_dict, section)
    blocked_any = blocked_any or bool(a_dict.get("blocked"))
    outcomes.append({
        "id": "protagonist-agency-skeleton",
        "score": a_dict["score"],
        "blocked": a_dict["blocked"],
        "cases_hit": a_dict.get("cases_hit", []),
        "notes": a_dict.get("notes"),
        "details": a_dict,
    })

    # 3. chapter-hook-density
    section = thresholds.get("chapter_hook_density", {}) or {}
    density_report = check_chapter_hook_density(
        outline_volume_skeleton=skeleton,
        llm_client=llm_client,
        block_threshold=float(section.get("block_threshold", 0.70)),
    )
    d_dict = density_report.to_dict()
    _inject_cases(d_dict, section)
    blocked_any = blocked_any or bool(d_dict.get("blocked"))
    outcomes.append({
        "id": "chapter-hook-density",
        "score": d_dict["score"],
        "blocked": d_dict["blocked"],
        "cases_hit": d_dict.get("cases_hit", []),
        "notes": d_dict.get("notes"),
        "details": d_dict,
    })

    effective_blocked = blocked_any and not dry_run

    evidence.record_checkers(outcomes)
    evidence.outcome = "blocked" if effective_blocked else "passed"
    path = write_planning_evidence_chain(
        book=book, evidence=evidence, base_dir=base_dir
    )

    if dry_run:
        increment_counter(counter_path)

    return {
        "stage": "ink-plan",
        "skipped": False,
        "blocked_any": blocked_any,
        "effective_blocked": effective_blocked,
        "dry_run": dry_run,
        "evidence_path": str(path),
        "checkers": outcomes,
    }


def _load_outline(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _build_cli_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ink_writer.planning_review.ink_plan_review",
        description="M4 P0 ink-plan Step 99 策划期审查",
    )
    p.add_argument("--book", required=True)
    p.add_argument("--outline", required=True, type=Path)
    p.add_argument("--base-dir", type=Path, default=None)
    p.add_argument("--skip-planning-review", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ink-writer" / "scripts"))
        from runtime_compat import enable_windows_utf8_stdio  # noqa: PLC0415

        enable_windows_utf8_stdio()
    except ImportError:
        pass

    args = _build_cli_parser().parse_args(argv)
    outline = _load_outline(args.outline)

    import anthropic  # noqa: PLC0415

    llm_client = anthropic.Anthropic()

    result = run_ink_plan_review(
        book=args.book,
        outline=outline,
        llm_client=llm_client,
        base_dir=args.base_dir,
        skip=args.skip_planning_review,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["effective_blocked"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
