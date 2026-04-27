"""PRD US-011: explosive_retriever 语义检索器测试。

验证:
  1. ExplosiveRetriever 从 mock 索引正确加载切片
  2. retrieve 按 scene_type 过滤
  3. retrieve 返回 top-k 正确结构和排序
  4. 空索引/缺失索引 graceful fallback
  5. build_retriever / get_retriever 工厂函数
  6. 返回结果兼容新旧两套字段名
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from ink_writer.retrieval.explosive_retriever import (
    ExplosiveRetriever,
    build_retriever,
    get_retriever,
)


def _mock_index() -> list[dict]:
    """返回 6 切片 mock 索引，覆盖各 scene_type。"""
    return [
        {
            "excerpt": "他第一时间缩肩，下蹲，滚向一侧的雪地。刀风擦过后颈。",
            "scene_type": "combat",
            "source_book": "夜无疆",
            "source_chapter": 12,
        },
        {
            "excerpt": "'找到了！' '嗯？' 两句对话各占一段。",
            "scene_type": "dialogue",
            "source_book": "青山",
            "source_chapter": 5,
        },
        {
            "excerpt": "秦铭从干果堆中挑出一部分橡果，道：'这种坚果需要处理后才能吃。'",
            "scene_type": "dialogue",
            "source_book": "夜无疆",
            "source_chapter": 3,
        },
        {
            "excerpt": "她把碗洗了三遍。第三遍的时候水早就凉了。",
            "scene_type": "emotional",
            "source_book": "苟在武道世界成圣",
            "source_chapter": 8,
        },
        {
            "excerpt": "伤口不深，血很快止住了。如果反应稍慢一拍，后颈要被咬断。",
            "scene_type": "combat",
            "source_book": "夜无疆",
            "source_chapter": 12,
        },
        {
            "excerpt": "周良：'量物，亦量人。量你的筋骨，量你的胆气。'",
            "scene_type": "dialogue",
            "source_book": "苟在武道世界成圣",
            "source_chapter": 2,
        },
    ]


def _write_mock_index(path: Path) -> None:
    path.write_text(json.dumps(_mock_index(), ensure_ascii=False), encoding="utf-8")


class TestExplosiveRetrieverLoad:
    """索引加载与 fallback。"""

    def test_loads_from_valid_index(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(_mock_index(), f, ensure_ascii=False)
            tmp_path = f.name

        try:
            retriever = ExplosiveRetriever(tmp_path)
            results = retriever.retrieve("战斗场景", k=6)
            assert len(results) >= 1
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_empty_index_missing_file(self) -> None:
        retriever = ExplosiveRetriever("/tmp/nonexistent_index.json")
        results = retriever.retrieve("anything", k=3)
        assert results == []

    def test_build_retriever_returns_explosive_retriever(self) -> None:
        r = build_retriever()
        assert isinstance(r, ExplosiveRetriever)

    def test_build_retriever_graceful_on_missing(self) -> None:
        r = build_retriever("/tmp/definitely_not_there.json")
        assert r.retrieve("test", k=1) == []

    def test_load_method_loads_index(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(_mock_index(), f, ensure_ascii=False)
            tmp_path = f.name

        try:
            r = ExplosiveRetriever(tmp_path)
            r.load()
            assert r.is_loaded
            assert r.slice_count == len(_mock_index())
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_get_retriever_returns_loaded_retriever(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(_mock_index(), f, ensure_ascii=False)
            tmp_path = f.name

        try:
            r = get_retriever(tmp_path)
            assert r.is_loaded
            assert r.slice_count == len(_mock_index())
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_get_retriever_graceful_on_missing(self) -> None:
        r = get_retriever("/nonexistent/index.json")
        assert r.is_loaded
        assert r.slice_count == 0


class TestRetrieveFiltering:
    """按 scene_type 过滤 + top-k 返回。"""

    def test_scene_type_filter_combat(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(_mock_index(), f, ensure_ascii=False)
            tmp_path = f.name

        try:
            retriever = ExplosiveRetriever(tmp_path)
            results = retriever.retrieve("战斗 刀", scene_type="combat", k=2)
            assert len(results) >= 1
            for r in results:
                assert r["scene_type"] == "combat"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_scene_type_filter_dialogue(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(_mock_index(), f, ensure_ascii=False)
            tmp_path = f.name

        try:
            retriever = ExplosiveRetriever(tmp_path)
            results = retriever.retrieve("对话 说", scene_type="dialogue", k=3)
            assert len(results) >= 1
            dialogue_types = {r["scene_type"] for r in results}
            assert dialogue_types == {"dialogue"} or "dialogue" in dialogue_types
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_no_scene_type_returns_all(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(_mock_index(), f, ensure_ascii=False)
            tmp_path = f.name

        try:
            retriever = ExplosiveRetriever(tmp_path)
            results = retriever.retrieve("测试", scene_type=None, k=10)
            assert len(results) >= 1
            types = {r["scene_type"] for r in results}
            assert len(types) >= 1
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_nonexistent_scene_type_falls_back(self) -> None:
        """不存在的 scene_type -> fallback 到全集。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(_mock_index(), f, ensure_ascii=False)
            tmp_path = f.name

        try:
            retriever = ExplosiveRetriever(tmp_path)
            results = retriever.retrieve("测试", scene_type="nonexistent_type", k=3)
            assert len(results) >= 1
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class TestRetrieveReturnSchema:
    """验证返回结构（新旧两套字段名兼容）。"""

    def test_result_has_required_fields(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(_mock_index(), f, ensure_ascii=False)
            tmp_path = f.name

        try:
            retriever = ExplosiveRetriever(tmp_path)
            results = retriever.retrieve("战斗", k=1)
            assert len(results) == 1
            r = results[0]
            # 旧字段名
            for field in ("excerpt", "score", "scene_type", "source_book", "source_chapter"):
                assert field in r, f"Missing field: {field}"
            # 新字段名 (linter API 兼容)
            for field in ("text", "book", "chapter", "has_dialogue"):
                assert field in r, f"Missing field: {field}"
            assert isinstance(r["excerpt"], str) and len(r["excerpt"]) > 0
            assert isinstance(r["score"], float)
            assert isinstance(r["source_book"], str)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_results_sorted_by_score_desc(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(_mock_index(), f, ensure_ascii=False)
            tmp_path = f.name

        try:
            retriever = ExplosiveRetriever(tmp_path)
            results = retriever.retrieve("战斗 刀", k=5)
            scores = [r["score"] for r in results]
            assert scores == sorted(scores, reverse=True), (
                f"Scores not descending: {scores}"
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_k_limits_results(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(_mock_index(), f, ensure_ascii=False)
            tmp_path = f.name

        try:
            retriever = ExplosiveRetriever(tmp_path)
            for k in (1, 2, 3):
                results = retriever.retrieve("测试", k=k)
                assert len(results) <= k, f"k={k} but got {len(results)} results"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_top_k_alias_works(self) -> None:
        """top_k 参数（linter API）与 k 参数行为一致。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(_mock_index(), f, ensure_ascii=False)
            tmp_path = f.name

        try:
            retriever = ExplosiveRetriever(tmp_path)
            results_k = retriever.retrieve("战斗", k=2)
            results_topk = retriever.retrieve("战斗", top_k=2)
            assert len(results_k) == len(results_topk)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
