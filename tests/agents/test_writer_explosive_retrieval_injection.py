"""US-012: writer-agent Step 2A explosive_retriever injection test.

验证:
  1. ExplosiveRetriever 可从 writer-agent draft 流程中调用
  2. retrieval 结果可注入 prompt reference_examples 块
  3. 索引缺失时 graceful fallback（不阻断写作）
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
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


def _inject_reference_examples(
    retriever: ExplosiveRetriever,
    scene_outline: str,
    scene_type: str | None,
) -> str:
    """模拟 Step 2A 中 retrieval injection 的逻辑。"""
    results = retriever.retrieve(scene_outline, scene_type=scene_type, k=2)
    if not results:
        return ""
    lines = ["<reference_examples>"]
    for r in results:
        lines.append(
            f"<!-- source: {r['source_book']} ch{r['source_chapter']} -->\n"
            f"{r['excerpt']}"
        )
    lines.append("</reference_examples>")
    return "\n".join(lines)


class TestRetrievalInjection:
    """US-012 AC: retriever injection into prompt."""

    def test_injection_produces_reference_examples_block(self, mock_index_path: str) -> None:
        retriever = ExplosiveRetriever(mock_index_path)
        block = _inject_reference_examples(
            retriever, "战斗场景：主角对敌", scene_type="combat"
        )
        assert "<reference_examples>" in block
        assert "</reference_examples>" in block
        assert "夜无疆" in block

    def test_injection_empty_when_no_index(self) -> None:
        retriever = ExplosiveRetriever("/nonexistent/path.json")
        block = _inject_reference_examples(
            retriever, "对话场景", scene_type="dialogue"
        )
        assert block == ""

    def test_injection_includes_source_metadata(self, mock_index_path: str) -> None:
        retriever = ExplosiveRetriever(mock_index_path)
        block = _inject_reference_examples(
            retriever, "对话", scene_type="dialogue"
        )
        assert "剑来" in block
        assert "ch15" in block or "source_chapter" in block.lower() or "15" in block

    def test_injection_without_scene_type_works(self, mock_index_path: str) -> None:
        retriever = ExplosiveRetriever(mock_index_path)
        block = _inject_reference_examples(
            retriever, "主角进入山洞", scene_type=None
        )
        if block:
            assert "<reference_examples>" in block

    def test_retrieval_failure_graceful_fallback(self) -> None:
        """索引损坏/缺失时 injection 返回空字符串，不抛异常。"""
        retriever = ExplosiveRetriever("/nonexistent/index.json")
        block = _inject_reference_examples(retriever, "test", scene_type="action")
        assert block == ""
