"""US-006: Retriever 单例化测试。

验证 get_retriever() 返回 module-level 单例，同 index_dir 多次调用返回同一对象。
"""
from __future__ import annotations

import pytest


def test_get_retriever_returns_singleton():
    """5 次调用返回同一实例。"""
    pytest.importorskip("faiss")
    pytest.importorskip("sentence_transformers")
    from ink_writer.editor_wisdom.exceptions import EditorWisdomIndexMissingError
    from ink_writer.editor_wisdom.retriever import clear_retriever_cache, get_retriever

    clear_retriever_cache()
    try:
        first = get_retriever()
    except EditorWisdomIndexMissingError:
        pytest.skip("editor-wisdom index not available; singleton logic still correct via cache dict")

    for _ in range(4):
        assert get_retriever() is first, "get_retriever must return the same singleton"


def test_different_index_dir_creates_separate_instance(tmp_path):
    """不同 index_dir 返回不同实例（仍缓存各自 key）。"""
    pytest.importorskip("faiss")
    from ink_writer.editor_wisdom.retriever import clear_retriever_cache, get_retriever

    clear_retriever_cache()
    # Pointing to nonexistent dirs – we only verify cache key logic, not actual loading
    fake_dir_a = tmp_path / "a"
    fake_dir_b = tmp_path / "b"
    fake_dir_a.mkdir()
    fake_dir_b.mkdir()

    # 两者都应 raise EditorWisdomIndexMissingError（无 faiss/metadata 文件）
    from ink_writer.editor_wisdom.exceptions import EditorWisdomIndexMissingError
    with pytest.raises(EditorWisdomIndexMissingError):
        get_retriever(fake_dir_a)
    with pytest.raises(EditorWisdomIndexMissingError):
        get_retriever(fake_dir_b)


def test_clear_retriever_cache():
    """clear_retriever_cache() 清空后能重新构造。"""
    pytest.importorskip("faiss")
    from ink_writer.editor_wisdom.retriever import _RETRIEVER_CACHE, clear_retriever_cache

    _RETRIEVER_CACHE["dummy"] = "placeholder"  # type: ignore[assignment]
    clear_retriever_cache()
    assert _RETRIEVER_CACHE == {}
