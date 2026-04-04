#!/usr/bin/env python3
"""
ink-writer benchmark — 统计层分析引擎
对标杆语料库进行多维量化分析，生成风格基线。

用法:
    python3 benchmark/stat_analyzer.py --input benchmark/corpus --output benchmark/style_benchmark.json
    python3 benchmark/stat_analyzer.py --input benchmark/corpus/夜无疆 --verbose   # 单本分析
    python3 benchmark/stat_analyzer.py --compare /path/to/inkwriter/chapters/      # 对比ink-writer产出
"""

import argparse
import json
import math
import pathlib
import re
import sys
from collections import Counter
from typing import Any

import jieba

# ============================================================
# 词表
# ============================================================

# AI高频词 — AI写作中异常高频出现的词汇
AI_HIGH_FREQ_WORDS = [
    "缓缓", "微微", "不由得", "不禁", "仿佛", "似乎",
    "默默", "淡淡", "轻轻", "静静", "悄悄",
    "一股", "一丝", "一抹", "一缕",
    "涌上心头", "划过嘴角", "掠过眼底", "闪过脑海",
    "深吸一口气", "紧紧攥住", "微不可察",
    "目光扫过", "目光落在", "眉头微皱", "嘴角微扬",
    "心中一动", "心中暗道", "心中不由",
    "显然", "毫无疑问", "不言而喻",
    "此刻", "这一刻", "那一刻", "刹那间",
    "意味深长", "若有所思", "恍然大悟",
]

# 五感词表 — 感官描写词汇
SENSORY_WORDS = {
    "视觉": ["看到", "望见", "瞥见", "瞧", "注视", "凝视", "目光", "眼前", "光", "暗",
             "色", "影", "闪", "亮", "黑", "白", "红", "绿", "蓝", "金", "银", "模糊", "清晰"],
    "听觉": ["听到", "听见", "声音", "响", "吼", "叫", "喊", "低语", "呢喃", "轰", "嗡",
             "嘶", "吱", "咔", "砰", "哗", "沙沙", "呜", "啸", "鸣", "寂静", "喧嚣"],
    "触觉": ["摸", "触", "碰", "冷", "热", "烫", "凉", "温", "疼", "痛", "麻", "痒",
             "滑", "粗糙", "柔软", "坚硬", "刺", "扎", "抓", "握", "搂"],
    "嗅觉": ["闻到", "气味", "香", "臭", "腥", "膻", "霉", "焦", "腐", "芬芳",
             "刺鼻", "清新"],
    "味觉": ["甜", "苦", "酸", "辣", "咸", "涩", "鲜", "腻", "淡", "浓",
             "吃", "尝", "咽", "嚼", "吞"],
}

# 口语词
COLLOQUIAL_WORDS = [
    "妈的", "他妈", "老子", "爷", "小子", "丫头", "家伙", "混蛋", "狗屁",
    "屁", "鬼", "死", "该死", "可恶", "哼", "呸", "嘿", "哟",
    "咋", "啥", "咱", "俺", "甭", "别", "得了", "算了", "行了",
    "特么", "卧槽", "牛逼", "厉害", "真的假的", "不是吧",
]

# ============================================================
# 分析函数
# ============================================================

def split_sentences(text: str) -> list[str]:
    """中文分句"""
    # 按句号、问号、感叹号、省略号分句
    sentences = re.split(r'[。！？…]+', text)
    return [s.strip() for s in sentences if s.strip() and len(s.strip()) > 1]


def split_paragraphs(text: str) -> list[str]:
    """分段"""
    paras = re.split(r'\n+', text)
    return [p.strip() for p in paras if p.strip()]


def is_dialogue(text: str) -> bool:
    """判断一段文本是否包含对话（支持所有中文引号变体）"""
    # Unicode中文引号: U+201C/U+201D (curly), U+300C/U+300D, U+300E/U+300F
    # 检查是否包含任何形式的引号
    return bool(re.search(r'[\u201c\u201d\u300c\u300d\u300e\u300f\u2018\u2019]', text))


def count_pattern(text: str, words: list[str]) -> int:
    """统计词列表在文本中的出现次数"""
    count = 0
    for word in words:
        count += text.count(word)
    return count


