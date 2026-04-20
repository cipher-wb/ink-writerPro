#!/usr/bin/env python3
"""gen_directness_baseline_report.py — 从 US-001 stats.json 汇总基线阈值报告（US-002）

消费 ``reports/prose-directness-stats.json``（US-001 产出，每章一行 JSONL），
产出两份文件：

1. ``reports/prose-directness-baseline.md``——人类可读基线报告，含：
   * 场景样本分布（golden_three / combat / other）
   * 5 维度 P25/P50/P75 分布表（按场景分段）
   * Green/Yellow/Red 推荐阈值（lower_is_better 与 mid_is_better 两类）
   * 推荐阈值常量代码块（US-005 directness-checker 可直接引用）
   * 跨书对比表（最直白 Top 5 / 最华丽 Top 5）

2. ``reports/seed_thresholds.yaml``——机器可读阈值表，供 US-005
   directness-checker 与 US-010 现有 checker 阈值微调消费。

评分规则（consistent with PRD US-005 0-10 分制的 Green≥8 / Yellow 6-8 / Red<6）:

* **lower_is_better**（D1 修辞密度 / D2 形容词-动词比 / D3 抽象词密度 /
  D5 空描写段）: value ≤ P50 → Green；P50 < value ≤ P75 → Yellow；
  value > P75 → Red。
* **mid_is_better**（D4 句长中位数）: [P25, P75] → Green；外扩 1 个 IQR
  → Yellow；更远 → Red。

用法::

    python scripts/gen_directness_baseline_report.py \\
        --stats reports/prose-directness-stats.json \\
        --markdown reports/prose-directness-baseline.md \\
        --yaml reports/seed_thresholds.yaml
"""
from __future__ import annotations

import os as _os_win_stdio
import sys as _sys_win_stdio

_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    "../ink-writer/scripts",
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio  # type: ignore[import-not-found]

    _enable_utf8_stdio()
except Exception:
    pass

import argparse  # noqa: E402
import json  # noqa: E402
import statistics  # noqa: E402
from collections import defaultdict  # noqa: E402
from collections.abc import Iterable, Sequence  # noqa: E402
from datetime import date  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

_METRIC_NAMES: tuple[str, ...] = (
    "D1_rhetoric_density",
    "D2_adj_verb_ratio",
    "D3_abstract_per_100_chars",
    "D4_sent_len_median",
    "D5_empty_paragraphs",
)

_METRIC_LABELS: dict[str, str] = {
    "D1_rhetoric_density": "D1 修辞密度 (比喻+排比/总句数)",
    "D2_adj_verb_ratio": "D2 形容词-动词比",
    "D3_abstract_per_100_chars": "D3 抽象词密度 (每 100 字)",
    "D4_sent_len_median": "D4 句长中位数 (词)",
    "D5_empty_paragraphs": "D5 空描写段数",
}

_METRIC_DIRECTIONS: dict[str, str] = {
    "D1_rhetoric_density": "lower_is_better",
    "D2_adj_verb_ratio": "lower_is_better",
    "D3_abstract_per_100_chars": "lower_is_better",
    "D4_sent_len_median": "mid_is_better",
    "D5_empty_paragraphs": "lower_is_better",
}

# Checker 代码常量的 snake_case 名，PRD 明示要"如 RHETORIC_MAX=0.15"式，留给
# US-005 Python 模块直接 import。
_METRIC_CONST_NAMES: dict[str, str] = {
    "D1_rhetoric_density": "RHETORIC_MAX",
    "D2_adj_verb_ratio": "ADJ_VERB_MAX",
    "D3_abstract_per_100_chars": "ABSTRACT_MAX",
    "D4_sent_len_median": "SENT_LEN",
    "D5_empty_paragraphs": "EMPTY_PARA_MAX",
}

_SCENE_ORDER: tuple[str, ...] = ("golden_three", "combat", "other")

