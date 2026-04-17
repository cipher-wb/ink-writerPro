"""US-008: Style RAG 自动构建 + SQLite fallback 测试。

验证 FAISS 索引缺失时：
  1. 尝试 auto-build 失败后降级到 SQLite 直查
  2. 返回的 StyleFragment 字段完整
  3. filter 条件正确应用
  4. SQLite DB 也不存在时抛 FileNotFoundError
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _make_style_db(db_path: Path, rows: int = 10) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE style_fragments (
            id TEXT PRIMARY KEY,
            book_title TEXT NOT NULL,
            book_genre TEXT NOT NULL,
            chapter_num INTEGER NOT NULL,
            scene_index INTEGER NOT NULL,
            scene_type TEXT NOT NULL,
            emotion TEXT NOT NULL,
            content TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            avg_sentence_length REAL, short_sentence_ratio REAL,
            long_sentence_ratio REAL, dialogue_ratio REAL,
            exclamation_density REAL, ellipsis_density REAL,
            question_density REAL, quality_score REAL
        )
    """)
    for i in range(rows):
        conn.execute(
            "INSERT INTO style_fragments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"frag{i}", f"book{i % 3}", "仙侠" if i % 2 else "都市",
                i + 1, 0, "dialogue" if i % 2 else "action",
                "紧张" if i % 3 else "平静", f"示例内容 {i}", 100 + i,
                15.0, 0.3, 0.2, 0.2, 0.1, 0.05, 0.05, 70 + i,
            ),
        )
    conn.commit()
    conn.close()


def test_fallback_to_sqlite_when_index_missing(tmp_path):
    pytest.importorskip("faiss")
    from ink_writer.style_rag.retriever import StyleRAGRetriever

    index_dir = tmp_path / "style_rag_empty"
    index_dir.mkdir()
    db_path = tmp_path / "style_rag.db"
    _make_style_db(db_path, rows=20)

    retriever = StyleRAGRetriever(index_dir=index_dir, db_path=db_path, auto_build=False)
    assert retriever._use_fallback is True

    results = retriever.retrieve("任意查询", k=3)
    assert len(results) == 3
    for frag in results:
        assert frag.content.startswith("示例内容")
        assert frag.quality_score >= 70


def test_fallback_filter_scene_type(tmp_path):
    pytest.importorskip("faiss")
    from ink_writer.style_rag.retriever import StyleRAGRetriever

    index_dir = tmp_path / "style_rag_empty"
    index_dir.mkdir()
    db_path = tmp_path / "style_rag.db"
    _make_style_db(db_path, rows=20)

    retriever = StyleRAGRetriever(index_dir=index_dir, db_path=db_path, auto_build=False)
    results = retriever.retrieve("x", k=5, scene_type="dialogue")
    assert all(f.scene_type == "dialogue" for f in results)


def test_missing_index_and_no_db_raises(tmp_path):
    pytest.importorskip("faiss")
    from ink_writer.style_rag.retriever import StyleRAGRetriever

    index_dir = tmp_path / "style_rag_empty"
    index_dir.mkdir()
    db_path = tmp_path / "nonexistent.db"

    with pytest.raises(FileNotFoundError, match="auto-build failed and SQLite fallback"):
        StyleRAGRetriever(index_dir=index_dir, db_path=db_path, auto_build=False)
