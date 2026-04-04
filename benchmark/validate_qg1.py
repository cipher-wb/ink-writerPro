#!/usr/bin/env python3
"""
ink-writer benchmark — QG1 质量门禁验证
验证 Phase 1 的所有产出是否达标。

用法:
    python3 benchmark/validate_qg1.py
"""

import json
import pathlib
import sys

BENCHMARK_DIR = pathlib.Path(__file__).parent
CORPUS_DIR = BENCHMARK_DIR / "corpus"
CORPUS_INDEX = BENCHMARK_DIR / "corpus_index.json"
STYLE_BENCHMARK = BENCHMARK_DIR / "style_benchmark.json"
CRAFT_LESSONS_DIR = BENCHMARK_DIR / "craft_lessons"
GAP_ANALYSIS = BENCHMARK_DIR / "gap_analysis.md"


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")
    return condition


def main():
    results = []

    print("=" * 60)
    print("QG1 质量门禁验证")
    print("=" * 60)

    # === Check 1: 语料库完整性 ===
    print("\n📚 Check 1: 语料库完整性")

    if not CORPUS_INDEX.exists():
        check("corpus_index.json 存在", False)
        results.append(False)
    else:
        index = json.loads(CORPUS_INDEX.read_text(encoding="utf-8"))
        book_count = len(index)
        genres = set(b.get("genre", "") for b in index)
        total_chapters = sum(b.get("chapter_count", 0) for b in index)

        results.append(check(
            f"书籍数量 ≥50",
            book_count >= 50,
            f"当前: {book_count}本"
        ))
        results.append(check(
            f"题材覆盖 ≥5",
            len(genres) >= 5,
            f"当前: {len(genres)}个 ({', '.join(genres)})"
        ))
        results.append(check(
            f"总章节 ≥500",
            total_chapters >= 500,
            f"当前: {total_chapters}章"
        ))

        # 检查每本书至少10章
        low_chapter_books = [b["title"] for b in index if b.get("chapter_count", 0) < 10]
        results.append(check(
            f"每本书 ≥10章",
            len(low_chapter_books) == 0,
            f"不足10章: {low_chapter_books[:5]}" if low_chapter_books else ""
        ))

    # === Check 2: 统计数据有效性 ===
    print("\n📊 Check 2: 统计数据有效性")

    if not STYLE_BENCHMARK.exists():
        check("style_benchmark.json 存在", False)
        results.append(False)
    else:
        benchmark = json.loads(STYLE_BENCHMARK.read_text(encoding="utf-8"))
        overall = benchmark.get("overall", {})
        by_genre = benchmark.get("by_genre", {})

        # 检查关键字段非空
        required_keys = [
            "sentence_length_mean", "sentence_length_std",
            "sentence_length_variance_coeff",
            "short_sentence_ratio", "long_sentence_ratio",
            "dialogue_ratio", "sensory_word_density",
            "ai_word_density",
        ]

        all_valid = True
        for key in required_keys:
            val = overall.get(key)
            if val is None or (isinstance(val, float) and val != val):  # NaN check
                all_valid = False
                print(f"         ⚠️ Missing or NaN: {key}")

        results.append(check("所有关键字段有效", all_valid))
        results.append(check(
            f"by_genre 覆盖 ≥5题材",
            len(by_genre) >= 5,
            f"当前: {len(by_genre)}个"
        ))

    # === Check 3: Craft分析质量 ===
    print("\n🎨 Check 3: Craft分析质量")

    if not CRAFT_LESSONS_DIR.exists():
        check("craft_lessons/ 目录存在", False)
        results.append(False)
    else:
        lesson_files = list(CRAFT_LESSONS_DIR.glob("*.md"))
        results.append(check(
            f"Craft文件 ≥6个",
            len(lesson_files) >= 6,
            f"当前: {len(lesson_files)}个"
        ))

        # 检查每个文件非空且有内容
        short_files = []
        for f in lesson_files:
            content = f.read_text(encoding="utf-8")
            if len(content) < 500:
                short_files.append(f.name)

        results.append(check(
            "所有Craft文件内容充实(>500字)",
            len(short_files) == 0,
            f"过短: {short_files}" if short_files else ""
        ))

    # === Check 4: 差距报告可用性 ===
    print("\n📋 Check 4: 差距报告可用性")

    if not GAP_ANALYSIS.exists():
        check("gap_analysis.md 存在", False)
        results.append(False)
    else:
        report = GAP_ANALYSIS.read_text(encoding="utf-8")
        results.append(check(
            "包含'统计差距'章节",
            "统计差距" in report
        ))
        results.append(check(
            "包含'改进优先级'章节",
            "改进优先级" in report
        ))
        results.append(check(
            "包含'改进建议'章节",
            "改进建议" in report
        ))
        results.append(check(
            "报告长度 >1000字",
            len(report) > 1000,
            f"当前: {len(report)}字"
        ))

    # === 汇总 ===
    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r)
    total = len(results)
    all_passed = all(results)
    status = "PASS ✅" if all_passed else "FAIL ❌"
    print(f"QG1 OVERALL: {status} ({passed}/{total} checks passed)")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
