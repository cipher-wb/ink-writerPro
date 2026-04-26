#!/usr/bin/env python3
"""US-LR-008: 题材聚合器 — 从 CASE-LR-*.yaml 聚合到 genre_acceptance.json。

聚合算法:
    1. 扫 cases-dir/CASE-LR-*.yaml 全部病例。
    2. 对每本的 ``live_review_meta.genre_guess`` 数组每个标签独立计入
       (笛卡尔积; ["都市","重生"] 算 2 次贡献)。
    3. 按 genre 分组; case_count < min_cases 的 genre 被过滤。
    4. 统计 score_mean / score_median / score_p25 / score_p75
       (statistics.quantiles, method=exclusive; 全 None 时返 null)。
    5. verdict_pass_rate = count(verdict=='pass') / total。
    6. common_complaints: 聚合 negative 评论 dimension 频率,
       排序取 Top-N (默认 5); examples 取该 dim 下 raw_quote 前 3 条。
    7. 输出 schema_version=1.0 + updated_at + total_novels_analyzed (扫描 case 总数)
       + min_cases_per_genre + genres dict.

CLI:
    python3 scripts/live-review/aggregate_genre.py \\
        --cases-dir data/case_library/cases/live_review \\
        --out data/live-review/genre_acceptance.json

退出码:
    0  聚合成功
    1  内部错误 (yaml 解析失败 / IO 错误)
    2  cases-dir 不存在
"""
from __future__ import annotations

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio

_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    "../../ink-writer/scripts",
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass

import argparse  # noqa: E402
import json  # noqa: E402
import statistics  # noqa: E402
import sys  # noqa: E402
from collections import Counter, defaultdict  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

import yaml  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_DEFAULT_OUT = _REPO_ROOT / "data" / "live-review" / "genre_acceptance.json"
_DEFAULT_MIN_CASES = 3
_DEFAULT_TOP_COMPLAINTS = 5
_DEFAULT_EXAMPLES_PER_DIM = 3


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Aggregate live-review CASE-LR-*.yaml into per-genre acceptance stats "
            "(scores / verdict_pass_rate / common_complaints)."
        )
    )
    p.add_argument(
        "--cases-dir",
        dest="cases_dir",
        required=True,
        help="CASE-LR-*.yaml 输入目录",
    )
    p.add_argument(
        "--out",
        dest="out",
        default=str(_DEFAULT_OUT),
        help=f"genre_acceptance.json 输出路径 (默认 {_DEFAULT_OUT})",
    )
    p.add_argument(
        "--min-cases",
        dest="min_cases",
        type=int,
        default=_DEFAULT_MIN_CASES,
        help=f"genre 最小样本数 (默认 {_DEFAULT_MIN_CASES}; 低于该值的 genre 被过滤)",
    )
    p.add_argument(
        "--top-complaints",
        dest="top_complaints",
        type=int,
        default=_DEFAULT_TOP_COMPLAINTS,
        help=f"common_complaints 取 Top-N (默认 {_DEFAULT_TOP_COMPLAINTS})",
    )
    return p


def _safe_quantiles(
    scores: list[float],
) -> tuple[float | None, float | None, float | None]:
    """Compute (p25, median, p75) with None-safe fallback for small samples."""
    if not scores:
        return (None, None, None)
    if len(scores) == 1:
        return (None, float(scores[0]), None)
    q = statistics.quantiles(scores, n=4, method="exclusive")
    return (q[0], q[1], q[2])


def _load_cases(cases_dir: Path) -> list[dict]:
    cases: list[dict] = []
    for path in sorted(cases_dir.glob("CASE-LR-*.yaml")):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data is None:
            continue
        cases.append(data)
    return cases


def _summarize_genre(
    cases_in_genre: list[dict],
    *,
    top_complaints: int,
) -> dict:
    metas = [c["live_review_meta"] for c in cases_in_genre]
    scores = [m["score"] for m in metas if m.get("score") is not None]
    verdicts = [m["verdict"] for m in metas]
    pass_count = sum(1 for v in verdicts if v == "pass")
    verdict_pass_rate = pass_count / len(verdicts) if verdicts else 0.0

    if scores:
        score_mean: float | None = statistics.mean(scores)
        score_median: float | None = statistics.median(scores)
        p25, _, p75 = _safe_quantiles(scores)
    else:
        score_mean = None
        score_median = None
        p25 = None
        p75 = None

    negatives: list[dict] = []
    for m in metas:
        for cm in m.get("comments", []):
            if cm.get("severity") == "negative":
                negatives.append(cm)

    dim_counter = Counter(cm["dimension"] for cm in negatives)
    total_neg = len(negatives)
    common_complaints: list[dict] = []
    if total_neg > 0:
        for dim, cnt in dim_counter.most_common(top_complaints):
            examples: list[str] = []
            for cm in negatives:
                if cm["dimension"] != dim:
                    continue
                ex = cm.get("raw_quote") or cm.get("content", "")
                if ex:
                    examples.append(ex)
                if len(examples) >= _DEFAULT_EXAMPLES_PER_DIM:
                    break
            common_complaints.append(
                {
                    "dimension": dim,
                    "frequency": cnt / total_neg,
                    "examples": examples,
                }
            )

    case_ids = sorted({c["case_id"] for c in cases_in_genre})

    return {
        "case_count": len(cases_in_genre),
        "score_mean": score_mean,
        "score_median": score_median,
        "score_p25": p25,
        "score_p75": p75,
        "verdict_pass_rate": verdict_pass_rate,
        "common_complaints": common_complaints,
        "case_ids": case_ids,
    }


def aggregate(cases_dir: Path, *, min_cases: int, top_complaints: int) -> dict:
    cases = _load_cases(cases_dir)

    by_genre: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        meta = case.get("live_review_meta", {}) or {}
        for genre in meta.get("genre_guess", []) or []:
            by_genre[genre].append(case)

    genres_out: dict[str, dict] = {}
    for genre in sorted(by_genre):
        cases_in_genre = by_genre[genre]
        if len(cases_in_genre) < min_cases:
            continue
        genres_out[genre] = _summarize_genre(
            cases_in_genre, top_complaints=top_complaints
        )

    return {
        "schema_version": "1.0",
        "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "total_novels_analyzed": len(cases),
        "min_cases_per_genre": min_cases,
        "genres": genres_out,
    }


def _run(args: argparse.Namespace) -> int:
    cases_dir = Path(args.cases_dir)
    if not cases_dir.is_dir():
        print(
            f"[aggregate_genre] cases-dir not found: {cases_dir}",
            file=sys.stderr,
        )
        return 2

    out = aggregate(
        cases_dir,
        min_cases=args.min_cases,
        top_complaints=args.top_complaints,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"[aggregate_genre] OK {len(out['genres'])} genre(s) "
        f"({out['total_novels_analyzed']} cases) → {out_path}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
