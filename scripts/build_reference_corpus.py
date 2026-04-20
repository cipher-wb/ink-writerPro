#!/usr/bin/env python3
"""
build_reference_corpus.py - 从已爬取语料中筛选 Top-N 爆款建立标准对照集

从 benchmark/corpus/ 读取已有语料，按收藏量排序筛选 Top-N 本，
为每本生成 manifest.json，分析章节文本计算钩子密度和爽点密度，
最终输出 benchmark/reference_stats.json (P25/P50/P75 百分位)。

用法:
    python scripts/build_reference_corpus.py [--top N] [--min-chapters M]
"""

from __future__ import annotations

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio
_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    '../ink-writer/scripts',
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass
import argparse
import json
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
BENCHMARK_DIR = REPO_ROOT / "benchmark"
CORPUS_DIR = BENCHMARK_DIR / "corpus"
CORPUS_INDEX = BENCHMARK_DIR / "corpus_index.json"
REFERENCE_DIR = BENCHMARK_DIR / "reference_corpus"
REFERENCE_STATS = BENCHMARK_DIR / "reference_stats.json"

# US-006: 跨平台 symlink 兜底。统一走 runtime_compat.safe_symlink，
# 它在无 symlink 权限时自动 shutil.copyfile 降级并 WARNING 日志。
try:
    sys.path.insert(0, str(REPO_ROOT / "ink-writer" / "scripts"))
    from runtime_compat import safe_symlink as _safe_symlink  # type: ignore
except Exception:  # pragma: no cover
    def _safe_symlink(src, dst, **_kwargs) -> bool:  # type: ignore
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        if sys.platform != "win32":
            import os as _os
            _os.symlink(Path(src), Path(dst))
            return True
        shutil.copyfile(src, dst)
        return False


def _link_or_copy(src: Path, dst: Path) -> None:
    """Symlink when allowed, else copy. Idempotent (skips if dst exists)."""
    if dst.exists():
        return
    _safe_symlink(src.resolve(), dst)

DEFAULT_TOP_N = 50
DEFAULT_MIN_CHAPTERS = 10

HOOK_PATTERNS_CHAPTER_END = [
    r"究竟.{0,20}[？?]",
    r"到底.{0,20}[？?]",
    r"难道.{0,20}[？?]",
    r"这.{0,10}怎么可能",
    r"不可能[！!]",
    r"发生了什么",
    r"却[没不]想到",
    r"然而[，,]",
    r"可就在这时",
    r"突然[，,]",
    r"一道.{0,10}[声光影]",
    r"一个.{0,10}出现",
    r"来人[！!]",
    r"谁[！!？?]",
    r"你[！!]",
    r"[他她它].*?笑了",
    r"还没有结束",
    r"才刚刚开始",
    r"一切.*?改变",
    r"[他她].*?消失",
    r"下一刻",
    r"瞬间[，,]",
]

HOOK_PATTERNS_CHAPTER_OPEN = [
    r"^[^\n]{0,20}[！!]$",
    r"^[^\n]{0,10}[？?]$",
    r"[痛死危]",
    r"砰|轰|啪|咔",
    r"不[！!]",
    r"小心[！!]",
    r"快[跑走逃闪]",
]

HIGH_POINT_KEYWORDS = [
    "突破", "觉醒", "逆转", "震惊", "不可能", "碾压", "爆发",
    "释放", "终于", "成功", "晋级", "进阶", "领悟", "顿悟",
    "奇迹", "万众瞩目", "全场", "沸腾", "欢呼", "膜拜",
    "臣服", "跪", "震撼", "颤抖", "恐惧", "绝望", "崩溃",
    "认输", "求饶", "打脸", "扬眉吐气", "痛快", "畅快",
    "大获全胜", "一战成名", "威震", "名动", "惊天",
]


def load_corpus_index() -> list[dict]:
    if not CORPUS_INDEX.exists():
        return []
    with open(CORPUS_INDEX, encoding="utf-8") as f:
        return json.load(f)


def select_top_books(index: list[dict], top_n: int, min_chapters: int) -> list[dict]:
    eligible = [
        b for b in index
        if b.get("chapter_count", 0) >= min_chapters
        and b.get("collections", 0) > 0
    ]
    eligible.sort(key=lambda b: b.get("collections", 0), reverse=True)
    return eligible[:top_n]


def read_chapter_text(book_dir: Path, ch_num: int) -> str | None:
    candidates = [
        book_dir / "chapters" / f"ch{ch_num:03d}.txt",
        book_dir / "chapters" / f"ch{ch_num:02d}.txt",
        book_dir / "chapters" / f"chapter_{ch_num}.txt",
    ]
    for p in candidates:
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def analyze_chapter_hooks(text: str, is_opening: bool = False) -> dict:
    lines = text.strip().split("\n")
    tail_text = "\n".join(lines[-10:]) if len(lines) >= 10 else text
    head_text = "\n".join(lines[:5]) if len(lines) >= 5 else text

    end_hooks = 0
    for pat in HOOK_PATTERNS_CHAPTER_END:
        if re.search(pat, tail_text):
            end_hooks += 1

    open_hooks = 0
    if is_opening:
        for pat in HOOK_PATTERNS_CHAPTER_OPEN:
            if re.search(pat, head_text):
                open_hooks += 1

    return {"end_hooks": min(end_hooks, 5), "open_hooks": min(open_hooks, 3)}


