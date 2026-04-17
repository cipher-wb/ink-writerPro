"""Semantic retriever over human-written style fragments using FAISS.

v13 US-008：索引缺失时三档降级：
  1. 尝试 subprocess 调用 `scripts/build_style_rag.py` 自动构建（需要
     benchmark/style_rag.db 源数据 + sentence-transformers）
  2. 构建失败时 → 退化到 SQLite 直查模式（style_rag.db.style_fragments 表
     按 filter + quality_score DESC 采样，无语义相似度但仍可用）
  3. 无 style_rag.db 时 → raise FileNotFoundError（保持原契约）
"""

from __future__ import annotations

import json
import logging
import random
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

DEFAULT_INDEX_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "style_rag"
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "benchmark" / "style_rag.db"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
BUILD_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "build_style_rag.py"


@dataclass
class StyleFragment:
    id: str
    book_title: str
    book_genre: str
    chapter_num: int
    scene_index: int
    scene_type: str
    emotion: str
    content: str
    word_count: int
    avg_sentence_length: float = 0.0
    short_sentence_ratio: float = 0.0
    long_sentence_ratio: float = 0.0
    dialogue_ratio: float = 0.0
    exclamation_density: float = 0.0
    ellipsis_density: float = 0.0
    question_density: float = 0.0
    quality_score: float = 0.0
    score: float = 0.0


