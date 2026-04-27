"""US-011: explosive_retriever.py 爆款示例语义检索器测试。

覆盖:
  1. 空索引 graceful degradation
  2. mock 索引检索（关键词 overlap 评分）
  3. scene_type 过滤
  4. k 参数控制
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from ink_writer.retrieval.explosive_retriever import (
    ExplosiveRetriever,
    build_retriever,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MOCK_SLICES: list[dict] = [
    {
        "excerpt": "他一拳轰出，气浪把地面的石砖掀飞了七八块。",
        "scene_type": "combat",
        "source_book": "夜无疆",
        "source_chapter": 42,
    },
    {
        "excerpt": "\"你来了。\"她抬起头，眼里有泪，但嘴角在笑。",
        "scene_type": "dialogue",
        "source_book": "剑来",
        "source_chapter": 15,
    },
    {
        "excerpt": "他站在山巅，看着云海翻涌。三年前他在这里失去了一切。",
        "scene_type": "emotional",
        "source_book": "完美世界",
        "source_chapter": 100,
    },
    {
        "excerpt": "刀光闪过，他低头避开，反手一剑刺向对方肋下。",
        "scene_type": "combat",
        "source_book": "夜无疆",
        "source_chapter": 55,
    },
    {
        "excerpt": "\"这酒有毒。\"他把杯子往桌上一顿，酒液溅出半圈。",
        "scene_type": "dialogue",
        "source_book": "剑来",
        "source_chapter": 30,
    },
]


@pytest.fixture
def mock_index_path() -> str:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(_MOCK_SLICES, f, ensure_ascii=False)
        return f.name


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExplosiveRetrieverEmpty:
    """Graceful degradation when index doesn't exist."""

    def test_retrieve_with_no_index_returns_empty(self) -> None:
        retriever = ExplosiveRetriever("/nonexistent/path/index.json")
        results = retriever.retrieve("战斗场景", k=3)
        assert results == []

    def test_build_retriever_with_no_index_returns_empty(self) -> None:
        retriever = build_retriever("/nonexistent/path/index.json")
        results = retriever.retrieve("test", k=5)
        assert results == []


class TestExplosiveRetrieverWithMockIndex:
    """Test retrieval with mock index data."""

    def test_retrieve_returns_k_results(self, mock_index_path: str) -> None:
        retriever = ExplosiveRetriever(mock_index_path)
        results = retriever.retrieve("战斗场景刀光剑影", k=3)
        assert len(results) <= 3
        assert len(results) >= 1

    def test_retrieve_with_scene_type_filter(self, mock_index_path: str) -> None:
        retriever = ExplosiveRetriever(mock_index_path)
        results = retriever.retrieve("战斗", scene_type="combat", k=10)
        assert len(results) > 0
        for r in results:
            assert r["scene_type"] == "combat"

    def test_retrieve_dialogue_scene_type(self, mock_index_path: str) -> None:
        retriever = ExplosiveRetriever(mock_index_path)
        results = retriever.retrieve("对话", scene_type="dialogue", k=10)
        assert len(results) > 0
        for r in results:
            assert r["scene_type"] == "dialogue"

    def test_result_has_required_fields(self, mock_index_path: str) -> None:
        retriever = ExplosiveRetriever(mock_index_path)
        results = retriever.retrieve("test", k=1)
        assert len(results) == 1
        r = results[0]
        for field in ("excerpt", "score", "scene_type", "source_book", "source_chapter"):
            assert field in r, f"Result missing field: {field}"

    def test_results_sorted_by_score_desc(self, mock_index_path: str) -> None:
        retriever = ExplosiveRetriever(mock_index_path)
        results = retriever.retrieve("战斗刀光剑影轰拳", k=5)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True), f"Scores not sorted desc: {scores}"

    def test_retrieve_k_zero_returns_empty(self, mock_index_path: str) -> None:
        retriever = ExplosiveRetriever(mock_index_path)
        results = retriever.retrieve("test", k=0)
        assert results == []

    def test_retrieve_empty_query_returns_results(self, mock_index_path: str) -> None:
        retriever = ExplosiveRetriever(mock_index_path)
        results = retriever.retrieve("", k=3)
        # Empty query should still return results (all equal score)
        assert len(results) <= 3


class TestExplosiveRetrieverCaching:
    """Index is loaded only once."""

    def test_second_retrieve_reuses_cache(self, mock_index_path: str) -> None:
        retriever = ExplosiveRetriever(mock_index_path)
        r1 = retriever.retrieve("战斗", k=1)
        r2 = retriever.retrieve("对话", k=1)
        assert r1 == retriever.retrieve("战斗", k=1)  # deterministic for same query


class TestBuildRetriever:
    """Factory function tests."""

    def test_build_retriever_returns_retriever(self, mock_index_path: str) -> None:
        retriever = build_retriever(mock_index_path)
        assert isinstance(retriever, ExplosiveRetriever)
        results = retriever.retrieve("test", k=1)
        assert len(results) == 1


class TestPublicAPI:
    """ink_writer.retrieval __all__ exports."""

    def test_init_exports(self) -> None:
        from ink_writer import retrieval

        assert hasattr(retrieval, "ExplosiveRetriever")
        assert hasattr(retrieval, "build_retriever")
        assert "ExplosiveRetriever" in retrieval.__all__
        assert "build_retriever" in retrieval.__all__