def analyze_chapter_high_points(text: str) -> dict:
    word_count = len(text)
    if word_count == 0:
        return {"high_point_count": 0, "high_point_density": 0.0}

    count = 0
    for kw in HIGH_POINT_KEYWORDS:
        count += len(re.findall(re.escape(kw), text))

    density = count / (word_count / 1000)
    return {"high_point_count": count, "high_point_density": round(density, 4)}


def analyze_book(book_dir: Path, chapter_count: int) -> dict:
    actual_count = min(chapter_count, 30)
    hook_scores = []
    hp_densities = []

    for ch in range(1, actual_count + 1):
        text = read_chapter_text(book_dir, ch)
        if not text or len(text) < 200:
            continue

        hooks = analyze_chapter_hooks(text, is_opening=(ch == 1))
        total_hook_score = hooks["end_hooks"] + hooks["open_hooks"]
        hook_scores.append(total_hook_score)

        hp = analyze_chapter_high_points(text)
        hp_densities.append(hp["high_point_density"])

    if not hook_scores:
        return {"hook_density": 0.0, "high_point_density": 0.0, "chapters_analyzed": 0}

    return {
        "hook_density": round(mean(hook_scores), 4),
        "high_point_density": round(mean(hp_densities), 4),
        "chapters_analyzed": len(hook_scores),
    }


def compute_percentiles(values: list[float]) -> dict:
    if not values:
        return {"p25": 0.0, "p50": 0.0, "p75": 0.0, "min": 0.0, "max": 0.0, "mean": 0.0}
    s = sorted(values)
    n = len(s)

    def _percentile(p: float) -> float:
        k = (n - 1) * p
        f = int(k)
        c = f + 1
        if c >= n:
            return s[-1]
        return round(s[f] + (k - f) * (s[c] - s[f]), 4)

    return {
        "p25": _percentile(0.25),
        "p50": _percentile(0.50),
        "p75": _percentile(0.75),
        "min": round(s[0], 4),
        "max": round(s[-1], 4),
        "mean": round(mean(s), 4),
    }


def build_manifest(book: dict) -> dict:
    return {
        "book_id": book.get("book_id", ""),
        "title": book.get("title", ""),
        "author": book.get("author", ""),
        "source": "qidian_public_chapters",
        "genre": book.get("genre", ""),
        "chapters_count": book.get("chapter_count", 0),
        "collections": book.get("collections", 0),
        "license_note": "公开免费章节，仅用于内部质量对照研究",
    }


def build_reference_corpus(
    top_n: int = DEFAULT_TOP_N,
    min_chapters: int = DEFAULT_MIN_CHAPTERS,
) -> dict:
    index = load_corpus_index()
    if not index:
        raise FileNotFoundError(f"Corpus index not found: {CORPUS_INDEX}")

    selected = select_top_books(index, top_n, min_chapters)
    if len(selected) < 30:
        raise ValueError(
            f"Only {len(selected)} books meet criteria (need ≥30). "
            f"Lower min_chapters or add more books to corpus."
        )

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    hook_densities = []
    hp_densities = []
    book_stats = []

    for book in selected:
        book_dir = CORPUS_DIR / book["dir"]
        if not book_dir.exists():
            continue

        ref_book_dir = REFERENCE_DIR / book["dir"]
        ref_book_dir.mkdir(parents=True, exist_ok=True)

        manifest = build_manifest(book)
        manifest_path = ref_book_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        src_chapters = book_dir / "chapters"
        dst_chapters = ref_book_dir / "chapters"
        if src_chapters.exists():
            dst_chapters.mkdir(parents=True, exist_ok=True)
            for ch_file in sorted(src_chapters.glob("ch*.txt")):
                dst = dst_chapters / ch_file.name
                _link_or_copy(ch_file, dst)

        analysis = analyze_book(book_dir, book.get("chapter_count", 30))
        if analysis["chapters_analyzed"] > 0:
            hook_densities.append(analysis["hook_density"])
            hp_densities.append(analysis["high_point_density"])

        book_stats.append({
            "title": book["title"],
            "author": book["author"],
            "genre": book["genre"],
            "collections": book["collections"],
            **analysis,
        })

    stats = {
        "version": "1.0.0",
        "timestamp": datetime.now(UTC).isoformat(),
        "corpus_size": len(selected),
        "books_analyzed": len([s for s in book_stats if s["chapters_analyzed"] > 0]),
        "hook_density": compute_percentiles(hook_densities),
        "high_point_density": compute_percentiles(hp_densities),
        "per_book": book_stats,
    }

    with open(REFERENCE_STATS, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Build reference corpus from scraped data")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N, help="Top N books by collections")
    parser.add_argument("--min-chapters", type=int, default=DEFAULT_MIN_CHAPTERS, help="Min chapters per book")
    args = parser.parse_args()

    stats = build_reference_corpus(top_n=args.top, min_chapters=args.min_chapters)
    print(f"Reference corpus built: {stats['corpus_size']} books, {stats['books_analyzed']} analyzed")
    print(f"Hook density P75: {stats['hook_density']['p75']}")
    print(f"High-point density P75: {stats['high_point_density']['p75']}")
    print(f"Stats written to: {REFERENCE_STATS}")


if __name__ == "__main__":
    main()
