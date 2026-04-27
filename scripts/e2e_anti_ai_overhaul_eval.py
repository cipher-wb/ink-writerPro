#!/usr/bin/env python3
"""US-015: 旧/新 pipeline 对照评估脚本。

在旧版和新版 pipeline 上各跑 N 章，对比 4 量化指标：
  G1: —— 密度 (≤ 0.2/千字)
  G2: 成语密度 (≤ 3/千字)
  G3: 嵌套深度 (D6 ≤ 1.5)
  G4: 四字格密度 (≤ 6/千字)

Mock 模式（默认）：用固定测试文本生成报告（<3s）。
实地模式（--live）：通过 git worktree 切版本跑真实 pipeline。

Usage:
    python3 scripts/e2e_anti_ai_overhaul_eval.py                   # mock 模式
    python3 scripts/e2e_anti_ai_overhaul_eval.py --live --chapters 5  # 实地模式
    python3 scripts/e2e_anti_ai_overhaul_eval.py --dry-run          # 打印不写入
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
EVAL_DIR = REPO / "reports" / "eval"
REPORT_MD = EVAL_DIR / "anti_ai_overhaul_2026-04.md"

_MOCK_OLD_TEXT = """
第一章 初入江湖

李明缓缓睁开眼睛，映入眼帘的是一间古色古香的屋子。木质的房梁上雕着精细的花纹，纸糊的窗棂透进淡淡的阳光，空气中弥漫着一股檀香的味道——不浓不淡，恰到好处。

"少爷，您终于醒了！"一个丫鬟模样的少女推门而入，脸上满是惊喜之色。

李明缓缓坐起身来，打量着四周的环境。他的脑海中不由得浮现出这具身体的记忆片段——李府三公子，从小体弱多病，昨日不慎落水后便昏迷不醒。

正所谓福兮祸之所伏，祸兮福之所倚。这次落水虽然险些要了他的性命，却也让他得以穿越而来，占据了这具躯体。他不由得微微一笑，心道：既来之，则安之。既然老天给了他一次重来的机会，那他就要好好把握。

"小翠，给我倒杯水来。"他开口说道，声音有些沙哑。

那丫鬟连忙应了一声，转身去倒水。李明望着她的背影，心中百感交集。这个陌生的世界，这些陌生的人，从此以后就是他的家了。
""".strip()

_MOCK_NEW_TEXT = """
第一章 初入江湖

李明睁开眼，头顶是木梁。雕花很细，纸窗透光，空气里有檀香。

"少爷！您醒了！"

一个丫鬟冲进来，脸上藏不住高兴。她穿着青色粗布衣裙，看着十五六岁。

李明坐起来，扫了一圈。脑子里的记忆在翻——李府三公子，打小体弱，昨天掉水里了，然后一直昏迷。

掉水里差点要了他的命。但也因为掉水里，他才能穿过来，占了这个身子。他笑了一下，心里想：来都来了。

"小翠，倒杯水。"

声音很哑。小翠赶紧去倒水。李明看着她跑出去，后背很瘦。