# combat 场景在 benchmark 里可能 0 样本（US-001 启发式无法从 ch###.txt 文件名
# 识别战斗标题）——此时 checker 运行期会读这里的 inherit 配置，退回黄金三章阈值，
# 理由：黄金三章本身就是快节奏高激活区，与战斗场景直白诉求同向。
_COMBAT_FALLBACK_SCENE: str = "golden_three"


def load_records(path: Path) -> list[dict[str, Any]]:
    """读取 US-001 的 JSONL stats。空行跳过。"""
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if text:
                records.append(json.loads(text))
    return records


def percentiles(values: Sequence[float]) -> dict[str, float]:
    """统计摘要：n / min / p25 / p50 / p75 / max。空序列返回全 0。"""
    if not values:
        return {"n": 0, "min": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "max": 0.0}
    sorted_vals = sorted(float(v) for v in values)
    n = len(sorted_vals)
    if n == 1:
        only = sorted_vals[0]
        return {"n": 1, "min": only, "p25": only, "p50": only, "p75": only, "max": only}
    quarts = statistics.quantiles(sorted_vals, n=4)  # [p25, p50, p75]
    return {
        "n": n,
        "min": sorted_vals[0],
        "p25": float(quarts[0]),
        "p50": float(statistics.median(sorted_vals)),
        "p75": float(quarts[2]),
        "max": sorted_vals[-1],
    }


def bucket_by_scene(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, list[float]]]:
    """scene → metric_name → list[value]"""
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for rec in records:
        scene = str(rec.get("scene", "other"))
        metrics = rec.get("metrics", {}) or {}
        for name in _METRIC_NAMES:
            if name in metrics:
                try:
                    buckets[scene][name].append(float(metrics[name]))
                except (TypeError, ValueError):
                    continue
    return {scene: dict(inner) for scene, inner in buckets.items()}


def compute_scene_percentiles(
    scene_bucket: dict[str, list[float]],
) -> dict[str, dict[str, float]]:
    """对一个场景下的各 metric 批量产出 percentile 摘要。"""
    return {name: percentiles(scene_bucket.get(name, [])) for name in _METRIC_NAMES}


def recommend_thresholds(
    scene_pcts: dict[str, dict[str, float]],
) -> dict[str, dict[str, Any]]:
    """把 percentiles 转成 Green/Yellow/Red 阈值。

    * lower_is_better：暴露 green_max (=P50) / yellow_max (=P75) / red_min (=P75)
    * mid_is_better：暴露 green_low/high (=P25/P75) 与 yellow_low/high (外扩 1 IQR)
    """
    out: dict[str, dict[str, Any]] = {}
    for name in _METRIC_NAMES:
        direction = _METRIC_DIRECTIONS[name]
        pcts = scene_pcts.get(name, {"p25": 0.0, "p50": 0.0, "p75": 0.0})
        if direction == "lower_is_better":
            out[name] = {
                "direction": direction,
                "green_max": round(pcts["p50"], 4),
                "yellow_max": round(pcts["p75"], 4),
                "red_min": round(pcts["p75"], 4),
            }
        else:  # mid_is_better
            iqr = max(pcts["p75"] - pcts["p25"], 0.0)
            out[name] = {
                "direction": direction,
                "green_low": round(pcts["p25"], 4),
                "green_high": round(pcts["p75"], 4),
                "yellow_low": round(max(pcts["p25"] - iqr, 0.0), 4),
                "yellow_high": round(pcts["p75"] + iqr, 4),
            }
    return out


def compute_book_means(
    records: Iterable[dict[str, Any]],
) -> list[tuple[str, float]]:
    """跨书对比用：按书聚合 D1+D3 均值，用作"华丽度"排序锚。"""
    per_book: dict[str, list[float]] = defaultdict(list)
    for rec in records:
        metrics = rec.get("metrics", {}) or {}
        d1 = float(metrics.get("D1_rhetoric_density", 0.0))
        d3 = float(metrics.get("D3_abstract_per_100_chars", 0.0))
        per_book[str(rec.get("book", "?"))].append(d1 + d3)
    pairs = [(b, statistics.mean(vs)) for b, vs in per_book.items() if vs]
    pairs.sort(key=lambda x: x[1])
    return pairs