def analyze_chapter(text: str) -> dict:
    """分析单章的统计特征"""
    total_chars = len(text)
    if total_chars == 0:
        return {}

    # --- 句式分析 ---
    sentences = split_sentences(text)
    sent_lengths = [len(s) for s in sentences]
    sent_count = len(sent_lengths)

    if sent_count == 0:
        return {}

    sent_mean = sum(sent_lengths) / sent_count
    sent_var = sum((l - sent_mean) ** 2 for l in sent_lengths) / sent_count
    sent_std = math.sqrt(sent_var)
    sent_var_coeff = sent_std / sent_mean if sent_mean > 0 else 0

    short_count = sum(1 for l in sent_lengths if l <= 8)
    long_count = sum(1 for l in sent_lengths if l >= 35)

    # --- 段落分析 ---
    paragraphs = split_paragraphs(text)
    para_lengths = [len(p) for p in paragraphs]
    para_count = len(para_lengths)
    para_mean = sum(para_lengths) / para_count if para_count > 0 else 0

    dialogue_paras = sum(1 for p in paragraphs if is_dialogue(p))
    dialogue_ratio = dialogue_paras / para_count if para_count > 0 else 0

    # 单句段落占比
    single_sent_paras = sum(1 for p in paragraphs if len(split_sentences(p)) == 1)
    single_sent_ratio = single_sent_paras / para_count if para_count > 0 else 0

    # --- 标点分析 ---
    excl_count = text.count("！") + text.count("!")
    quest_count = text.count("？") + text.count("?")
    ellipsis_count = text.count("……") + text.count("...")

    per_1k = 1000 / total_chars if total_chars > 0 else 0

    # --- 词汇分析 ---
    words = list(jieba.cut(text))
    word_count = len(words)

    # 感官词密度
    sensory_total = 0
    sensory_by_type = {}
    all_sensory_words = []
    for sense_type, word_list in SENSORY_WORDS.items():
        count = count_pattern(text, word_list)
        sensory_by_type[sense_type] = count
        sensory_total += count
        all_sensory_words.extend(word_list)
    sensory_density = sensory_total / word_count if word_count > 0 else 0

    # AI高频词密度
    ai_word_count = count_pattern(text, AI_HIGH_FREQ_WORDS)
    ai_word_density = ai_word_count / word_count if word_count > 0 else 0

    # AI高频词逐个统计
    ai_word_detail = {}
    for w in AI_HIGH_FREQ_WORDS:
        c = text.count(w)
        if c > 0:
            ai_word_detail[w] = c

    # 口语词密度
    colloquial_count = count_pattern(text, COLLOQUIAL_WORDS)
    colloquial_ratio = colloquial_count / word_count if word_count > 0 else 0

    return {
        "total_chars": total_chars,
        "word_count": word_count,
        "sentence_count": sent_count,
        "paragraph_count": para_count,
        # 句式
        "sentence_length_mean": round(sent_mean, 2),
        "sentence_length_std": round(sent_std, 2),
        "sentence_length_variance_coeff": round(sent_var_coeff, 3),
        "short_sentence_ratio": round(short_count / sent_count, 3) if sent_count > 0 else 0,
        "long_sentence_ratio": round(long_count / sent_count, 3) if sent_count > 0 else 0,
        # 段落
        "paragraph_length_mean": round(para_mean, 2),
        "dialogue_ratio": round(dialogue_ratio, 3),
        "single_sentence_para_ratio": round(single_sent_ratio, 3),
        # 标点
        "exclamation_density": round(excl_count * per_1k, 4),
        "question_density": round(quest_count * per_1k, 4),
        "ellipsis_density": round(ellipsis_count * per_1k, 4),
        # 词汇
        "sensory_word_density": round(sensory_density, 4),
        "sensory_by_type": {k: v for k, v in sensory_by_type.items()},
        "ai_word_density": round(ai_word_density, 5),
        "ai_word_detail": ai_word_detail,
        "colloquial_ratio": round(colloquial_ratio, 5),
    }


