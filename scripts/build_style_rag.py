#!/usr/bin/env python3
"""
Build Style RAG vector index from style_rag.db fragments.

Reads scene-level fragments from benchmark/style_rag.db (built by
benchmark/style_rag_builder.py), encodes them with the same
sentence-transformers model used by editor-wisdom, and writes a FAISS
index + metadata JSON to data/style_rag/.

Usage:
    python scripts/build_style_rag.py              # build index
    python scripts/build_style_rag.py --rebuild     # drop existing & rebuild
    python scripts/build_style_rag.py --stats       # show index stats
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
import pathlib
import sqlite3
import sys
import time

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
STYLE_RAG_DB = PROJECT_ROOT / "benchmark" / "style_rag.db"
INDEX_DIR = PROJECT_ROOT / "data" / "style_rag"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
BATCH_SIZE = 256


def load_fragments(db_path: pathlib.Path) -> list[dict]:
    if not db_path.exists():
        print(f"ERROR: {db_path} 不存在，请先运行 benchmark/style_rag_builder.py --build",
              file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, book_title, book_genre, chapter_num, scene_index,
               scene_type, emotion, content, word_count,
               avg_sentence_length, short_sentence_ratio, long_sentence_ratio,
               dialogue_ratio, exclamation_density, ellipsis_density,
               question_density, quality_score
        FROM style_fragments
        ORDER BY quality_score DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def build_index(
    db_path: pathlib.Path = STYLE_RAG_DB,
    index_dir: pathlib.Path = INDEX_DIR,
    model_name: str = MODEL_NAME,
) -> dict:
    fragments = load_fragments(db_path)
    if not fragments:
        print("ERROR: style_rag.db 中无片段", file=sys.stderr)
        sys.exit(1)

    print(f"加载 {len(fragments)} 个片段")

    model = SentenceTransformer(model_name)

    texts = [f.get("content", "") for f in fragments]
    print(f"编码中 (batch_size={BATCH_SIZE})...")
    t0 = time.time()
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=BATCH_SIZE,
    )
    embeddings = np.array(embeddings, dtype=np.float32)
    elapsed = time.time() - t0
    print(f"编码完成: {elapsed:.1f}s ({len(texts)/elapsed:.0f} 片段/s)")

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    index_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_dir / "style_rag.faiss"))

    metadata = []
    for frag in fragments:
        entry = {k: v for k, v in frag.items() if k != "content"}
        entry["content_preview"] = frag["content"][:200]
        metadata.append(entry)

    (index_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    (index_dir / "contents.json").write_text(
        json.dumps(
            [{"id": f["id"], "content": f["content"]} for f in fragments],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    stats = {
        "fragments_indexed": len(fragments),
        "embedding_dim": dim,
        "model": model_name,
        "index_path": str(index_dir),
    }
    (index_dir / "build_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n构建完成:")
    print(f"  片段数: {len(fragments)}")
    print(f"  向量维度: {dim}")
    print(f"  索引: {index_dir / 'style_rag.faiss'}")
    print(f"  元数据: {index_dir / 'metadata.json'}")
    print(f"  全文: {index_dir / 'contents.json'}")
    return stats


def show_stats(index_dir: pathlib.Path = INDEX_DIR):
    stats_path = index_dir / "build_stats.json"
    if not stats_path.exists():
        print("索引未构建，请先运行 --build")
        return

    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    meta_path = index_dir / "metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        from collections import Counter
        scene_counts = Counter(m["scene_type"] for m in meta)
        emotion_counts = Counter(m["emotion"] for m in meta)
        genre_counts = Counter(m["book_genre"] for m in meta)

        print(f"\n场景类型分布:")
        for k, v in scene_counts.most_common():
            print(f"  {k}: {v}")
        print(f"\n情绪分布:")
        for k, v in emotion_counts.most_common():
            print(f"  {k}: {v}")
        print(f"\n题材分布:")
        for k, v in genre_counts.most_common():
            print(f"  {k}: {v}")


def main():
    parser = argparse.ArgumentParser(description="Build Style RAG FAISS index")
    parser.add_argument("--rebuild", action="store_true", help="删除旧索引重建")
    parser.add_argument("--stats", action="store_true", help="显示索引统计")
    parser.add_argument("--db", type=str, default=str(STYLE_RAG_DB), help="style_rag.db 路径")
    parser.add_argument("--output", type=str, default=str(INDEX_DIR), help="输出目录")
    args = parser.parse_args()

    db_path = pathlib.Path(args.db)
    index_dir = pathlib.Path(args.output)

    if args.stats:
        show_stats(index_dir)
        return

    if args.rebuild and index_dir.exists():
        import shutil
        shutil.rmtree(index_dir)
        print(f"已删除旧索引: {index_dir}")

    build_index(db_path, index_dir)


if __name__ == "__main__":
    main()