def render_markdown(
    records: Sequence[dict[str, Any]],
    scene_counts: dict[str, int],
    scene_stats: dict[str, dict[str, dict[str, float]]],
    thresholds: dict[str, dict[str, dict[str, Any]]],
    *,
    generated: str,
    source: Path,
) -> str:
    total = len(records)
    books = sorted({str(rec.get("book", "?")) for rec in records})

    lines: list[str] = []
    lines.append("# Prose Directness Baseline Report")
    lines.append("")
    lines.append(f"- Generated: {generated}")
    lines.append(f"- Source: `{source}`")
    lines.append(f"- Total chapters: **{total}** from **{len(books)}** books")
    lines.append("")
    lines.append(
        "> 本报告消费 US-001 产出的 5 维度直白密度扫描结果，为 US-005 directness-checker"
    )
    lines.append("> 提供 P25/P50/P75 基线与 Green/Yellow/Red 阈值推荐；机器可读版见同目录")
    lines.append("> `seed_thresholds.yaml`。")
    lines.append("")

    # ---- 场景分布 ----
    lines.append("## 场景样本分布")
    lines.append("")
    lines.append("| Scene | Chapters | 占比 |")
    lines.append("|-------|----------|------|")
    for scene in _SCENE_ORDER:
        n = scene_counts.get(scene, 0)
        pct = f"{n * 100 / total:.1f}%" if total else "0%"
        lines.append(f"| {scene} | {n} | {pct} |")
    lines.append("")
    if scene_counts.get("combat", 0) == 0:
        lines.append(
            f"> _combat 场景 0 样本：US-001 启发式无法从 `ch###.txt` 文件名"
            f"识别战斗标题，运行期将继承 `{_COMBAT_FALLBACK_SCENE}` 阈值（"
            "快节奏高激活区，直白诉求同向）。_"
        )
        lines.append("")

    # ---- 5 维度分布 ----
    lines.append("## 每场景 5 维度百分位")
    lines.append("")
    for scene in _SCENE_ORDER:
        stats = scene_stats.get(scene, {})
        n = scene_counts.get(scene, 0)
        lines.append(f"### {scene} (n={n})")
        lines.append("")
        if n == 0:
            lines.append(
                f"> _样本为空_——阈值继承自 `{_COMBAT_FALLBACK_SCENE}`。"
            )
            lines.append("")
            continue
        lines.append("| Metric | P25 | P50 | P75 | min | max |")
        lines.append("|--------|-----|-----|-----|-----|-----|")
        for name in _METRIC_NAMES:
            p = stats.get(name, {})
            label = _METRIC_LABELS[name]
            lines.append(
                f"| {label} | {p.get('p25', 0.0):.4f} | {p.get('p50', 0.0):.4f} | "
                f"{p.get('p75', 0.0):.4f} | {p.get('min', 0.0):.4f} | "
                f"{p.get('max', 0.0):.4f} |"
            )
        lines.append("")

    # ---- 阈值推荐 ----
    lines.append("## 推荐阈值（directness-checker 消费）")
    lines.append("")
    lines.append("评分规则（映射到 PRD US-005 的 0-10 分制）：")
    lines.append("")
    lines.append("- **lower_is_better**（D1 / D2 / D3 / D5）：")
    lines.append("  `value ≤ P50` → Green（score ≥ 8）；")
    lines.append("  `P50 < value ≤ P75` → Yellow（6 ≤ score < 8）；")
    lines.append("  `value > P75` → Red（score < 6，触发重写）。")
    lines.append("- **mid_is_better**（D4 句长）：`[P25, P75]` → Green；")
    lines.append("  外扩 1 个 IQR → Yellow；更远 → Red。")
    lines.append("")

    for scene in _SCENE_ORDER:
        n = scene_counts.get(scene, 0)
        if n == 0:
            continue
        th = thresholds.get(scene, {})
        if not th:
            continue
        lines.append(f"### {scene}")
        lines.append("")
        lines.append("| Metric | Green | Yellow | Red |")
        lines.append("|--------|-------|--------|-----|")
        for name in _METRIC_NAMES:
            t = th.get(name, {})
            if t.get("direction") == "lower_is_better":
                green = f"≤ {t.get('green_max', 0.0):.4f}"
                yellow = f"≤ {t.get('yellow_max', 0.0):.4f}"
                red = f"> {t.get('red_min', 0.0):.4f}"
            else:
                green = (
                    f"[{t.get('green_low', 0.0):.2f}, "
                    f"{t.get('green_high', 0.0):.2f}]"
                )
                yellow = (
                    f"[{t.get('yellow_low', 0.0):.2f}, "
                    f"{t.get('yellow_high', 0.0):.2f}]"
                )
                red = "outside yellow band"
            lines.append(f"| {_METRIC_LABELS[name]} | {green} | {yellow} | {red} |")
        lines.append("")

    # ---- 代码常量块（供 US-005 导入） ----
    lines.append("## 推荐 checker 阈值常量（Python 风格，示例）")
    lines.append("")
    lines.append("```python")
    lines.append("# 黄金三章 + 战斗/高潮/爽点场景；directness-checker 可 import")
    gt = thresholds.get("golden_three", {})
    for name in _METRIC_NAMES:
        t = gt.get(name, {})
        const_base = _METRIC_CONST_NAMES[name]
        if t.get("direction") == "lower_is_better":
            lines.append(f"{const_base} = {t.get('green_max', 0.0):.4f}  # P50 → Green upper bound")
            lines.append(
                f"{const_base.replace('_MAX', '')}_RED = {t.get('red_min', 0.0):.4f}"
                "  # P75 → Red lower bound"
            )
        else:
            lines.append(
                f"{const_base}_GREEN_LOW = {t.get('green_low', 0.0):.2f}  # P25"
            )
            lines.append(
                f"{const_base}_GREEN_HIGH = {t.get('green_high', 0.0):.2f}  # P75"
            )
    lines.append("```")
    lines.append("")

    # ---- 跨书对比 ----
    lines.append("## 跨书对比（D1 修辞 + D3 抽象词 均值）")
    lines.append("")
    book_means = compute_book_means(records)
    if book_means:
        cleanest = book_means[:5]
        ornate = list(reversed(book_means[-5:]))
        lines.append("### 最直白 Top 5")
        lines.append("")
        lines.append("| Book | D1+D3 mean |")
        lines.append("|------|-----------|")
        for b, s in cleanest:
            lines.append(f"| {b} | {s:.4f} |")
        lines.append("")
        lines.append("### 最华丽 Top 5")
        lines.append("")
        lines.append("| Book | D1+D3 mean |")
        lines.append("|------|-----------|")
        for b, s in ornate:
            lines.append(f"| {b} | {s:.4f} |")
        lines.append("")

    lines.append("## 机器可读输出")
    lines.append("")
    lines.append(
        "同目录 `seed_thresholds.yaml` 包含完整 percentile 与阈值常量，"
        "供 US-005 directness-checker / US-010 现有 checker 微调消费。"
    )
    lines.append("")
    return "\n".join(lines)