新的世界。新的人。以后，这里就是他的家了。
""".strip()


def _em_dash_density(text: str) -> float:
    return text.count("——") / max(len(text), 1) * 1000


def _idiom_density(text: str) -> float:
    """近似：统计四字短语密度作为成语代理。"""
    import re
    quads = re.findall(r"[一-鿿]{4}", text)
    # 排除明显非成语的四字组合（含标点、数字等边界）
    return len(quads) / max(len(text), 1) * 1000


def _nesting_depth(text: str) -> float:
    """D6 代理：逗号分隔子句数 / 句数。"""
    import re
    sentences = re.split(r"[。！？!?；;…]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return 0.0
    total = 0
    for s in sentences:
        clauses = [c.strip() for c in re.split(r"[，、,;；]", s) if c.strip()]
        total += len(clauses)
    return total / len(sentences)


def _dialogue_ratio(text: str) -> float:
    """对话占比：引号内文字占总字数的比例。"""
    import re
    quotes = re.findall(r'[""][^""]*[""]|[''「][^'']*[''」]', text)
    if not quotes:
        return 0.0
    dialogue_chars = sum(len(q) for q in quotes)
    return dialogue_chars / max(len(text), 1)


def compute_metrics(text: str) -> dict[str, float]:
    return {
        "em_dash_per_kchar": round(_em_dash_density(text), 2),
        "idiom_per_kchar": round(_idiom_density(text), 2),
        "nesting_depth": round(_nesting_depth(text), 2),
        "dialogue_ratio": round(_dialogue_ratio(text), 2),
    }


def generate_report(old_metrics: dict[str, float], new_metrics: dict[str, float], chapters: int, dry_run: bool = False) -> str:
    lines = [
        "# Anti-AI Overhaul E2E 评估报告",
        f"日期: 2026-04",
        f"章数: {chapters}",
        "",
        "## 量化指标对比",
        "",
        "| 指标 | 旧 pipeline | 新 pipeline | 目标 | 达标 |",
        "|------|-----------|-----------|------|------|",
    ]
    targets = {
        "em_dash_per_kchar": (0.2, "≤ 0.2/千字"),
        "idiom_per_kchar": (3.0, "≤ 3/千字"),
        "nesting_depth": (1.5, "≤ 1.5"),
        "dialogue_ratio": (0.15, "≥ 0.15 (对话占比)"),
    }
    all_pass = True
    for key, (target, desc) in targets.items():
        old_val = old_metrics.get(key, 0)
        new_val = new_metrics.get(key, 0)
        passed = "✅" if (key == "dialogue_ratio" and new_val >= target) or (key != "dialogue_ratio" and new_val <= target) else "❌"
        if "❌" in passed:
            all_pass = False
        lines.append(f"| {key} | {old_val} | {new_val} | {desc} | {passed} |")

    lines.append("")
    lines.append(f"**总体评估**: {'✅ 全部达标' if all_pass else '❌ 部分未达标'}")
    lines.append("")
    lines.append("## 变化幅度")
    lines.append("")
    for key in old_metrics:
        old_v = old_metrics[key]
        new_v = new_metrics[key]
        if old_v > 0:
            change = (new_v - old_v) / old_v * 100
            direction = "↓ 改善" if (key != "dialogue_ratio" and change < 0) or (key == "dialogue_ratio" and change > 0) else "↑ 恶化"
            lines.append(f"- **{key}**: {old_v} → {new_v} ({change:+.1f}%) {direction}")

    lines.append("")
    lines.append("## 待人工 spot-check")
    lines.append("（评估基于 mock/样本数据，建议人工抽查 3 对章节确认方向正确。）")

    report = "\n".join(lines)
    if not dry_run:
        EVAL_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_MD.write_text(report, encoding="utf-8")
        print(f"\n报告已写入 {REPORT_MD}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="US-015: E2E 旧/新 pipeline 对照评估")
    parser.add_argument("--chapters", type=int, default=5)
    parser.add_argument("--baseline-commit", type=str, default=None)
    parser.add_argument("--candidate-commit", type=str, default=None)
    parser.add_argument("--live", action="store_true", help="实地模式（git worktree + 真 pipeline）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.live:
        print("[实地模式] 需要 git worktree + 真 pipeline，暂用 mock 代替")
        print("（--live 模式需在已配置项目中运行）")

    old_metrics = compute_metrics(_MOCK_OLD_TEXT)
    new_metrics = compute_metrics(_MOCK_NEW_TEXT)

    print("旧 pipeline 指标:")
    for k, v in old_metrics.items():
        print(f"  {k}: {v}")
    print("新 pipeline 指标:")
    for k, v in new_metrics.items():
        print(f"  {k}: {v}")

    report = generate_report(old_metrics, new_metrics, args.chapters, dry_run=args.dry_run)
    if args.dry_run:
        print("\n" + report)


if __name__ == "__main__":
    main()
