#!/usr/bin/env python3
"""
Style RAG Builder — 从标杆语料库构建风格参考数据库

读取 corpus/ 下的标杆小说，切分为300-800字场景片段，
按 genre × scene_type × emotion 三维标注，计算风格指标，
输出到 style_rag.db (SQLite)。

用法:
    python benchmark/style_rag_builder.py --build              # 全量构建
    python benchmark/style_rag_builder.py --build --genre 玄幻  # 只构建某题材
    python benchmark/style_rag_builder.py --stats              # 查看统计
    python benchmark/style_rag_builder.py --query --scene-type 战斗 --emotion 紧张 --limit 3
"""

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
import hashlib
import json
import math
import pathlib
import re
import sqlite3
import sys
from collections import Counter
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from config import (
    CORPUS_DIR, CORPUS_INDEX, STYLE_RAG_DB,
    SCENE_TYPE_KEYWORDS, EMOTION_KEYWORDS,
    STYLE_RAG_MIN_FRAGMENT_WORDS, STYLE_RAG_MAX_FRAGMENT_WORDS,
    STYLE_RAG_MIN_QUALITY_SCORE,
)


# ============================================================
# 数据库
# ============================================================

def init_db(db_path: pathlib.Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS style_fragments (
            id TEXT PRIMARY KEY,
            book_title TEXT NOT NULL,
            book_genre TEXT NOT NULL,
            chapter_num INTEGER NOT NULL,
            scene_index INTEGER NOT NULL,
            scene_type TEXT NOT NULL,
            emotion TEXT NOT NULL,
            content TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            avg_sentence_length REAL,
            short_sentence_ratio REAL,
            long_sentence_ratio REAL,
            dialogue_ratio REAL,
            exclamation_density REAL,
            ellipsis_density REAL,
            question_density REAL,
            quality_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_genre_scene ON style_fragments(book_genre, scene_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emotion ON style_fragments(emotion)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_quality ON style_fragments(quality_score DESC)")
    conn.commit()
    return conn


# ============================================================
# 文本分析
# ============================================================

def split_sentences(text: str) -> list[str]:
    parts = re.split(r'[。！？…]+', text)
    return [p.strip() for p in parts if p.strip() and len(p.strip()) > 1]


def compute_style_metrics(text: str) -> dict[str, float]:
    compact = re.sub(r'\s+', '', text)
    length = len(compact)
    if length < 50:
        return {}

    sentences = split_sentences(text)
    sent_lengths = [len(re.sub(r'\s+', '', s)) for s in sentences]
    sent_count = len(sent_lengths)
    if sent_count == 0:
        return {}

    avg_sent_len = sum(sent_lengths) / sent_count
    short_ratio = sum(1 for l in sent_lengths if l <= 8) / sent_count
    long_ratio = sum(1 for l in sent_lengths if l >= 35) / sent_count

    # 对话占比
    dialogue_matches = re.findall(r'\u201c[^\u201d]*\u201d', text)
    dialogue_chars = sum(len(re.sub(r'\s+', '', m)) - 2 for m in dialogue_matches)
    dialogue_ratio = dialogue_chars / max(1, length)

    # 标点密度
    k = length / 1000
    excl = (text.count('！') + text.count('!')) / max(0.1, k)
    ellip = (text.count('……') + text.count('...') + text.count('…')) / max(0.1, k)
    quest = (text.count('？') + text.count('?')) / max(0.1, k)

    return {
        "avg_sentence_length": round(avg_sent_len, 2),
        "short_sentence_ratio": round(short_ratio, 4),
        "long_sentence_ratio": round(long_ratio, 4),
        "dialogue_ratio": round(dialogue_ratio, 4),
        "exclamation_density": round(excl, 2),
        "ellipsis_density": round(ellip, 2),
        "question_density": round(quest, 2),
    }


def compute_quality_score(metrics: dict[str, float]) -> float:
    """基于与标杆均值的接近度计算质量分 (0-1)"""
    # 标杆均值（来自 gap_analysis.md）
    benchmarks = {
        "avg_sentence_length": 28.6,
        "short_sentence_ratio": 0.134,
        "long_sentence_ratio": 0.301,
        "dialogue_ratio": 0.345,
        "exclamation_density": 3.80,
        "ellipsis_density": 2.83,
        "question_density": 4.19,
    }

    score = 1.0
    for key, target in benchmarks.items():
        val = metrics.get(key, 0)
        if target > 0:
            deviation = abs(val - target) / target
            penalty = min(0.15, deviation * 0.1)
            score -= penalty

    return round(max(0.0, score), 4)


# ============================================================
# 片段切分与标注
# ============================================================

def split_into_fragments(text: str, min_words: int, max_words: int) -> list[str]:
    """按双换行+场景切换词切分章节为片段"""
    # 先按双换行分段
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    if not paragraphs:
        return []

    fragments = []
    current = []
    current_len = 0

    scene_switch_patterns = re.compile(
        r'^(与此同时|另一边|此刻|而在|回到|不远处|就在这时|当|翌日|次日|几天后|夜幕|天亮)'
    )

    for para in paragraphs:
        para_len = len(re.sub(r'\s+', '', para))

        # 检测场景切换
        is_switch = bool(scene_switch_patterns.match(para))

        if is_switch and current_len >= min_words:
            fragments.append('\n\n'.join(current))
            current = [para]
            current_len = para_len
        elif current_len + para_len > max_words and current_len >= min_words:
            fragments.append('\n\n'.join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len

    if current and current_len >= min_words:
        fragments.append('\n\n'.join(current))

    return fragments


def classify_scene_type(text: str) -> str:
    scores: dict[str, int] = {}
    for scene_type, keywords in SCENE_TYPE_KEYWORDS.items():
        scores[scene_type] = sum(text.count(kw) for kw in keywords)

    if not scores or max(scores.values()) == 0:
        return "日常"

    return max(scores, key=scores.get)


def classify_emotion(text: str) -> str:
    scores: dict[str, int] = {}
    for emotion, keywords in EMOTION_KEYWORDS.items():
        scores[emotion] = sum(text.count(kw) for kw in keywords)

    if not scores or max(scores.values()) == 0:
        return "轻松"

    return max(scores, key=scores.get)


def fragment_id(book_title: str, chapter_num: int, scene_index: int) -> str:
    raw = f"{book_title}:ch{chapter_num}:s{scene_index}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ============================================================
# 主流程
# ============================================================

def build_style_rag(genre_filter: str | None = None, verbose: bool = False):
    if not CORPUS_INDEX.exists():
        print("ERROR: corpus_index.json 不存在，请先运行 scraper.py")
        return

    index = json.loads(CORPUS_INDEX.read_text(encoding="utf-8"))
    if genre_filter:
        index = [b for b in index if genre_filter in (b.get("genre", "") or "")]
        print(f"过滤题材 '{genre_filter}': {len(index)} 本")

    conn = init_db(STYLE_RAG_DB)

    total_fragments = 0
    total_filtered = 0

    for book_entry in index:
        title = book_entry.get("title", "")
        genre = book_entry.get("genre", "未知")
        dir_name = book_entry.get("dir", "")
        book_dir = CORPUS_DIR / dir_name

        if not book_dir.exists():
            continue

        ch_dir = book_dir / "chapters"
        if not ch_dir.exists():
            continue

        ch_files = sorted(ch_dir.glob("ch*.txt"))
        if not ch_files:
            continue

        book_fragments = 0

        for ch_file in ch_files:
            ch_num_match = re.search(r'ch(\d+)', ch_file.name)
            ch_num = int(ch_num_match.group(1)) if ch_num_match else 0

            text = ch_file.read_text(encoding="utf-8")
            fragments = split_into_fragments(
                text,
                STYLE_RAG_MIN_FRAGMENT_WORDS,
                STYLE_RAG_MAX_FRAGMENT_WORDS,
            )

            for i, frag in enumerate(fragments):
                metrics = compute_style_metrics(frag)
                if not metrics:
                    continue

                quality = compute_quality_score(metrics)
                if quality < STYLE_RAG_MIN_QUALITY_SCORE:
                    total_filtered += 1
                    continue

                scene_type = classify_scene_type(frag)
                emotion = classify_emotion(frag)
                frag_word_count = len(re.sub(r'\s+', '', frag))
                fid = fragment_id(title, ch_num, i)

                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO style_fragments
                        (id, book_title, book_genre, chapter_num, scene_index,
                         scene_type, emotion, content, word_count,
                         avg_sentence_length, short_sentence_ratio, long_sentence_ratio,
                         dialogue_ratio, exclamation_density, ellipsis_density,
                         question_density, quality_score)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        fid, title, genre, ch_num, i,
                        scene_type, emotion, frag, frag_word_count,
                        metrics["avg_sentence_length"],
                        metrics["short_sentence_ratio"],
                        metrics["long_sentence_ratio"],
                        metrics["dialogue_ratio"],
                        metrics["exclamation_density"],
                        metrics["ellipsis_density"],
                        metrics["question_density"],
                        quality,
                    ))
                    book_fragments += 1
                    total_fragments += 1
                except sqlite3.Error as e:
                    if verbose:
                        print(f"    DB error: {e}")

        if verbose or book_fragments > 0:
            print(f"  {title}: {book_fragments} 片段")

        # 批量提交
        conn.commit()

    conn.close()
    print(f"\n构建完成:")
    print(f"  总片段: {total_fragments}")
    print(f"  过滤掉: {total_filtered} (质量分 < {STYLE_RAG_MIN_QUALITY_SCORE})")
    print(f"  数据库: {STYLE_RAG_DB}")


def show_stats():
    if not STYLE_RAG_DB.exists():
        print("style_rag.db 不存在，请先运行 --build")
        return

    conn = sqlite3.connect(str(STYLE_RAG_DB))

    total = conn.execute("SELECT COUNT(*) FROM style_fragments").fetchone()[0]
    print(f"总片段: {total}")

    print("\n按题材:")
    for row in conn.execute("SELECT book_genre, COUNT(*) FROM style_fragments GROUP BY book_genre ORDER BY COUNT(*) DESC"):
        print(f"  {row[0]}: {row[1]}")

    print("\n按场景类型:")
    for row in conn.execute("SELECT scene_type, COUNT(*) FROM style_fragments GROUP BY scene_type ORDER BY COUNT(*) DESC"):
        print(f"  {row[0]}: {row[1]}")

    print("\n按情绪:")
    for row in conn.execute("SELECT emotion, COUNT(*) FROM style_fragments GROUP BY emotion ORDER BY COUNT(*) DESC"):
        print(f"  {row[0]}: {row[1]}")

    print("\n风格指标均值:")
    row = conn.execute("""
        SELECT AVG(avg_sentence_length), AVG(short_sentence_ratio), AVG(long_sentence_ratio),
               AVG(dialogue_ratio), AVG(exclamation_density), AVG(quality_score)
        FROM style_fragments
    """).fetchone()
    print(f"  句长均值: {row[0]:.1f}字")
    print(f"  短句占比: {row[1]:.1%}")
    print(f"  长句占比: {row[2]:.1%}")
    print(f"  对话占比: {row[3]:.1%}")
    print(f"  感叹号密度: {row[4]:.1f}/千字")
    print(f"  质量均分: {row[5]:.3f}")

    conn.close()


def query_fragments(
    scene_type: str | None = None,
    emotion: str | None = None,
    genre: str | None = None,
    limit: int = 3,
):
    if not STYLE_RAG_DB.exists():
        print("style_rag.db 不存在，请先运行 --build")
        return

    conn = sqlite3.connect(str(STYLE_RAG_DB))

    where_clauses = []
    params = []
    if scene_type:
        where_clauses.append("scene_type = ?")
        params.append(scene_type)
    if emotion:
        where_clauses.append("emotion = ?")
        params.append(emotion)
    if genre:
        where_clauses.append("book_genre LIKE ?")
        params.append(f"%{genre}%")

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    params.append(limit)

    rows = conn.execute(f"""
        SELECT book_title, book_genre, chapter_num, scene_type, emotion,
               content, word_count, avg_sentence_length, dialogue_ratio,
               exclamation_density, quality_score
        FROM style_fragments
        WHERE {where_sql}
        ORDER BY quality_score DESC
        LIMIT ?
    """, params).fetchall()

    if not rows:
        print("未找到匹配的片段")
        return

    results = []
    for row in rows:
        result = {
            "book_title": row[0],
            "book_genre": row[1],
            "chapter_num": row[2],
            "scene_type": row[3],
            "emotion": row[4],
            "content": row[5],
            "word_count": row[6],
            "avg_sentence_length": row[7],
            "dialogue_ratio": row[8],
            "exclamation_density": row[9],
            "quality_score": row[10],
        }
        results.append(result)

        print(f"\n{'='*60}")
        print(f"【{row[0]}】ch{row[2]} | {row[3]}/{row[4]} | {row[6]}字 | 质量:{row[10]:.3f}")
        print(f"句长{row[7]:.0f}字 | 对话{row[8]:.0%} | 感叹{row[9]:.1f}/千字")
        print(f"{'='*60}")
        print(row[5][:500] + ("..." if len(row[5]) > 500 else ""))

    conn.close()
    return results


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Style RAG Builder")
    parser.add_argument("--build", action="store_true", help="构建/重建风格参考库")
    parser.add_argument("--genre", type=str, help="只构建某题材")
    parser.add_argument("--stats", action="store_true", help="查看统计")
    parser.add_argument("--query", action="store_true", help="查询片段")
    parser.add_argument("--scene-type", type=str, help="场景类型过滤")
    parser.add_argument("--emotion", type=str, help="情绪过滤")
    parser.add_argument("--limit", type=int, default=3, help="返回数量")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    if args.build:
        build_style_rag(genre_filter=args.genre, verbose=args.verbose)
    elif args.stats:
        show_stats()
    elif args.query:
        results = query_fragments(
            scene_type=args.scene_type,
            emotion=args.emotion,
            genre=args.genre,
            limit=args.limit,
        )
        if args.format == "json" and results:
            print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