def render_yaml(
    scene_stats: dict[str, dict[str, dict[str, float]]],
    thresholds: dict[str, dict[str, dict[str, Any]]],
    scene_counts: dict[str, int],
    *,
    generated: str,
    source: str,
) -> str:
    """不依赖 PyYAML，手写稳定 YAML（字段顺序固定，便于 diff review）。"""
    lines: list[str] = []
    lines.append("# Prose Directness seed thresholds (generated by US-002)")
    lines.append("# 每次重跑 scripts/gen_directness_baseline_report.py 覆盖本文件。")
    lines.append("version: 1")
    lines.append(f"generated: '{generated}'")
    lines.append(f"source: '{source}'")
    lines.append(f"combat_fallback_scene: '{_COMBAT_FALLBACK_SCENE}'")
    lines.append("scenes:")
    for scene in _SCENE_ORDER:
        n = scene_counts.get(scene, 0)
        lines.append(f"  {scene}:")
        lines.append(f"    n: {n}")
        if n == 0:
            lines.append(f"    inherits_from: {_COMBAT_FALLBACK_SCENE}")
            continue
        lines.append("    percentiles:")
        scene_block = scene_stats.get(scene, {})
        for name in _METRIC_NAMES:
            p = scene_block.get(name, {})
            lines.append(f"      {name}:")
            lines.append(f"        n: {int(p.get('n', 0))}")
            lines.append(f"        min: {p.get('min', 0.0):.4f}")
            lines.append(f"        p25: {p.get('p25', 0.0):.4f}")
            lines.append(f"        p50: {p.get('p50', 0.0):.4f}")
            lines.append(f"        p75: {p.get('p75', 0.0):.4f}")
            lines.append(f"        max: {p.get('max', 0.0):.4f}")
        lines.append("    thresholds:")
        th_block = thresholds.get(scene, {})
        for name in _METRIC_NAMES:
            t = th_block.get(name, {})
            lines.append(f"      {name}:")
            lines.append(f"        direction: {t.get('direction', 'lower_is_better')}")
            if t.get("direction") == "lower_is_better":
                lines.append(f"        green_max: {t.get('green_max', 0.0):.4f}")
                lines.append(f"        yellow_max: {t.get('yellow_max', 0.0):.4f}")
                lines.append(f"        red_min: {t.get('red_min', 0.0):.4f}")
            else:
                lines.append(f"        green_low: {t.get('green_low', 0.0):.4f}")
                lines.append(f"        green_high: {t.get('green_high', 0.0):.4f}")
                lines.append(f"        yellow_low: {t.get('yellow_low', 0.0):.4f}")
                lines.append(f"        yellow_high: {t.get('yellow_high', 0.0):.4f}")
    lines.append("")
    return "\n".join(lines)


