"""ink-init Step 99 编排（M4 P0 spec §5.1）。

串行跑 4 个策划期 checker：
1. ``genre-novelty`` — 题材新颖度（vs 起点 top200）
2. ``golden-finger-spec`` — 金手指四维度规格
3. ``naming-style`` — 角色起名风格（纯规则）
4. ``protagonist-motive`` — 主角动机三维度

setting JSON schema（最小集）::

    {
      "genre_tags": ["仙侠", "正剧"],
      "main_plot_one_liner": "...",
      "golden_finger_description": "...",
      "character_names": [{"role": "protagonist", "name": "顾望安"}, ...],
      "protagonist_motive_description": "..."
    }

输出：``<base_dir>/<book>/planning_evidence_chain.json`` 写入 stage='ink-init' 段。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ink_writer.checker_pipeline.thresholds_loader import load_thresholds
from ink_writer.checkers.genre_novelty import check_genre_novelty
from ink_writer.checkers.golden_finger_spec import check_golden_finger_spec
from ink_writer.checkers.naming_style import check_naming_style
from ink_writer.checkers.protagonist_motive import check_protagonist_motive
from ink_writer.evidence_chain import EvidenceChain, write_planning_evidence_chain
from ink_writer.planning_review.dry_run import (
    DEFAULT_COUNTER_PATH,
    increment_counter,
    is_dry_run_active,
)

DEFAULT_TOP200_PATH = Path("data/market_intelligence/qidian_top200.jsonl")
SKIP_REASON = "--skip-planning-review"


def _load_top200(path: Path | str | None = None) -> list[dict[str, Any]]:
    """读 jsonl 后端；缺失或解析失败 → 空列表（genre-novelty 跳过逻辑兜底）。"""
    target = Path(path) if path is not None else DEFAULT_TOP200_PATH
    if not target.exists():
        return []
    items: list[dict[str, Any]] = []
    try:
        with open(target, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                items.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return []
    return items


def _resolve_dry_run_path(path: Path | str | None, cfg: dict[str, Any]) -> Path:
    if path is not None:
        return Path(path)
    cfg_path = cfg.get("counter_path")
    return Path(cfg_path) if cfg_path else DEFAULT_COUNTER_PATH


def _inject_cases(report_dict: dict[str, Any], section: dict[str, Any]) -> None:
    """阻断时把 thresholds yaml 的 case_ids 注入到 report.cases_hit。"""
    if not report_dict.get("blocked"):
        return
    case_ids = list(section.get("case_ids", []) or [])
    if case_ids:
        report_dict["cases_hit"] = case_ids


def _checker_outcome(name: str, report: Any) -> dict[str, Any]:
    data = report.to_dict() if hasattr(report, "to_dict") else dict(report)
    return {
        "id": name,
        "score": data.get("score"),
        "blocked": data.get("blocked", False),
        "cases_hit": data.get("cases_hit", []),
        "notes": data.get("notes"),
        "details": data,
    }


def run_ink_init_review(
    *,
    book: str,
    setting: dict[str, Any],
    llm_client: Any,
    base_dir: Path | str | None = None,
    skip: bool = False,
    dry_run_counter_path: Path | str | None = None,
    thresholds_path: Path | str | None = None,
    top200_path: Path | str | None = None,
    naming_blacklist_path: Path | str | None = None,
) -> dict[str, Any]:
    """ink-init Step 99 入口；返回结构化结果。

    ``skip=True`` 时不调任何 checker，仅写一条 skipped stage。
    其余路径按 4 checker 串行 → 阻断聚合 → 写 evidence。
    """
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
        stage="ink-init",
        dry_run=dry_run,
    )

    if skip:
        evidence.outcome = "skipped"
        evidence.human_overrides.append(
            {"action": "skip", "reason": SKIP_REASON, "stage": "ink-init"}
        )
        skipped_dict = evidence.to_dict()
        skipped_dict["skipped"] = True
        skipped_dict["skip_reason"] = SKIP_REASON
        path = write_planning_evidence_chain(
            book=book, evidence=evidence, base_dir=base_dir
        )
        return {
            "stage": "ink-init",
            "skipped": True,
            "skip_reason": SKIP_REASON,
            "blocked_any": False,
            "effective_blocked": False,
            "dry_run": dry_run,
            "evidence_path": str(path),
            "checkers": [],
        }

    outcomes: list[dict[str, Any]] = []
    blocked_any = False

    # 1. genre-novelty
    section = thresholds.get("genre_novelty", {}) or {}
    top200 = _load_top200(top200_path)
    genre_report = check_genre_novelty(
        genre_tags=list(setting.get("genre_tags", []) or []),
        main_plot_one_liner=str(setting.get("main_plot_one_liner", "") or ""),
        top200=top200,
        llm_client=llm_client,
        block_threshold=float(section.get("block_threshold", 0.40)),
    )
    g_dict = genre_report.to_dict()
    _inject_cases(g_dict, section)
    blocked_any = blocked_any or bool(g_dict.get("blocked"))
    outcomes.append({
        "id": "genre-novelty",
        "score": g_dict["score"],
        "blocked": g_dict["blocked"],
        "cases_hit": g_dict.get("cases_hit", []),
        "notes": g_dict.get("notes"),
        "details": g_dict,
    })

    # 2. golden-finger-spec
    section = thresholds.get("golden_finger_spec", {}) or {}
    spec_report = check_golden_finger_spec(
        description=str(setting.get("golden_finger_description", "") or ""),
        llm_client=llm_client,
        block_threshold=float(section.get("block_threshold", 0.65)),
    )
    s_dict = spec_report.to_dict()
    _inject_cases(s_dict, section)
    blocked_any = blocked_any or bool(s_dict.get("blocked"))
    outcomes.append({
        "id": "golden-finger-spec",
        "score": s_dict["score"],
        "blocked": s_dict["blocked"],
        "cases_hit": s_dict.get("cases_hit", []),
        "notes": s_dict.get("notes"),
        "details": s_dict,
    })

    # 3. naming-style（纯规则）
    section = thresholds.get("naming_style", {}) or {}
    name_report = check_naming_style(
        character_names=list(setting.get("character_names", []) or []),
        blacklist_path=naming_blacklist_path,
        block_threshold=float(section.get("block_threshold", 0.70)),
    )
    n_dict = name_report.to_dict()
    _inject_cases(n_dict, section)
    blocked_any = blocked_any or bool(n_dict.get("blocked"))
    outcomes.append({
        "id": "naming-style",
        "score": n_dict["score"],
        "blocked": n_dict["blocked"],
        "cases_hit": n_dict.get("cases_hit", []),
        "notes": n_dict.get("notes"),
        "details": n_dict,
    })

    # 4. protagonist-motive
    section = thresholds.get("protagonist_motive", {}) or {}
    motive_report = check_protagonist_motive(
        description=str(setting.get("protagonist_motive_description", "") or ""),
        llm_client=llm_client,
        block_threshold=float(section.get("block_threshold", 0.65)),
    )
    m_dict = motive_report.to_dict()
    _inject_cases(m_dict, section)
    blocked_any = blocked_any or bool(m_dict.get("blocked"))
    outcomes.append({
        "id": "protagonist-motive",
        "score": m_dict["score"],
        "blocked": m_dict["blocked"],
        "cases_hit": m_dict.get("cases_hit", []),
        "notes": m_dict.get("notes"),
        "details": m_dict,
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
        "stage": "ink-init",
        "skipped": False,
        "blocked_any": blocked_any,
        "effective_blocked": effective_blocked,
        "dry_run": dry_run,
        "evidence_path": str(path),
        "checkers": outcomes,
    }


def _load_setting(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _build_cli_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ink_writer.planning_review.ink_init_review",
        description="M4 P0 ink-init Step 99 策划期审查",
    )
    p.add_argument("--book", required=True)
    p.add_argument("--setting", required=True, type=Path)
    p.add_argument("--base-dir", type=Path, default=None)
    p.add_argument("--skip-planning-review", action="store_true")
    p.add_argument("--top200", type=Path, default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ink-writer" / "scripts"))
        from runtime_compat import enable_windows_utf8_stdio  # noqa: PLC0415

        enable_windows_utf8_stdio()
    except ImportError:
        pass

    args = _build_cli_parser().parse_args(argv)
    setting = _load_setting(args.setting)

    # CLI 默认用 anthropic SDK（spec 标 LLM=glm-4.6 走 anthropic-shape proxy）；
    # 单测注入 FakeLLMClient 不走 CLI 入口。
    import anthropic  # noqa: PLC0415

    llm_client = anthropic.Anthropic()

    result = run_ink_init_review(
        book=args.book,
        setting=setting,
        llm_client=llm_client,
        base_dir=args.base_dir,
        skip=args.skip_planning_review,
        top200_path=args.top200,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["effective_blocked"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