class StyleRAGRetriever:
    """Retrieve human-written style fragments by semantic similarity.

    v13 US-008：构造时若 FAISS 索引缺失，先尝试 subprocess 自动构建；
    构建失败则降级为 SQLite 直查模式（`self._use_fallback = True`），
    retrieve() 会走 _sqlite_retrieve() 路径（按 quality_score / filter 采样）。
    """

    def __init__(
        self,
        index_dir: Path | str = DEFAULT_INDEX_DIR,
        *,
        db_path: Path | str = DEFAULT_DB_PATH,
        auto_build: bool = True,
    ) -> None:
        index_dir = Path(index_dir)
        self._index_dir = index_dir
        self._db_path = Path(db_path)
        self._use_fallback = False
        self._index = None
        self._metadata: list[dict] = []
        self._contents: dict[str, str] = {}
        self._model = None

        faiss_path = index_dir / "style_rag.faiss"
        meta_path = index_dir / "metadata.json"
        contents_path = index_dir / "contents.json"
        missing = [p for p in (faiss_path, meta_path, contents_path) if not p.exists()]

        # v13 US-008 降级链：FAISS 索引 → 自动构建 → SQLite fallback → 报错
        if missing and auto_build:
            logger.warning(
                "Style RAG FAISS index missing (%s); attempting auto-build via %s",
                [p.name for p in missing],
                BUILD_SCRIPT.name,
            )
            if self._try_auto_build():
                # 构建成功重新检查
                missing = [p for p in (faiss_path, meta_path, contents_path) if not p.exists()]

        if missing:
            # v13 US-008 第二档降级：退化到 SQLite 直查
            if self._db_path.exists():
                logger.warning(
                    "Style RAG auto-build unavailable; falling back to SQLite direct query "
                    "(no semantic similarity, uses quality_score ranking). DB: %s",
                    self._db_path,
                )
                self._use_fallback = True
                return
            raise FileNotFoundError(
                f"Style RAG index files missing: {[str(p) for p in missing]}; "
                f"auto-build failed and SQLite fallback source {self._db_path} not found. "
                f"Run 'python scripts/build_style_rag.py' to build the index."
            )

        # 正常 FAISS 路径
        self._index = faiss.read_index(str(faiss_path))
        self._metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        contents_raw = json.loads(contents_path.read_text(encoding="utf-8"))
        self._contents = {c["id"]: c["content"] for c in contents_raw}
        self._model = SentenceTransformer(MODEL_NAME)

    def _try_auto_build(self) -> bool:
        """尝试 subprocess 调用 build_style_rag.py。成功返回 True。"""
        if not BUILD_SCRIPT.exists():
            logger.warning("Build script not found at %s", BUILD_SCRIPT)
            return False
        if not self._db_path.exists():
            logger.warning("Source DB %s missing; cannot auto-build", self._db_path)
            return False
        try:
            result = subprocess.run(
                [sys.executable, str(BUILD_SCRIPT)],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode == 0:
                logger.info("Style RAG auto-build succeeded")
                return True
            logger.warning(
                "Style RAG auto-build failed (exit %d): %s",
                result.returncode, result.stderr[:500],
            )
            return False
        except subprocess.TimeoutExpired:
            logger.warning("Style RAG auto-build timeout after 600s")
            return False
        except Exception as exc:
            logger.warning("Style RAG auto-build exception: %s", exc)
            return False

    @property
    def fragment_count(self) -> int:
        return len(self._metadata)

    def retrieve(
        self,
        query: str,
        k: int = 5,
        scene_type: str | None = None,
        emotion: str | None = None,
        genre: str | None = None,
        min_quality: float = 0.0,
    ) -> list[StyleFragment]:
        if self._use_fallback:
            # v13 US-008：SQLite 直查路径（无语义相似度，按 filter + quality_score 采样）
            return self._sqlite_retrieve(k, scene_type, emotion, genre, min_quality)

        q_emb = self._model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        )
        q_vec = np.array(q_emb, dtype=np.float32).reshape(1, -1)

        filters = self._build_filter_mask(scene_type, emotion, genre, min_quality)

        if filters is not None:
            indices = [i for i, keep in enumerate(filters) if keep]
            if not indices:
                return []
            return self._filtered_search(q_vec, indices, k)

        return self._full_search(q_vec, k)

    def _sqlite_retrieve(
        self,
        k: int,
        scene_type: str | None,
        emotion: str | None,
        genre: str | None,
        min_quality: float,
    ) -> list[StyleFragment]:
        """v13 US-008 fallback：直接从 style_rag.db.style_fragments 按 filter + quality 采样。"""
        where = []
        params: list = []
        if scene_type:
            where.append("scene_type = ?")
            params.append(scene_type)
        if emotion:
            where.append("emotion = ?")
            params.append(emotion)
        if genre:
            where.append("book_genre LIKE ?")
            params.append(f"%{genre}%")
        if min_quality > 0:
            where.append("quality_score >= ?")
            params.append(min_quality)
        where_clause = ("WHERE " + " AND ".join(where)) if where else ""
        # 取 quality_score 最高的 k*3 条，再随机采样 k 条（避免固定排序导致每次同样结果）
        sample_pool = max(k * 3, 20)
        sql = f"""
            SELECT id, book_title, book_genre, chapter_num, scene_index, scene_type,
                   emotion, content, word_count, avg_sentence_length, short_sentence_ratio,
                   long_sentence_ratio, dialogue_ratio, exclamation_density, ellipsis_density,
                   question_density, quality_score
            FROM style_fragments
            {where_clause}
            ORDER BY quality_score DESC
            LIMIT ?
        """
        params.append(sample_pool)
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
        if not rows:
            return []
        sampled = random.sample(rows, min(k, len(rows)))
        return [self._row_to_fragment(r) for r in sampled]

    @staticmethod
    def _row_to_fragment(row) -> StyleFragment:
        return StyleFragment(
            id=row["id"], book_title=row["book_title"], book_genre=row["book_genre"],
            chapter_num=row["chapter_num"], scene_index=row["scene_index"],
            scene_type=row["scene_type"], emotion=row["emotion"], content=row["content"],
            word_count=row["word_count"],
            avg_sentence_length=row["avg_sentence_length"] or 0.0,
            short_sentence_ratio=row["short_sentence_ratio"] or 0.0,
            long_sentence_ratio=row["long_sentence_ratio"] or 0.0,
            dialogue_ratio=row["dialogue_ratio"] or 0.0,
            exclamation_density=row["exclamation_density"] or 0.0,
            ellipsis_density=row["ellipsis_density"] or 0.0,
            question_density=row["question_density"] or 0.0,
            quality_score=row["quality_score"] or 0.0,
            score=(row["quality_score"] or 0.0) / 100.0,  # 归一化为相似度近似
        )

    def _build_filter_mask(
        self,
        scene_type: str | None,
        emotion: str | None,
        genre: str | None,
        min_quality: float,
    ) -> list[bool] | None:
        if scene_type is None and emotion is None and genre is None and min_quality <= 0:
            return None

        mask = []
        for m in self._metadata:
            keep = True
            if scene_type is not None and m.get("scene_type") != scene_type:
                keep = False
            if emotion is not None and m.get("emotion") != emotion:
                keep = False
            if genre is not None and genre not in (m.get("book_genre") or ""):
                keep = False
            if min_quality > 0 and (m.get("quality_score") or 0) < min_quality:
                keep = False
            mask.append(keep)
        return mask

    def _filtered_search(
        self, q_vec: np.ndarray, indices: Sequence[int], k: int
    ) -> list[StyleFragment]:
        vecs = np.array(
            [self._index.reconstruct(i) for i in indices], dtype=np.float32
        )
        sims = (vecs @ q_vec.T).flatten()
        top_k = min(k, len(indices))
        ranked = np.argsort(-sims)[:top_k]

        results: list[StyleFragment] = []
        for pos in ranked:
            orig_idx = indices[pos]
            meta = self._metadata[orig_idx]
            results.append(self._meta_to_fragment(meta, float(sims[pos])))
        return results

    def _full_search(self, q_vec: np.ndarray, k: int) -> list[StyleFragment]:
        actual_k = min(k, len(self._metadata))
        scores, faiss_indices = self._index.search(q_vec, actual_k)
        results: list[StyleFragment] = []
        for sim, idx in zip(scores[0], faiss_indices[0]):
            if idx < 0:
                continue
            results.append(self._meta_to_fragment(self._metadata[idx], float(sim)))
        return results

    def _meta_to_fragment(self, meta: dict, score: float) -> StyleFragment:
        fid = meta["id"]
        content = self._contents.get(fid, meta.get("content_preview", ""))
        return StyleFragment(
            id=fid,
            book_title=meta.get("book_title", ""),
            book_genre=meta.get("book_genre", ""),
            chapter_num=meta.get("chapter_num", 0),
            scene_index=meta.get("scene_index", 0),
            scene_type=meta.get("scene_type", ""),
            emotion=meta.get("emotion", ""),
            content=content,
            word_count=meta.get("word_count", 0),
            avg_sentence_length=meta.get("avg_sentence_length", 0.0),
            short_sentence_ratio=meta.get("short_sentence_ratio", 0.0),
            long_sentence_ratio=meta.get("long_sentence_ratio", 0.0),
            dialogue_ratio=meta.get("dialogue_ratio", 0.0),
            exclamation_density=meta.get("exclamation_density", 0.0),
            ellipsis_density=meta.get("ellipsis_density", 0.0),
            question_density=meta.get("question_density", 0.0),
            quality_score=meta.get("quality_score", 0.0),
            score=score,
        )
