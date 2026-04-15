"""US-002: Verify no silent degradation when config.enabled=true and index is missing."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ink_writer.editor_wisdom.config import EditorWisdomConfig
from ink_writer.editor_wisdom.exceptions import EditorWisdomIndexMissingError


def test_retriever_raises_on_missing_index(tmp_path):
    """Retriever() raises EditorWisdomIndexMissingError when vector index files are absent."""
    from ink_writer.editor_wisdom.retriever import Retriever

    with pytest.raises(EditorWisdomIndexMissingError, match="index files missing"):
        Retriever(index_dir=tmp_path)


def test_context_injection_propagates_when_enabled():
    """With enabled=True, context_injection re-raises EditorWisdomIndexMissingError."""
    from ink_writer.editor_wisdom.context_injection import build_editor_wisdom_section

    config = EditorWisdomConfig(enabled=True)

    with patch(
        "ink_writer.editor_wisdom.context_injection.Retriever",
        side_effect=EditorWisdomIndexMissingError("missing index"),
    ):
        with pytest.raises(EditorWisdomIndexMissingError):
            build_editor_wisdom_section(
                chapter_outline="测试",
                config=config,
            )


def test_context_injection_swallows_when_disabled():
    """With enabled=False, context_injection returns empty section without raising."""
    from ink_writer.editor_wisdom.context_injection import build_editor_wisdom_section

    config = EditorWisdomConfig(enabled=False)
    section = build_editor_wisdom_section(
        chapter_outline="测试",
        config=config,
    )
    assert section.empty is True


def test_writer_injection_propagates_when_enabled():
    """With enabled=True, writer_injection re-raises EditorWisdomIndexMissingError."""
    from ink_writer.editor_wisdom.writer_injection import build_writer_constraints

    config = EditorWisdomConfig(enabled=True)

    with patch(
        "ink_writer.editor_wisdom.writer_injection.Retriever",
        side_effect=EditorWisdomIndexMissingError("missing index"),
    ):
        with pytest.raises(EditorWisdomIndexMissingError):
            build_writer_constraints(
                chapter_outline="测试",
                config=config,
            )


def test_writer_injection_swallows_when_disabled():
    """With enabled=False, writer_injection returns empty section without raising."""
    from ink_writer.editor_wisdom.writer_injection import build_writer_constraints

    config = EditorWisdomConfig(enabled=False)
    result = build_writer_constraints(
        chapter_outline="测试",
        config=config,
    )
    assert result.empty is True


def test_checker_raises_on_empty_rules_when_enabled():
    """With enabled=True, checker raises EditorWisdomIndexMissingError on empty rules."""
    from ink_writer.editor_wisdom.checker import check_chapter

    config = EditorWisdomConfig(enabled=True)
    with pytest.raises(EditorWisdomIndexMissingError):
        check_chapter("测试正文", 1, [], config=config)


def test_checker_returns_perfect_on_empty_rules_when_disabled():
    """With enabled=False, checker returns score=1.0 on empty rules."""
    from ink_writer.editor_wisdom.checker import check_chapter

    config = EditorWisdomConfig(enabled=False)
    result = check_chapter("测试正文", 1, [], config=config)
    assert result["score"] == 1.0
    assert result["violations"] == []
