#!/usr/bin/env python3
"""
ink-writer benchmark — 差距分析报告生成器
对比 ink-writer 产出与标杆语料的统计和Craft差距。

用法:
    python3 benchmark/compare.py \
      --benchmark benchmark/style_benchmark.json \
      --craft benchmark/craft_lessons/ \
      --inkwriter "/path/to/inkwriter/chapters/" \
      --output benchmark/gap_analysis.md
"""

import argparse
import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from stat_analyzer import analyze_chapter


def load_benchmark(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def analyze_inkwriter_chapters(chapter_dir: pathlib.Path) -> dict:
    """分析ink-writer产出的统计数据"""
    # 支持 .md 和 .txt 文件
    files = sorted(chapter_dir.glob("*.md")) or sorted(chapter_dir.glob("*.txt"))
    if not files:
        return {}

    all_stats = []
    for f in files[:30]:  # 最多分析30章
        text = f.read_text(encoding="utf-8")
        stats = analyze_chapter(text)
        if stats:
            all_stats.append(stats)

    if not all_stats:
        return {}

    # 计算均值
    numeric_keys = [k for k in all_stats[0] if isinstance(all_stats[0].get(k), (int, float))]
    averages = {}
    for key in numeric_keys:
        values = [s[key] for s in all_stats if key in s]
        if values:
            averages[key] = round(sum(values) / len(values), 4)

    return {
        "chapters_analyzed": len(all_stats),
        "averages": averages,
    }


def generate_gap_report(benchmark: dict, ink_stats: dict, craft_dir: pathlib.Path | None) -> str:
    """生成差距分析报告"""
    bm = benchmark.get("overall", {})
    ink = ink_stats.get("averages", {})

    report = []
    report.append("# ink-writer vs 标杆小说 — 差距分析报告\n")
    report.append(f"> 标杆: {benchmark.get('metadata', {}).get('total_books', '?')}本, "
                  f"{benchmark.get('metadata', {}).get('total_chapters', '?')}章\n")
    report.append(f"> ink-writer: {ink_stats.get('chapters_analyzed', '?')}章分析\n")

    # === 1. 统计差距 ===
    report.append("\n## 1. 统计差距\n")
    report.append("| 指标 | 标杆 | ink-writer | 差距 | 诊断 |")
    report.append("|------|------|-----------|------|------|")

    stat_diagnostics = {
        "sentence_length_mean": ("句长均值", "过短=句子碎片化，过长=AI说教感"),
        "sentence_length_variance_coeff": ("句长方差系数", "过低=AI均匀化，过高=过度插短句"),
        "short_sentence_ratio": ("短句占比(≤8字)", "过高=反AI规则过度执行"),
        "long_sentence_ratio": ("长句占比(≥35字)", "过低=缺乏节奏纵深"),
        "paragraph_length_mean": ("段落均长", ""),
        "dialogue_ratio": ("对话占比", "过低=缺乏角色互动"),
        "exclamation_density": ("感叹号密度(/千字)", "过低=情感表达匮乏"),
        "question_density": ("问号密度(/千字)", "过低=缺乏好奇心驱动"),
        "ellipsis_density": ("省略号密度(/千字)", "过低=缺乏戏剧停顿"),
        "sensory_word_density": ("感官词密度", "过低=场景不够沉浸"),
        "ai_word_density": ("AI高频词密度", "过高=AI味重"),
        "colloquial_ratio": ("口语词占比", "过低=语言过于正式/书面"),
    }

    critical_gaps = []  # 收集重大差距

    for key, (label, diag_hint) in stat_diagnostics.items():
        bm_val = bm.get(key, 0)
        ink_val = ink.get(key, 0)

        if bm_val != 0:
            diff_pct = (ink_val - bm_val) / abs(bm_val) * 100
        else:
            diff_pct = 0

        # 判断严重程度
        severity = ""
        if abs(diff_pct) > 50:
            severity = "⚠️ 严重"
            critical_gaps.append((label, bm_val, ink_val, diff_pct, diag_hint))
        elif abs(diff_pct) > 25:
            severity = "⚡ 偏离"

        diag = f"{severity} {diag_hint}" if severity else ""
        report.append(f"| {label} | {bm_val:.4f} | {ink_val:.4f} | {diff_pct:+.1f}% | {diag} |")

    # === 2. 关键差距诊断 ===
    report.append("\n## 2. 关键差距诊断\n")
    if critical_gaps:
        for label, bm_val, ink_val, diff_pct, diag in critical_gaps:
            report.append(f"### ⚠️ {label}: {diff_pct:+.1f}%")
            report.append(f"- 标杆值: {bm_val:.4f}")
            report.append(f"- ink-writer: {ink_val:.4f}")
            if diag:
                report.append(f"- 诊断: {diag}")
            report.append("")
    else:
        report.append("无严重差距。\n")

    # === 3. Craft差距 ===
    report.append("\n## 3. Craft差距（来自LLM分析）\n")
    if craft_dir and craft_dir.exists():
        for f in sorted(craft_dir.glob("*.md")):
            content = f.read_text(encoding="utf-8")
            # 提取与ink-writer对比的部分
            if "银针" in content or "ink-writer" in content or "差异" in content:
                report.append(f"### {f.stem}\n")
                # 简化：取前2000字
                report.append(content[:2000])
                report.append("\n")
    else:
        report.append("*Craft分析尚未完成，请运行 craft 分析后重新生成此报告。*\n")

    # === 4. 改进优先级 ===
    report.append("\n## 4. 改进优先级排序\n")
    report.append("基于差距大小和对过审影响排序：\n")

    priorities = []
    if critical_gaps:
        for i, (label, bm_val, ink_val, diff_pct, diag) in enumerate(
            sorted(critical_gaps, key=lambda x: -abs(x[3]))
        ):
            direction = "提高" if diff_pct < 0 else "降低"
            target = f"从 {ink_val:.4f} → {bm_val:.4f}"
            priorities.append(f"{i+1}. **{label}** — {direction} ({target})")
            if diag:
                priorities.append(f"   - 原因: {diag}")

    if priorities:
        report.extend(priorities)
    else:
        report.append("暂无基于统计的优先级建议。")

    # === 5. 具体改进建议 ===
    report.append("\n\n## 5. 具体改进建议\n")

    # 基于统计差距生成具体建议
    suggestions = []
    ink_sent_mean = ink.get("sentence_length_mean", 0)
    bm_sent_mean = bm.get("sentence_length_mean", 0)
    if ink_sent_mean > 0 and bm_sent_mean > 0:
        if ink_sent_mean < bm_sent_mean * 0.7:
            suggestions.append(
                "### 句长过短\n"
                f"ink-writer句长均值 {ink_sent_mean:.1f} 远低于标杆 {bm_sent_mean:.1f}。\n"
                "**建议**: 废除 anti-detection-writing.md 中\"每5句插短句\"的规则。"
                "让句长由叙事需要自然决定，而非人为切割。\n"
                "**对应任务**: T4.1 (重写anti-detection-writing.md)"
            )

    ink_short = ink.get("short_sentence_ratio", 0)
    bm_short = bm.get("short_sentence_ratio", 0)
    if ink_short > bm_short * 2:
        suggestions.append(
            "### 短句过多\n"
            f"ink-writer短句占比 {ink_short:.1%} 是标杆 {bm_short:.1%} 的{ink_short/bm_short:.1f}倍。\n"
            "**建议**: 短句应只在需要冲击力时使用，不应作为反AI手段机械插入。\n"
            "**对应任务**: T4.1 (重写anti-detection-writing.md)"
        )

    ink_excl = ink.get("exclamation_density", 0)
    bm_excl = bm.get("exclamation_density", 0)
    if ink_excl < bm_excl * 0.3:
        suggestions.append(
            "### 感叹号严重不足\n"
            f"ink-writer感叹号密度 {ink_excl:.2f}/千字 远低于标杆 {bm_excl:.2f}/千字。\n"
            "**建议**: 角色说话和内心感叹时自然使用感叹号。网文读者期待情感外化。\n"
            "**对应任务**: T2.1 (writer-agent prompt重构)"
        )

    if suggestions:
        report.extend(suggestions)
    else:
        report.append("*暂无基于统计的具体建议。*")

    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description="差距分析报告生成器")
    parser.add_argument("--benchmark", required=True, help="标杆统计基线JSON")
    parser.add_argument("--craft", default=None, help="Craft分析结果目录")
    parser.add_argument("--inkwriter", required=True, help="ink-writer产出目录")
    parser.add_argument("--output", default="benchmark/gap_analysis.md", help="输出报告路径")
    args = parser.parse_args()

    # 加载标杆数据
    benchmark = load_benchmark(pathlib.Path(args.benchmark))

    # 分析ink-writer产出
    print("分析ink-writer产出...")
    ink_stats = analyze_inkwriter_chapters(pathlib.Path(args.inkwriter))
    print(f"  分析了 {ink_stats.get('chapters_analyzed', 0)} 章")

    # 生成报告
    craft_dir = pathlib.Path(args.craft) if args.craft else None
    report = generate_gap_report(benchmark, ink_stats, craft_dir)

    # 保存
    output_path = pathlib.Path(args.output)
    output_path.write_text(report, encoding="utf-8")
    print(f"差距报告已保存到: {output_path}")


if __name__ == "__main__":
    main()
