#!/usr/bin/env python3
"""
ink-writer benchmark — Craft 分析引擎
使用 Claude Code Agent 对标杆小说做深度写作技巧分析。

注意：此脚本不直接调用 API，而是生成分析 prompt 供 Claude Code Agent 使用。
分析结果由 Agent 输出后，手动或自动存入 craft_lessons/ 目录。

用法:
    # 生成分析prompt（供Agent使用）
    python3 benchmark/craft_analyzer.py --generate-prompts

    # 汇总已有的craft分析结果
    python3 benchmark/craft_analyzer.py --summarize

    # 生成对比分析prompt
    python3 benchmark/craft_analyzer.py --compare /path/to/inkwriter/chapters/
"""

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from config import BENCHMARK_DIR, CORPUS_DIR

CRAFT_LESSONS_DIR = BENCHMARK_DIR / "craft_lessons"
PER_BOOK_CRAFT_DIR = BENCHMARK_DIR / "per_book_craft"


def generate_opening_prompt(book_dir: pathlib.Path) -> str:
    """生成开篇分析prompt"""
    ch1_path = book_dir / "chapters" / "ch001.txt"
    if not ch1_path.exists():
        return ""

    meta_path = book_dir / "metadata.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    title = meta.get("title", book_dir.name)

    return f"""请分析《{title}》第1章的开篇技巧。

文件路径: {ch1_path}

分析维度：
1. 第1句话的钩子技巧（动作/危机/悬念/感官冲击？）
2. 前300字传递的关键信息
3. 编辑10秒扫读能感知什么
4. 场景构建技巧（世界观如何融入行动）
5. 角色建立技巧（人设标签如何确立）
6. 句式节奏特征

输出JSON格式：
{{
  "title": "{title}",
  "hook_technique": "描述钩子技巧",
  "first_sentence_analysis": "第1句分析",
  "info_in_300_chars": ["信息1", "信息2"],
  "10s_impression": "10秒印象评估",
  "worldbuilding_technique": "世界观展示技巧",
  "character_establishment": "角色建立技巧",
  "rhythm_features": "句式节奏特征",
  "reusable_principles": ["原则1", "原则2"]
}}"""


def generate_scene_prompt(book_dir: pathlib.Path, chapter_nums: list[int]) -> str:
    """生成场景分析prompt"""
    meta_path = book_dir / "metadata.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    title = meta.get("title", book_dir.name)

    ch_paths = []
    for n in chapter_nums:
        ch_path = book_dir / "chapters" / f"ch{n:03d}.txt"
        if ch_path.exists():
            ch_paths.append(str(ch_path))

    if not ch_paths:
        return ""

    return f"""请分析《{title}》第{chapter_nums}章的场景写作技巧。

文件路径: {', '.join(ch_paths)}

分析维度：
1. 对话技巧（角色声音区分、潜台词、动作插入）
2. 战斗/紧张场景技巧（节奏控制、感官聚焦、力量可视化）
3. 情感/氛围技巧（环境映射情绪、留白、内外差异）
4. 句式节奏分析（紧张vs日常场景的句式差异）

输出JSON格式：
{{
  "title": "{title}",
  "dialogue_techniques": ["技巧1", "技巧2"],
  "combat_techniques": ["技巧1", "技巧2"],
  "emotion_techniques": ["技巧1", "技巧2"],
  "rhythm_analysis": "节奏分析",
  "reusable_principles": ["原则1", "原则2"]
}}"""


def summarize_craft_lessons():
    """汇总所有craft分析结果"""
    if not CRAFT_LESSONS_DIR.exists():
        print("craft_lessons/ 目录不存在")
        return

    files = sorted(CRAFT_LESSONS_DIR.glob("*.md"))
    if not files:
        print("无craft lesson文件")
        return

    summary_parts = ["# Craft 分析汇总\n"]
    for f in files:
        content = f.read_text(encoding="utf-8")
        summary_parts.append(f"## {f.stem}\n\n{content}\n\n---\n")

    summary_path = BENCHMARK_DIR / "craft_lessons_summary.md"
    summary_path.write_text("\n".join(summary_parts), encoding="utf-8")
    print(f"汇总已保存到: {summary_path}")
    print(f"包含 {len(files)} 个主题文件")


def main():
    parser = argparse.ArgumentParser(description="Craft 分析引擎")
    parser.add_argument("--generate-prompts", action="store_true",
                        help="为所有标杆小说生成分析prompt")
    parser.add_argument("--summarize", action="store_true",
                        help="汇总已有的craft分析结果")
    parser.add_argument("--compare", type=str, default=None,
                        help="生成与ink-writer产出的对比prompt")
    args = parser.parse_args()

    CRAFT_LESSONS_DIR.mkdir(exist_ok=True)
    PER_BOOK_CRAFT_DIR.mkdir(exist_ok=True)

    if args.generate_prompts:
        book_dirs = [d for d in CORPUS_DIR.iterdir()
                     if d.is_dir() and not d.name.startswith("_")
                     and (d / "chapters").exists()]
        print(f"为 {len(book_dirs)} 本书生成分析prompt:\n")

        for book_dir in book_dirs:
            print(f"=== {book_dir.name} ===")
            print("\n--- 开篇分析 ---")
            print(generate_opening_prompt(book_dir))
            print("\n--- 场景分析 ---")
            print(generate_scene_prompt(book_dir, [5, 6, 7]))
            print("\n" + "=" * 60)

    elif args.summarize:
        summarize_craft_lessons()

    elif args.compare:
        print(f"对比目录: {args.compare}")
        print("请使用 Claude Code Agent 运行对比分析")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
