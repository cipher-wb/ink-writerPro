"""US-011: 爆款示例语义检索器。

输入大纲文本 + scene_type，从 data/explosive_hit_index.json 中检索
top-k 最相关的爆款段落切片，返回带元数据的 excerpt 列表。

Usage:
    retriever = ExplosiveRetriever("data/explosive_hit_index.json")
    results = retriever.retrieve("战斗场景：主角对敌", scene_type="combat", k=3)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_INDEX = Path(__file__).resolve().parents[2] / "data" / "explosive_hit_index.json"


class ExplosiveRetriever:
    """从爆款索引中检索相似段落切片。

    当前实现基于关键词 overlap 的轻量检索（无 embedding 依赖，
    保证索引未 build 时也能 graceful fallback）。后续可替换为
    sentence-transformers 语义相似度。
    """

    def __init__(self, index_path: str | Path | None = None) -> None:
        self._index_path = Path(index_path) if index_path else _DEFAULT_INDEX
        self._slices: list[dict[str, Any]] = []
        self._loaded: bool = False

    # -- compat properties for linter API surface --------------------------

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def slice_count(self) -> int:
        return len(self._slices)

    def load(self) -> None:
        """公开加载方法（linter API 兼容）。"""
        self._ensure_loaded()

    # -- core ---------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        path = self._index_path
        if not path.exists():
            logger.warning("ExplosiveHit index not found at %s, retriever will return empty", path)
            self._loaded = True
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._slices = data
            elif isinstance(data, dict):
                self._slices = data.get("slices", data.get("entries", []))
            logger.info("Loaded %d slices from %s", len(self._slices), path)
        except Exception as exc:
            logger.warning("Failed to load explosive hit index: %s", exc)
        self._loaded = True

    def retrieve(
        self,
        query_text: str,
        scene_type: str | None = None,
        k: int = 3,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """返回 top-k 最相关的段落切片。

        Args:
            query_text: 大纲/场景描述文本
            scene_type: 过滤场景类型（combat/dialogue/emotional/action/setup/climax）
            k: 返回切片数
            top_k: k 的别名（linter API 兼容，优先于 k）

        Returns:
            [{"excerpt": str, "score": float, "scene_type": str,
              "source_book": str, "source_chapter": int, ...}, ...]
        """
        self._ensure_loaded()
        if not self._slices:
            return []

        # Reject queries with no CJK characters (e.g., pure ASCII/English)
        if not any('一' <= c <= '鿿' for c in query_text):
            return []

        limit = top_k if top_k is not None else k

        candidates = self._slices
        if scene_type:
            candidates = [
                s for s in candidates
                if s.get("scene_type", "").lower() == scene_type.lower()
            ]
            if not candidates:
                # Fallback: no exact match, return all
                candidates = self._slices

        # Keyword overlap scoring
        query_chars = set(query_text)
        scored: list[tuple[float, dict]] = []
        for s in candidates:
            text = s.get("text", s.get("excerpt", s.get("content", "")))
            if not text:
                continue
            text_chars = set(text)
            overlap = len(query_chars & text_chars) / max(len(query_chars), 1)
            scored.append((overlap, s))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_k_results = scored[:limit]

        return [
            {
                "excerpt": s.get("text", s.get("excerpt", s.get("content", "")))[:300],
                "text": s.get("text", s.get("excerpt", s.get("content", "")))[:300],
                "score": round(score, 4),
                "scene_type": s.get("scene_type", "unknown"),
                "source_book": s.get("book", s.get("source_book", "unknown")),
                "source_chapter": s.get("chapter", s.get("source_chapter", 0)),
                "book": s.get("book", s.get("source_book", "unknown")),
                "chapter": s.get("chapter", s.get("source_chapter", 0)),
                "has_dialogue": s.get("has_dialogue", False),
            }
            for score, s in top_k_results
        ]


def build_retriever(index_path: str | Path | None = None) -> ExplosiveRetriever:
    """工厂函数：构建 ExplosiveRetriever。

    索引缺失时不抛异常，返回空检索器（graceful degradation）。
    """
    return ExplosiveRetriever(index_path)


def get_retriever(index_path: str | Path | None = None) -> ExplosiveRetriever:
    """工厂函数别名：创建并加载检索器（linter API 兼容）。"""
    r = ExplosiveRetriever(index_path)
    r.load()
    return r
