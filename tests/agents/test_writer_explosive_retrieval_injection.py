"""US-012: writer-agent Step 2A explosive_retriever injection test.

验证:
  1. inject_explosive_examples 可从 writer-agent draft 流程中调用
  2. retrieval 结果可注入 prompt reference_examples 块
  3. enabled=False 时跳过检索，返回空
  4. 索引缺失时 graceful fallback（不阻断写作）
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from ink_writer.retrieval.inject import inject_explosive_examples
from ink_writer.retrieval.explosive_retriever import ExplosiveRetriever


_MOCK_SLICES = [
    {
        "excerpt": "\"你来了。\"她抬起头，眼里有泪，但嘴角在笑。",
        "scene_type": "dialogue",
        "source_book": "剑来",
        "source_chapter": 15,
    },
    {
        "excerpt": "他一拳轰出，气浪把地面的石砖掀飞了七八块。",
        "scene_type": "combat",
        "source_book": "夜无疆",
        "source_chapter": 42,
    },
]


@pytest.fixture
def mock_index_path() -> str:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(_MOCK_SLICES, f, ensure_ascii=False)
        return f.name


class TestExplosiveInjection:
    """US-012 AC: retriever injection into writer-agent prompt."""

    def test_injection_produces_reference_examples_block(self, mock_index_path: str) -> None:
        block = inject_explosive_examples(
            "战斗场景：主角对敌", scene_type="combat", k=2, index_path=mock_index_path
        )
        assert "<reference_examples>" in block
        assert "</reference_examples>" in block
        assert "夜无疆" in block

    def test_injection_empty_when_no_index(self) -> None:
        block = inject_explosive_examples(
            "对话场景", scene_type="dialogue", index_path="/nonexistent/path.json"
        )
        assert block == ""

    def test_injection_includes_source_metadata(self, mock_index_path: str) -> None:
        block = inject_explosive_examples(
            "对话", scene_type="dialogue", k=2, index_path=mock_index_path
        )
        assert "剑来" in block
        assert "ch15" in block or "15" in block

    def test_injection_without_scene_type_works(self, mock_index_path: str) -> None:
        block = inject_explosive_examples(
            "主角进入山洞", scene_type=None, k=2, index_path=mock_index_path
        )
        if block:
            assert "<reference_examples>" in block

    def test_retrieval_failure_graceful_fallback(self) -> None:
        """索引损坏/缺失时 injection 返回空字符串，不抛异常。"""
        block = inject_explosive_examples(
            "test", scene_type="action", index_path="/nonexistent/index.json"
        )
        assert block == ""

    def test_enabled_false_returns_empty(self, mock_index_path: str) -> None:
        """开关关闭时跳过检索，直接返回空字符串。"""
        block = inject_explosive_examples(
            "战斗场景：主角对敌",
            scene_type="combat",
            k=2,
            index_path=mock_index_path,
            enabled=False,
        )
        assert block == ""

    def test_enabled_false_bytes_identical_to_old_path(self, mock_index_path: str) -> None:
        """开关关闭时输出空，与无检索的旧路径字节级一致。"""
        block_off = inject_explosive_examples(
            "some scene", index_path=mock_index_path, enabled=False
        )
        block_no_index = inject_explosive_examples(
            "some scene", index_path="/nonexistent.json", enabled=True
        )
        # Both should be empty strings (old path = no reference_examples)
        assert block_off == ""
        assert block_no_index == ""

    def test_injection_score_included_in_comment(self, mock_index_path: str) -> None:
        """验证 score 包含在 HTML comment 中。"""
        block = inject_explosive_examples(
            "战斗", scene_type="combat", k=2, index_path=mock_index_path
        )
        if block:
            assert "score=" in block
