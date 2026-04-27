"""US-012: explosive_retrieval injection 集成测试。

验证 inject_explosive_examples 的 XML 块生成、开关控制、
graceful fallback 等行为。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from ink_writer.retrieval.inject import inject_explosive_examples


_MOCK_SLICES: list[dict] = [
    {"text": "他拔出长剑，剑光如雪，直刺对手咽喉。", "char_count": 60, "book": "test_book", "chapter": "ch001", "scene_type": "combat", "has_dialogue": False, "dialogue_ratio": 0.0},
    {"text": "\"你来了。\"她抬起头，眼里有泪光。", "char_count": 70, "book": "test_book", "chapter": "ch002", "scene_type": "dialogue", "has_dialogue": True, "dialogue_ratio": 0.5},
    {"text": "月光洒在湖面上，水面如镜。", "char_count": 80, "book": "test_book", "chapter": "ch003", "scene_type": "description", "has_dialogue": False, "dialogue_ratio": 0.0},
]


def _make_mock_index() -> str:
    data = {"version": 1, "slices": _MOCK_SLICES}
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(data, tmp, ensure_ascii=False)
    tmp.close()
    return tmp.name


class TestInjectExplosiveExamples:
    """inject_explosive_examples 核心功能测试。"""

    def test_returns_reference_examples_block(self) -> None:
        path = _make_mock_index()
        try:
            result = inject_explosive_examples("战斗场景：主角拔剑", scene_type="combat", index_path=path)
            assert "<reference_examples>" in result
            assert "</reference_examples>" in result
            assert "source:" in result
        finally:
            Path(path).unlink(missing_ok=True)

    def test_disabled_returns_empty(self) -> None:
        path = _make_mock_index()
        try:
            result = inject_explosive_examples("战斗", enabled=False, index_path=path)
            assert result == ""
        finally:
            Path(path).unlink(missing_ok=True)

    def test_missing_index_returns_empty(self) -> None:
        result = inject_explosive_examples("测试", index_path="/nonexistent/index.json")
        assert result == ""

    def test_no_results_returns_empty(self) -> None:
        path = _make_mock_index()
        try:
            # ASCII 无 CJK 字符 → 直接返回空
            result = inject_explosive_examples("XYZABC123", index_path=path)
            assert result == ""
        finally:
            Path(path).unlink(missing_ok=True)

    def test_block_contains_book_and_chapter(self) -> None:
        path = _make_mock_index()
        try:
            result = inject_explosive_examples("战斗", scene_type="combat", index_path=path)
            assert "test_book" in result
        finally:
            Path(path).unlink(missing_ok=True)

    def test_respects_k_parameter(self) -> None:
        path = _make_mock_index()
        try:
            result = inject_explosive_examples("战斗场景对话", k=1, index_path=path)
            # 应该只有 1 个 source 注释
            assert result.count("<!-- source:") == 1
        finally:
            Path(path).unlink(missing_ok=True)