def analyze_book(book_dir: pathlib.Path) -> dict:
    """分析一本书的所有章节，返回汇总统计"""
    ch_dir = book_dir / "chapters"
    if not ch_dir.exists():
        return {}

    chapters = sorted(ch_dir.glob("ch*.txt"))
    if not chapters:
        return {}

    all_stats = []
    for ch_file in chapters:
        text = ch_file.read_text(encoding="utf-8")
        stats = analyze_chapter(text)
        if stats:
            all_stats.append(stats)

    if not all_stats:
        return {}

    # 计算所有数值字段的均值
    numeric_keys = [
        "sentence_length_mean", "sentence_length_std", "sentence_length_variance_coeff",
        "short_sentence_ratio", "long_sentence_ratio",
        "paragraph_length_mean", "dialogue_ratio", "single_sentence_para_ratio",
        "exclamation_density", "question_density", "ellipsis_density",
        "sensory_word_density", "ai_word_density", "colloquial_ratio",
    ]

    averages = {}
    for key in numeric_keys:
        values = [s[key] for s in all_stats if key in s]
        if values:
            averages[key] = round(sum(values) / len(values), 4)

    # 汇总AI高频词
    ai_word_totals = Counter()
    total_words = sum(s.get("word_count", 0) for s in all_stats)
    for s in all_stats:
        for word, count in s.get("ai_word_detail", {}).items():
            ai_word_totals[word] += count

    ai_word_frequency = {}
    for word, count in ai_word_totals.most_common():
        ai_word_frequency[word] = round(count / total_words, 6) if total_words > 0 else 0

    # 汇总感官词
    sensory_totals = Counter()
    for s in all_stats:
        for sense_type, count in s.get("sensory_by_type", {}).items():
            sensory_totals[sense_type] += count

    # 加载元数据
    meta_path = book_dir / "metadata.json"
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

    return {
        "title": meta.get("title", book_dir.name),
        "author": meta.get("author", ""),
        "genre": meta.get("genre", ""),
        "chapters_analyzed": len(all_stats),
        "total_words_analyzed": total_words,
        "averages": averages,
        "ai_word_frequency": ai_word_frequency,
        "sensory_distribution": dict(sensory_totals),
    }


