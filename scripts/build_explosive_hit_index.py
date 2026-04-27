#!/usr/bin/env python3
"""US-010: 从 reference corpus 构建爆款示例 RAG 语义切片索引。

读取 benchmark/reference_corpus/ 下前 N 本爆款书，将每章正文按段落切片，
标注元数据（书名、章节、scene_type启发式判定），输出到 data/explosive_hit_index.json。

Usage:
    python3 scripts/build_explosive_hit_index.py                # 默认 5 本书
    python3 scripts/build_explosive_hit_index.py --books 10     # 10 本书
    python3 scripts/build_explosive_hit_index.py --dry-run       # 打印统计不写入
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORPUS = REPO / "benchmark" / "reference_corpus"
OUTPUT = REPO / "data" / "explosive_hit_index.json"

# 场景类型启发式关键词
_SCENE_HEURISTICS: list[tuple[str, list[str]]] = [
    ("combat", ["战斗", "出手", "杀", "剑", "刀", "拳", "掌", "轰", "攻", "战", "刺", "劈", "斩"]),
    ("dialogue", ["说", "道", "问", "答", "笑", "叹", "喊", "叫", "讲", "聊", "谈"]),
    ("emotional", ["泪", "哭", "悲", "痛", "伤", "恨", "悔", "思念", "回忆"]),
    ("action", ["走", "跑", "跳", "冲", "推", "拉", "抓", "拿", "放", "站", "坐", "转身"]),
    ("description", ["山", "水", "天", "云", "风", "雨", "树", "花", "月", "星", "雾", "光"]),
]


def _scene_type_for(text: str) -> str:
    """启发式判定段落场景类型。"""
    scores: dict[str, int] = {}
    for stype, keywords in _SCENE_HEURISTICS:
        scores[stype] = sum(1 for kw in keywords if kw in text)
    if not scores:
        return "other"
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] >= 2 else "other"


def _is_dialogue_line(line: str) -> bool:
    """判断是否为对话行（引号开头）。"""
    return bool(re.match(r'^["""''「」『』"\']', line.strip()))


def slice_chapter(text: str, book_name: str, chapter_file: str) -> list[dict]:
    """将章节正文切片为段落级示例，附带元数据。"""
    slices: list[dict] = []

    # 分行后按段落边界合并：空行或 　 缩进起头视为新段落
    raw_lines = text.split("\n")
    paragraphs: list[str] = []
    buf: list[str] = []
    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            if buf:
                paragraphs.append("".join(buf))
                buf = []
        elif line.startswith("　") and buf:
            # 中文段落缩进 → 新段落
            paragraphs.append("".join(buf))
            buf = [stripped]
        else:
            buf.append(stripped)
    if buf:
        paragraphs.append("".join(buf))

    for i, para in enumerate(paragraphs):
        p_len = len(para)
        if p_len < 10:  # 跳过过短段落
            continue

        scene = _scene_type_for(para)
        has_dialogue = any(_is_dialogue_line(line) for line in para.split("\n"))
        dialogue_ratio = sum(
            1 for line in para.split("\n") if _is_dialogue_line(line)
        ) / max(len(para.split("\n")), 1)

        slices.append({
            "text": para[:300],  # 截断到 300 字符
            "char_count": p_len,
            "book": book_name,
            "chapter": chapter_file.replace(".md", ""),
            "para_index": i,
            "scene_type": scene,
            "has_dialogue": has_dialogue,
            "dialogue_ratio": round(dialogue_ratio, 2),
        })

    return slices


def build_index(book_dirs: list[Path]) -> tuple[list[dict], dict]:
    """构建完整索引。"""
    all_slices: list[dict] = []
    stats: dict[str, int] = {}

    for book_dir in book_dirs:
        book_name = book_dir.name
        book_slices = 0
        chapter_files = sorted(
            [f for f in book_dir.rglob("*") if f.is_file() and f.suffix in (".md", ".txt")
             and f.name not in ("README.md", "index.md", "manifest.json")],
            key=lambda f: f.name,
        )

        for ch_file in chapter_files:
            try:
                text = ch_file.read_text(encoding="utf-8")
            except Exception:
                continue
            if len(text) < 100:
                continue

            rel_path = str(ch_file.relative_to(book_dir))
            slices = slice_chapter(text, book_name, rel_path)
            all_slices.extend(slices)
            book_slices += len(slices)

        stats[book_name] = book_slices
        print(f"  {book_name}: {len(chapter_files)} 章, {book_slices} 切片")

    return all_slices, stats


def list_corpus_books(limit: int = 5) -> list[Path]:
    """返回 corpus 中前 limit 本书的目录。"""
    if not CORPUS.is_dir():
        print(f"corpus 目录不存在: {CORPUS}", file=sys.stderr)
        return []
    dirs = sorted(
        [d for d in CORPUS.iterdir() if d.is_dir() and not d.name.startswith(".")],
        key=lambda d: d.name,
    )
    return dirs[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description="构建爆款示例 RAG 索引")
    parser.add_argument("--books", type=int, default=5, help="使用前 N 本书（默认 5）")
    parser.add_argument("--dry-run", action="store_true", help="打印统计不写入")
    args = parser.parse_args()

    books = list_corpus_books(limit=args.books)
    if not books:
        print("无可用 corpus 书，中止")
        sys.exit(1)

    print(f"从 {len(books)} 本书构建爆款索引...")
    slices, stats = build_index(books)

    print(f"\n总计: {len(slices)} 个语义切片")
    scene_dist = {}
    for s in slices:
        st = s["scene_type"]
        scene_dist[st] = scene_dist.get(st, 0) + 1
    print(f"场景分布: {scene_dist}")

    index_data = {
        "version": 1,
        "source": "benchmark/reference_corpus",
        "total_slices": len(slices),
        "book_stats": stats,
        "scene_distribution": scene_dist,
        "slices": slices,
    }

    if args.dry_run:
        print("\n[dry-run] 不写入文件")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        print(f"\n已写入 {OUTPUT}")
        print(f"文件大小: {OUTPUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