def generate_reports(
    stats_path: Path,
    markdown_path: Path,
    yaml_path: Path,
    *,
    generated: str | None = None,
) -> tuple[Path, Path]:
    """加载 stats.json，写入 markdown + yaml，返回两个最终路径。"""
    records = load_records(stats_path)
    buckets = bucket_by_scene(records)

    scene_stats: dict[str, dict[str, dict[str, float]]] = {}
    thresholds: dict[str, dict[str, dict[str, Any]]] = {}
    scene_counts: dict[str, int] = {scene: 0 for scene in _SCENE_ORDER}
    for scene in _SCENE_ORDER:
        inner = buckets.get(scene, {})
        sample_count = max(
            (len(inner.get(name, [])) for name in _METRIC_NAMES),
            default=0,
        )
        scene_counts[scene] = sample_count
        if sample_count == 0:
            continue
        pcts = compute_scene_percentiles(inner)
        scene_stats[scene] = pcts
        thresholds[scene] = recommend_thresholds(pcts)

    gen = generated or date.today().isoformat()
    md = render_markdown(
        records,
        scene_counts,
        scene_stats,
        thresholds,
        generated=gen,
        source=stats_path,
    )
    yml = render_yaml(
        scene_stats,
        thresholds,
        scene_counts,
        generated=gen,
        source=str(stats_path),
    )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(md, encoding="utf-8")
    yaml_path.write_text(yml, encoding="utf-8")
    return markdown_path, yaml_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--stats",
        type=Path,
        default=Path("reports/prose-directness-stats.json"),
        help="US-001 产出的 JSONL stats 文件（每行一条章节记录）",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=Path("reports/prose-directness-baseline.md"),
        help="输出人类可读 Markdown 报告",
    )
    parser.add_argument(
        "--yaml",
        type=Path,
        default=Path("reports/seed_thresholds.yaml"),
        help="输出机器可读阈值 YAML（供 US-005 checker 消费）",
    )
    parser.add_argument(
        "--generated",
        type=str,
        default=None,
        help="生成日期（ISO 8601）；缺省用今日",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    md, yml = generate_reports(
        args.stats,
        args.markdown,
        args.yaml,
        generated=args.generated,
    )
    print(f"gen_directness_baseline_report: wrote {md} + {yml}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