def aggregate_stats(book_stats: list[dict]) -> dict:
    """汇总多本书的统计，生成整体基线"""
    if not book_stats:
        return {}

    numeric_keys = [
        "sentence_length_mean", "sentence_length_std", "sentence_length_variance_coeff",
        "short_sentence_ratio", "long_sentence_ratio",
        "paragraph_length_mean", "dialogue_ratio", "single_sentence_para_ratio",
        "exclamation_density", "question_density", "ellipsis_density",
        "sensory_word_density", "ai_word_density", "colloquial_ratio",
    ]

    overall = {}
    for key in numeric_keys:
        values = [b["averages"][key] for b in book_stats if key in b.get("averages", {})]
        if values:
            overall[key] = round(sum(values) / len(values), 4)

    # 汇总AI高频词频率
    ai_freq_totals = Counter()
    ai_freq_counts = Counter()
    for b in book_stats:
        for word, freq in b.get("ai_word_frequency", {}).items():
            ai_freq_totals[word] += freq
            ai_freq_counts[word] += 1

    ai_word_frequency = {}
    for word in ai_freq_totals:
        ai_word_frequency[word] = round(ai_freq_totals[word] / ai_freq_counts[word], 6)

    # 按题材分组
    by_genre = {}
    for b in book_stats:
        genre = b.get("genre", "未知")
        if genre not in by_genre:
            by_genre[genre] = []
        by_genre[genre].append(b)

    genre_stats = {}
    for genre, books in by_genre.items():
        genre_overall = {}
        for key in numeric_keys:
            values = [b["averages"][key] for b in books if key in b.get("averages", {})]
            if values:
                genre_overall[key] = round(sum(values) / len(values), 4)
        genre_stats[genre] = {
            "book_count": len(books),
            **genre_overall,
        }

    # 按位置分组（前3章 vs 其他）
    # 这需要chapter级别数据，暂略

    return {
        "overall": overall,
        "by_genre": genre_stats,
        "ai_word_frequency": dict(sorted(ai_word_frequency.items(), key=lambda x: -x[1])),
        "metadata": {
            "total_books": len(book_stats),
            "total_chapters": sum(b.get("chapters_analyzed", 0) for b in book_stats),
            "total_words": sum(b.get("total_words_analyzed", 0) for b in book_stats),
        },
    }


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="标杆语料统计分析引擎")
    parser.add_argument("--input", required=True, help="语料库目录 或 单本书目录")
    parser.add_argument("--output", default=None, help="输出JSON文件路径")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    parser.add_argument("--compare", default=None, help="与ink-writer产出目录对比")
    args = parser.parse_args()

    input_path = pathlib.Path(args.input)

    # 判断是单本还是语料库
    if (input_path / "chapters").exists():
        # 单本书
        print(f"分析单本: {input_path.name}")
        stats = analyze_book(input_path)
        if args.verbose:
            print(json.dumps(stats, ensure_ascii=False, indent=2))
        if args.output:
            pathlib.Path(args.output).write_text(
                json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    else:
        # 语料库 — 分析所有书
        book_dirs = [d for d in input_path.iterdir()
                     if d.is_dir() and not d.name.startswith("_") and (d / "chapters").exists()]
        print(f"分析语料库: {len(book_dirs)} 本书")

        all_stats = []
        for book_dir in book_dirs:
            print(f"  分析: {book_dir.name}...", end=" ")
            stats = analyze_book(book_dir)
            if stats:
                all_stats.append(stats)
                print(f"✓ ({stats['chapters_analyzed']}章, {stats['total_words_analyzed']}字)")

                # 保存单本统计
                per_book_dir = input_path.parent / "per_book_stats"
                per_book_dir.mkdir(exist_ok=True)
                safe_name = re.sub(r'[<>:"/\\|?*]', '', book_dir.name)
                (per_book_dir / f"{safe_name}_stats.json").write_text(
                    json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            else:
                print("✗ (无有效数据)")

        # 汇总
        benchmark = aggregate_stats(all_stats)

        if args.verbose:
            print("\n=== 汇总统计 ===")
            print(json.dumps(benchmark, ensure_ascii=False, indent=2))

        output_path = args.output or str(input_path.parent / "style_benchmark.json")
        pathlib.Path(output_path).write_text(
            json.dumps(benchmark, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n基线统计已保存到: {output_path}")
        print(f"  书籍: {benchmark['metadata']['total_books']}")
        print(f"  章节: {benchmark['metadata']['total_chapters']}")
        print(f"  总字数: {benchmark['metadata']['total_words']}")

    # 对比模式
    if args.compare:
        compare_path = pathlib.Path(args.compare)
        print(f"\n=== 与ink-writer产出对比 ===")
        print(f"ink-writer目录: {compare_path}")
        # 分析ink-writer章节
        if compare_path.is_dir():
            txt_files = sorted(compare_path.glob("*.md")) or sorted(compare_path.glob("*.txt"))
            if txt_files:
                ink_stats_list = []
                for f in txt_files[:30]:
                    text = f.read_text(encoding="utf-8")
                    stats = analyze_chapter(text)
                    if stats:
                        ink_stats_list.append(stats)

                if ink_stats_list:
                    # 计算ink-writer均值
                    numeric_keys = list(ink_stats_list[0].keys())
                    numeric_keys = [k for k in numeric_keys if isinstance(ink_stats_list[0].get(k), (int, float))]

                    print(f"\n{'指标':<35} {'标杆':>10} {'ink-writer':>12} {'差距':>10}")
                    print("-" * 70)

                    benchmark_data = json.loads(pathlib.Path(output_path if args.output else str(input_path.parent / "style_benchmark.json")).read_text())
                    overall = benchmark_data.get("overall", {})

                    for key in numeric_keys:
                        bm_val = overall.get(key, 0)
                        ink_vals = [s[key] for s in ink_stats_list if key in s]
                        ink_val = sum(ink_vals) / len(ink_vals) if ink_vals else 0
                        diff = ink_val - bm_val
                        diff_pct = (diff / bm_val * 100) if bm_val != 0 else 0
                        print(f"{key:<35} {bm_val:>10.4f} {ink_val:>12.4f} {diff_pct:>+9.1f}%")


if __name__ == "__main__":
    main()
