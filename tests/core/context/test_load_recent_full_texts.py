#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""US-001 tests: ContextManager._load_recent_full_texts

Covers acceptance criteria from prd-chapter-context-injection:
- N=1 returns []
- N=2 returns 1 entry (n-1 only)
- N=3 returns 2 entries (n-1, n-2)
- N>=4 returns 3 entries (n-1, n-2, n-3) in ascending order
- N=100 still returns 3 entries
- Missing chapter file: warn + missing=True, no exception
- Empty chapter file: returns text="", word_count=0, missing=False
- All open() calls use UTF-8 encoding (Chinese content roundtrips intact)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ink_writer.core.infra.config import DataModulesConfig
from ink_writer.core.context.context_manager import ContextManager


def _write_chapter(chapters_dir: Path, num: int, body: str) -> Path:
    chapters_dir.mkdir(parents=True, exist_ok=True)
    path = chapters_dir / f"第{num:04d}章.md"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def manager(tmp_path: Path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return ContextManager(cfg)


def test_returns_empty_when_chapter_is_one(manager):
    assert manager._load_recent_full_texts(chapter=1) == []


def test_returns_only_previous_chapter_when_n_is_two(manager):
    chapters_dir = manager.config.chapters_dir
    _write_chapter(chapters_dir, 1, "第一章正文：萧炎踏入云岚宗。")

    result = manager._load_recent_full_texts(chapter=2)

    assert len(result) == 1
    assert result[0]["chapter"] == 1
    assert "云岚宗" in result[0]["text"]
    assert result[0]["word_count"] == len(result[0]["text"])
    assert result[0]["missing"] is False


def test_returns_two_when_n_is_three(manager):
    chapters_dir = manager.config.chapters_dir
    _write_chapter(chapters_dir, 1, "第一章正文")
    _write_chapter(chapters_dir, 2, "第二章正文")

    result = manager._load_recent_full_texts(chapter=3)

    assert [item["chapter"] for item in result] == [1, 2]
    assert all(item["missing"] is False for item in result)


def test_returns_three_when_n_is_four(manager):
    chapters_dir = manager.config.chapters_dir
    for ch in (1, 2, 3):
        _write_chapter(chapters_dir, ch, f"第{ch}章正文：内容{ch}")

    result = manager._load_recent_full_texts(chapter=4)

    assert [item["chapter"] for item in result] == [1, 2, 3]
    assert result[0]["text"].startswith("第1章正文")
    assert result[2]["text"].startswith("第3章正文")


def test_window_is_capped_at_three_for_large_n(manager):
    chapters_dir = manager.config.chapters_dir
    for ch in range(95, 100):
        _write_chapter(chapters_dir, ch, f"第{ch}章")

    result = manager._load_recent_full_texts(chapter=100)

    assert [item["chapter"] for item in result] == [97, 98, 99]


def test_missing_file_does_not_raise(manager, caplog):
    chapters_dir = manager.config.chapters_dir
    # only chapter 2 exists; chapter 1 file missing
    _write_chapter(chapters_dir, 2, "第二章存在")

    with caplog.at_level("WARNING"):
        result = manager._load_recent_full_texts(chapter=3)

    assert [item["chapter"] for item in result] == [1, 2]
    assert result[0]["missing"] is True
    assert result[0]["text"] == ""
    assert result[0]["word_count"] == 0
    assert result[1]["missing"] is False
    assert any(
        "chapter 1" in record.message and "not found" in record.message
        for record in caplog.records
    )


def test_empty_file_returns_zero_word_count(manager):
    chapters_dir = manager.config.chapters_dir
    _write_chapter(chapters_dir, 1, "")

    result = manager._load_recent_full_texts(chapter=2)

    assert len(result) == 1
    assert result[0]["text"] == ""
    assert result[0]["word_count"] == 0
    # Empty content is still "found", not missing
    assert result[0]["missing"] is False


def test_window_zero_returns_empty(manager):
    chapters_dir = manager.config.chapters_dir
    _write_chapter(chapters_dir, 1, "第一章")
    assert manager._load_recent_full_texts(chapter=5, window=0) == []


def test_custom_window_size(manager):
    chapters_dir = manager.config.chapters_dir
    for ch in range(1, 6):
        _write_chapter(chapters_dir, ch, f"ch{ch}")

    result = manager._load_recent_full_texts(chapter=6, window=5)

    assert [item["chapter"] for item in result] == [1, 2, 3, 4, 5]


def test_utf8_chinese_content_roundtrips(manager):
    chapters_dir = manager.config.chapters_dir
    body = "萧炎踏出云岚宗大门，紫衫飘动。\n药老低声道：『此去山高水远。』"
    _write_chapter(chapters_dir, 1, body)

    result = manager._load_recent_full_texts(chapter=2)

    assert result[0]["text"] == body
    assert result[0]["word_count"] == len(body)


def test_large_chapter_file(manager):
    chapters_dir = manager.config.chapters_dir
    big = "斗破苍穹。" * 1000  # ~6000 chars
    _write_chapter(chapters_dir, 1, big)

    result = manager._load_recent_full_texts(chapter=2)

    assert result[0]["text"] == big
    assert result[0]["word_count"] == len(big)
