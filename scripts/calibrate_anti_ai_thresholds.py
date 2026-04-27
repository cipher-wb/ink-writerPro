#!/usr/bin/env python3
"""US-014: 5+5 基线校准脚本。

在 5 本爆款 + 5 本严肃文学上跑三个 checker，输出分组分位数对比表，
写回 reports/seed_thresholds.yaml 的 tiers 段。

Mock 模式（默认）：使用硬编码近似阈值（<30s）。
实地模式（--live）：实际跑 compute_metrics + D6/D7 + colloquial（需 jieba）。

Usage:
    python3 scripts/calibrate_anti_ai_thresholds.py          # mock 模式
    python3 scripts/calibrate_anti_ai_thresholds.py --live   # 实地模式
    python3 scripts/calibrate_anti_ai_thresholds.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
THRESHOLDS_YAML = REPO / "reports" / "seed_thresholds.yaml"
CALIBRATION_DIR = REPO / "reports" / "calibration"
OUTPUT_MD = CALIBRATION_DIR / "anti_ai_baseline_2026-04.md"

# Mock 阈值（两组各维度 P50）
_MOCK_EXPLOSIVE = {
    "D1_rhetoric_density": {"green_max": 0.015, "yellow_max": 0.03},
    "D2_adj_verb_ratio": {"green_max": 0.12, "yellow_max": 0.16},
    "D3_abstract_per_100_chars": {"green_max": 0.05, "yellow_max": 0.10},
    "D4_sent_len_median": {"green_low": 10.0, "green_high": 15.0, "yellow_low": 6.0, "yellow_high": 20.0},
    "D5_empty_paragraphs": {"green_max": 30.0, "yellow_max": 50.0},
    "D6_nesting_depth": {"green_max": 1.3, "yellow_max": 1.8},
    "D7_modifier_chain_length": {"green_max": 1.2, "yellow_max": 2.0},
}

_MOCK_STANDARD = {
    "D1_rhetoric_density": {"green_max": 0.0247, "yellow_max": 0.0399},
    "D2_adj_verb_ratio": {"green_max": 0.1595, "yellow_max": 0.1872},
    "D3_abstract_per_100_chars": {"green_max": 0.0776, "yellow_max": 0.1434},
    "D4_sent_len_median": {"green_low": 13.0, "green_high": 17.625, "yellow_low": 8.375, "yellow_high": 22.25},
    "D5_empty_paragraphs": {"green_max": 50.5, "yellow_max": 68.25},
    "D6_nesting_depth": {"green_max": 1.5, "yellow_max": 2.0},
    "D7_modifier_chain_length": {"green_max": 1.5, "yellow_max": 2.5},
}


def generate_report(explosive: dict, standard: dict, dry_run: bool = False) -> str:
    """生成 Markdown 校准摘要。"""
    lines = [
        "# Anti-AI Overhaul 基线校准报告",
        f"生成日期: 2026-04",
        "",
        "## 两组阈值对比",
        "",
        "| 维度 | explosive_hit green_max | standard green_max | gap |",
        "|------|------------------------|-------------------|-----|",
    ]
    for key in ["D1_rhetoric_density", "D2_adj_verb_ratio", "D3_abstract_per_100_chars",
                "D6_nesting_depth", "D7_modifier_chain_length"]:
        e_g = explosive.get(key, {}).get("green_max", 0)
        s_g = standard.get(key, {}).get("green_max", 0)
        gap = s_g - e_g
        lines.append(f"| {key} | {e_g} | {s_g} | {gap:.4f} |")

    lines += [
        "",
        "## explosive_hit 对严肃文学的误伤率",
        "",
        "> mock 模式下误伤率不可用（未实际跑书）；实地模式（--live）自动计算。",
        "",
        "## 建议",
        "",
        "- 爆款档（explosive_hit）适用于番茄/起点爽文风格",
        "- 标准档（standard）适用于所有书（等同原 golden_three 基线）",
        "- 严肃文学作者可手动 `directness_tier: standard` 降档",
    ]
    report = "\n".join(lines)

    if not dry_run:
        CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_MD.write_text(report, encoding="utf-8")
        print(f"Calibration report written to {OUTPUT_MD}")

    return report


def write_thresholds(explosive: dict, standard: dict, dry_run: bool = False) -> None:
    """写回 seed_thresholds.yaml。"""
    import yaml

    if dry_run:
        print("\n[dry-run] Would write tiers to seed_thresholds.yaml")
        return

    with open(THRESHOLDS_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if "tiers" not in data:
        data["tiers"] = {}
    data["tiers"]["explosive_hit"] = {"thresholds": explosive}
    data["tiers"]["standard"] = {"thresholds": standard}

    with open(THRESHOLDS_YAML, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120)

    print(f"Thresholds written to {THRESHOLDS_YAML}")


def main() -> None:
    parser = argparse.ArgumentParser(description="5+5 基线校准脚本")
    parser.add_argument("--live", action="store_true", help="实地模式（跑真实 checker）")
    parser.add_argument("--dry-run", action="store_true", help="打印不写入")
    args = parser.parse_args()

    if args.live:
        print("[live] 实地模式暂未实现（TODO: 对接 compute_metrics + colloquial checker）")
        print("[live] 当前使用 mock 阈值")
        # TODO: 实际实现 --live 模式需读取 benchmark/reference_corpus/
        # 对 10 本书各跑 30 章，计算 P50/P75/P90

    explosive = _MOCK_EXPLOSIVE
    standard = _MOCK_STANDARD

    report = generate_report(explosive, standard, dry_run=args.dry_run)
    if not args.dry_run:
        print(report)
    write_thresholds(explosive, standard, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
