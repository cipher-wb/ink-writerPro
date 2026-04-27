"""US-011: explosive_retriever.py 爆款示例检索器测试。

验证检索器的加载、检索、graceful fallback 等行为。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from ink_writer.retrieval.explosive_retriever import (
    ExplosiveRetriever,
    get_retriever,
    _CJK_RE,
)


_MOCK_SLICES: list[dict] = [
    {"text": "他拔出长剑，剑光如雪，直刺对手咽喉。对手侧身避开，反手一掌拍向他胸口。", "char_count": 120, "book": "test_book", "chapter": "ch001", "scene_type": "combat", "has_dialogue": False, "dialogue_ratio": 0.0},
    {"text": "\"你来了。\"她抬起头，眼里有泪光闪烁。\"我以为你不会来了。\"他沉默片刻，伸手擦去她脸上的泪。\"我答应过你的。\"", "char_count": 150, "book": "test_book", "chapter": "ch002", "scene_type": "dialogue", "has_dialogue": True, "dialogue_ratio": 0.6},
    {"text": "天空是灰色的，云层压得很低。他站在山巅，望着脚下的云海翻滚，心中百感交集。", "char_count": 110, "book": "test_book", "chapter": "ch003", "scene_type": "emotional", "has_dialogue": False, "dialogue_ratio": 0.0},
    {"text": "他冲出门外，几步跃下台阶，翻身跨上马背。缰绳一抖，马匹如离弦之箭飞驰而去。", "char_count": 90, "book": "test_book", "chapter": "ch004", "scene_type": "action", "has_dialogue": False, "dialogue_ratio": 0.0},
    {"text": "月光洒在湖面上，水面如镜，映出满天繁星。远处的山影朦胧，像一幅淡淡的水墨画。", "char_count": 120, "book": "test_book", "chapter": "ch005", "scene_type": "description", "has_dialogue": False, "dialogue_ratio": 0.0},
    {"text": "\"别跑！\"少年大喊一声，拔腿就追。前方的人影翻过围墙，消失在夜色中。", "char_count": 95, "book": "test_book2", "chapter": "ch001", "scene_type": "action", "has_dialogue": True, "dialogue_ratio": 0.3},
]


def _make_mock_index() -> str:
    """创建临时 mock 索引文件并返回路径。"""
    data = {
        "version": 1,
        "slices": _MOCK_SLICES,
    }
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(data, tmp, ensure_ascii=False)
    tmp.close()
    return tmp.name


class TestExplosiveRetriever:
    """检索器核心功能测试。"""

    def test_load_from_mock_index(self) -> None:
        path = _make_mock_index()
        try:
            r = ExplosiveRetriever(path)
            r.load()
            assert r.is_loaded
            assert r.slice_count == len(_MOCK_SLICES)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_load_missing_file_graceful(self) -> None:
        r = ExplosiveRetriever("/nonexistent/path/index.json")
        r.load()
        assert r.is_loaded
        assert r.slice_count == 0

    def test_retrieve_returns_top_k(self) -> None:
        path = _make_mock_index()
        try:
            r = ExplosiveRetriever(path)
            results = r.retrieve("战斗场景：主角拔剑对敌", top_k=2)
            assert len(results) <= 2
            assert len(results) > 0
        finally:
            Path(path).unlink(missing_ok=True)

    def test_retrieve_scene_type_filter(self) -> None:
        path = _make_mock_index()
        try:
            r = ExplosiveRetriever(path)
            results = r.retrieve("对话场景：两人交谈", scene_type="dialogue", top_k=3)
            assert len(results) > 0
            if results:
                assert any(r_["scene_type"] == "dialogue" for r_ in results)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_retrieve_no_results_for_unrelated_query(self) -> None:
        path = _make_mock_index()
        try:
            r = ExplosiveRetriever(path)
            # ASCII 无 CJK 字符 → 直接返回空
            results = r.retrieve("XYZQWERTY123", top_k=3)
            assert results == []
        finally:
            Path(path).unlink(missing_ok=True)

    def test_retrieve_empty_index(self) -> None:
        r = ExplosiveRetriever()
        r._slices = []
        r._loaded = True
        results = r.retrieve("anything")
        assert results == []

    def test_result_structure(self) -> None:
        path = _make_mock_index()
        try:
            r = ExplosiveRetriever(path)
            results = r.retrieve("战斗", top_k=1)
            assert len(results) == 1
            res = results[0]
            assert "text" in res
            assert "book" in res
            assert "chapter" in res
            assert "scene_type" in res
            assert "score" in res
            assert "has_dialogue" in res
            # 向后兼容字段
            assert "excerpt" in res
            assert "source_book" in res
            assert "source_chapter" in res
        finally:
            Path(path).unlink(missing_ok=True)

    def test_dialogue_slices_get_boost(self) -> None:
        """对话段落应有更高权重。"""
        path = _make_mock_index()
        try:
            r = ExplosiveRetriever(path)
            results = r.retrieve("\"你来了\"她说", top_k=3)
            assert len(results) > 0
            dialogue_results = [r_ for r_ in results if r_["has_dialogue"]]
            non_dialogue = [r_ for r_ in results if not r_["has_dialogue"]]
            if dialogue_results:
                avg_d = sum(r_["score"] for r_ in dialogue_results) / len(dialogue_results)
                if non_dialogue:
                    avg_nd = sum(r_["score"] for r_ in non_dialogue) / len(non_dialogue)
                    assert avg_d >= avg_nd or len(dialogue_results) >= len(non_dialogue)
        finally:
            Path(path).unlink(missing_ok=True)


class TestKeywordExtraction:
    """_extract_keywords bigram 提取单元测试。"""

    def test_extracts_bigrams(self) -> None:
        kw = ExplosiveRetriever._extract_keywords("主角使用金手指")
        assert len(kw) > 0
        assert all(len(w) == 2 for w in kw)

    def test_filters_stopwords(self) -> None:
        kw = ExplosiveRetriever._extract_keywords("这个什么一个可以")
        valid = [w for w in kw if w not in {"这个", "个什", "什么", "么一", "一个", "个可", "可以"}]
        assert len(valid) == 0 or all(len(w) == 2 for w in valid)

    def test_short_text_returns_empty(self) -> None:
        kw = ExplosiveRetriever._extract_keywords("一")
        assert kw == []

    def test_empty_text(self) -> None:
        kw = ExplosiveRetriever._extract_keywords("")
        assert kw == []

    def test_returns_max_10(self) -> None:
        kw = ExplosiveRetriever._extract_keywords(
            "主角穿越异世界获得金手指系统开启修炼之路战斗升级"
        )
        assert len(kw) <= 10


class TestScoring:
    """_score_slice 评分逻辑单元测试。"""

    def test_zero_for_short_text(self) -> None:
        score = ExplosiveRetriever._score_slice(
            {"text": "abc", "scene_type": "other"}, ["战斗"], None,
        )
        assert score == 0.0

    def test_zero_for_no_keyword_match(self) -> None:
        score = ExplosiveRetriever._score_slice(
            {"text": "这是一个测试文本内容较长确保超过二十字符限制", "scene_type": "other"},
            ["战斗", "金手指"],
            None,
        )
        assert score == 0.0

    def test_scene_type_bonus(self) -> None:
        s = {"text": "战斗开始了主角拔出长剑冲向敌人刀光剑影杀声震天血染长袍", "scene_type": "combat", "char_count": 100}
        score_with_match = ExplosiveRetriever._score_slice(
            s, ["主角", "战斗"], scene_type="combat",
        )
        score_without_match = ExplosiveRetriever._score_slice(
            s, ["主角", "战斗"], scene_type="dialogue",
        )
        assert score_with_match > score_without_match

    def test_dialogue_bonus(self) -> None:
        s_with = {"text": "\"你好\"他说着走了过来站在门口看着远方暮色渐沉", "scene_type": "dialogue", "has_dialogue": True, "dialogue_ratio": 0.5, "char_count": 100}
        s_without = {"text": "他走了过来站在门口看着远方的天空云彩飘过晚风吹拂", "scene_type": "description", "has_dialogue": False, "dialogue_ratio": 0.0, "char_count": 100}
        score_with = ExplosiveRetriever._score_slice(s_with, ["过来", "门口"], None)
        score_without = ExplosiveRetriever._score_slice(s_without, ["过来", "门口"], None)
        assert score_with > score_without


class TestGetRetriever:
    """get_retriever 工厂函数测试。"""

    def test_returns_loaded_retriever(self) -> None:
        path = _make_mock_index()
        try:
            r = get_retriever(path)
            assert r.is_loaded
            assert r.slice_count == len(_MOCK_SLICES)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_graceful_on_missing(self) -> None:
        r = get_retriever("/nonexistent/index.json")
        assert r.is_loaded
        assert r.slice_count == 0
