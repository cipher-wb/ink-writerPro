#!/usr/bin/env python3
"""US-008: 从 reference corpus 校准 explosive_hit 阈值桶。

从 benchmark/reference_corpus/ 取前 N 本书（默认 5 本）计算 D1-D7 分位数，
将结果写入 reports/seed_thresholds.yaml 的 tiers.explosive_hit 段。

Mock 模式（默认）：仅读取书名，生成近似阈值（<30s）。
实地模式（--live）：实际对全书跑 compute_metrics + D6/D7，聚合后取分位。

Usage:
    python3 scripts/regen_directness_thresholds_explosive.py          # mock 模式
    python3 scripts/regen_directness_thresholds_explosive.py --live   # 实地模式（需 jieba）
    python3 scripts/regen_directness_thresholds_explosive.py --dry-run  # 打印不写入
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORPUS = REPO / "benchmark" / "reference_corpus"
THRESHOLDS_YAML = REPO / "reports" / "seed_thresholds.yaml"

# explosive_hit 默认阈值（mock 模式直接写入这些值）
_EXPLOSIVE_THRESHOLDS = {
    "D1_rhetoric_density": {
        "direction": "lower_is_better",
        "green_max": 0.015,
        "yellow_max": 0.03,
    },
    "D2_adj_verb_ratio": {
        "direction": "lower_is_better",
        "green_max": 0.12,
        "yellow_max": 0.16,
    },
    "D3_abstract_per_100_chars": {
        "direction": "lower_is_better",
        "green_max": 0.05,
        "yellow_max": 0.10,
    },
    "D4_sent_len_median": {
        "direction": "mid_is_better",
        "green_low": 10.0,
        "green_high": 15.0,
        "yellow_low": 6.0,
        "yellow_high": 20.0,
    },
    "D5_empty_paragraphs": {
        "direction": "lower_is_better",
        "green_max": 30.0,
        "yellow_max": 50.0,
    },
    "D6_nesting_depth": {
        "direction": "lower_is_better",
        "green_max": 1.3,
        "yellow_max": 1.8,
    },
    "D7_modifier_chain_length": {
        "direction": "lower_is_better",
        "green_max": 1.2,
        "yellow_max": 2.0,
    },
}


def list_corpus_books(limit: int = 5) -> list[Path]:
    """返回 corpus 中前 limit 本书的目录 path。"""
    if not CORPUS.is_dir():
        print(f"corpus 目录不存在: {CORPUS}", file=sys.stderr)
        return []
    dirs = sorted(
        [d for d in CORPUS.iterdir() if d.is_dir() and not d.name.startswith(".")],
        key=lambda d: d.name,
    )
    return dirs[:limit]


def mock_generate(book_dirs: list[Path]) -> dict:
    """Mock 模式：返回近似阈值（不实际跑全文分析）。"""
    print(f"[mock] 从 {len(book_dirs)} 本书生成近似 explosive_hit 阈值")
    for d in book_dirs:
        print(f"  - {d.name}")
    return _EXPLOSIVE_THRESHOLDS


def live_generate(book_dirs: list[Path]) -> dict:
    """实地模式：对每本书全文计算 D1-D7，聚合后取中位数作为阈值。

    NOTE: 实地模式需要 jieba 分词，处理时间取决于 corpus 大小。
    """
    import statistics

    sys.path.insert(0, str(REPO / "scripts"))
    from analyze_prose_directness import compute_metrics, _ABSTRACT_SEED  # noqa: E402

    sys.path.insert(0, str(REPO / "ink_writer" / "prose"))
    from directness_checker import (  # noqa: E402
        _calc_d6_nesting_depth,
        _calc_d7_modifier_chain_length,
    )

    all_metrics: dict[str, list[float]] = {
        "D1_rhetoric_density": [],
        "D2_adj_verb_ratio": [],
        "D3_abstract_per_100_chars": [],
        "D4_sent_len_median": [],
        "D5_empty_paragraphs": [],
        "D6_nesting_depth": [],
        "D7_modifier_chain_length": [],
    }

    for book_dir in book_dirs:
        print(f"[live] 处理: {book_dir.name}...")
        # 收集该书所有章节文本
        chapters: list[str] = []
        for f in sorted(book_dir.rglob("*.md")):
            try:
                text = f.read_text(encoding="utf-8")
                if len(text) >= 100:
                    chapters.append(text)
            except Exception:
                pass

        if not chapters:
            print(f"  ⚠ {book_dir.name}: 无有效章节，跳过")
            continue

        for ch_text in chapters:
            metrics = compute_metrics(ch_text, abstract_words=_ABSTRACT_SEED)
            d6 = _calc_d6_nesting_depth(ch_text)
            d7_mean, _ = _calc_d7_modifier_chain_length(ch_text)

            all_metrics["D1_rhetoric_density"].append(float(metrics.get("D1_rhetoric_density", 0)))
            all_metrics["D2_adj_verb_ratio"].append(float(metrics.get("D2_adj_verb_ratio", 0)))
            all_metrics["D3_abstract_per_100_chars"].append(float(metrics.get("D3_abstract_per_100_chars", 0)))
            all_metrics["D4_sent_len_median"].append(float(metrics.get("D4_sent_len_median", 0)))
            all_metrics["D5_empty_paragraphs"].append(float(metrics.get("D5_empty_paragraphs", 0)))
            all_metrics["D6_nesting_depth"].append(d6)
            all_metrics["D7_modifier_chain_length"].append(d7_mean)

        print(f"  ✓ {len(chapters)} 章，累计 {len(all_metrics['D1_rhetoric_density'])} 条")

    # 以 p50 为 green_max, p75 为 yellow_max（lower_is_better 维度）
    result: dict = {}
    for key in [
        "D1_rhetoric_density", "D2_adj_verb_ratio", "D3_abstract_per_100_chars",
        "D5_empty_paragraphs", "D6_nesting_depth", "D7_modifier_chain_length",
    ]:
        vals = sorted(all_metrics[key])
        if not vals:
            continue
        result[key] = {
            "direction": "lower_is_better",
            "green_max": round(statistics.median(vals), 4),
            "yellow_max": round(_percentile(vals, 75), 4),
        }

    # D4: mid_is_better
    d4_vals = sorted(all_metrics["D4_sent_len_median"])
    if d4_vals:
        result["D4_sent_len_median"] = {
            "direction": "mid_is_better",
            "green_low": round(_percentile(d4_vals, 25), 2),
            "green_high": round(_percentile(d4_vals, 75), 2),
            "yellow_low": round(max(4.0, _percentile(d4_vals, 10)), 2),
            "yellow_high": round(_percentile(d4_vals, 90), 2),
        }

    return result


def _percentile(sorted_vals: list[float], p: float) -> float:
    """线性插值法计算百分位数。"""
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    k = (p / 100.0) * (n - 1)
    f = int(k)
    c = k - f
    if f + 1 < n:
        return sorted_vals[f] + c * (sorted_vals[f + 1] - sorted_vals[f])
    return sorted_vals[f]


def write_yaml(thresholds: dict, dry_run: bool = False) -> None:
    """将 thresholds 写回 YAML 的 tiers.explosive_hit 段。"""
    import yaml  # noqa: PLC0415

    if dry_run:
        print("\n[dry-run] 将写入 tiers.explosive_hit.thresholds:")
        print(yaml.dump({"tiers": {"explosive_hit": {"thresholds": thresholds}}},
                        default_flow_style=False, allow_unicode=True, sort_keys=False))
        return

    with open(THRESHOLDS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if "tiers" not in data:
        data["tiers"] = {}
    if "explosive_hit" not in data["tiers"]:
        data["tiers"]["explosive_hit"] = {}
    data["tiers"]["explosive_hit"]["thresholds"] = thresholds

    with open(THRESHOLDS_YAML, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False,
                  width=120)

    print(f"\n✓ 已写入 {THRESHOLDS_YAML}")


def main() -> None:
    parser = argparse.ArgumentParser(description="校准 explosive_hit 阈值桶")
    parser.add_argument("--live", action="store_true", help="实地模式（需 jieba）")
    parser.add_argument("--dry-run", action="store_true", help="打印不写入")
    parser.add_argument("--books", type=int, default=5, help="使用前 N 本书（默认 5）")
    args = parser.parse_args()

    books = list_corpus_books(limit=args.books)
    if not books:
        print("无可用 corpus 书，使用硬编码默认阈值")
        thresholds = _EXPLOSIVE_THRESHOLDS
    elif args.live:
        thresholds = live_generate(books)
    else:
        thresholds = mock_generate(books)

    write_yaml(thresholds, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
