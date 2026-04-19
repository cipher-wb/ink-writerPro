#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""US-002 tests: context pack data contract for recent_full_texts + injection_policy.

Covers acceptance criteria from prd-chapter-context-injection:
- recent_full_texts field exists on core with correct schema
- recent_summaries window shifts to [n-10, n-4] once N >= 4
- recent_summaries never overlaps with recent_full_texts
- injection_policy metadata is exposed with full_text_window / summary_range / hard_inject
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


def _write_summary(summaries_dir: Path, num: int, body: str) -> Path:
    summaries_dir.mkdir(parents=True, exist_ok=True)
    path = summaries_dir / f"ch{num:04d}.md"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def manager(tmp_path: Path) -> ContextManager:
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return ContextManager(cfg)


def _build_pack(manager: ContextManager, chapter: int) -> dict:
    pack = manager._build_pack(chapter)
    assert "core" in pack and "meta" in pack
    return pack


def test_core_pack_exposes_recent_full_texts_field(manager):
    chapters_dir = manager.config.chapters_dir
    _write_chapter(chapters_dir, 1, "第一章")
    _write_chapter(chapters_dir, 2, "第二章")

    pack = _build_pack(manager, 3)

    assert "recent_full_texts" in pack["core"]
    texts = pack["core"]["recent_full_texts"]
    assert isinstance(texts, list)
    assert [entry["chapter"] for entry in texts] == [1, 2]
    for entry in texts:
        assert set(entry.keys()) >= {"chapter", "text", "word_count", "missing"}
        assert isinstance(entry["chapter"], int)
        assert isinstance(entry["text"], str)
        assert isinstance(entry["word_count"], int)
        assert isinstance(entry["missing"], bool)


def test_injection_policy_metadata_present(manager):
    pack = _build_pack(manager, 5)

    policy = pack["meta"].get("injection_policy")
    assert isinstance(policy, dict)
    assert policy["full_text_window"] == 3
    assert policy["summary_window"] == 10
    assert policy["hard_inject"] is True
    summary_range = policy["summary_range"]
    assert isinstance(summary_range, list) and len(summary_range) == 2


def test_recent_summaries_window_shifts_to_n_minus_10_through_n_minus_4(manager):
    summaries_dir = manager.config.ink_dir / "summaries"
    # Provide summaries for chapters 1..14 so we can assert the window
    for ch in range(1, 15):
        _write_summary(summaries_dir, ch, f"## 剧情摘要\n第{ch}章摘要内容")

    pack = _build_pack(manager, 15)
    summaries = pack["core"]["recent_summaries"]
    chapters_loaded = [entry["chapter"] for entry in summaries]

    # Expected range: [n-10, n-4] = [5, 11] inclusive, 7 chapters total
    assert chapters_loaded == [5, 6, 7, 8, 9, 10, 11]


def test_recent_summaries_excludes_full_text_window(manager):
    summaries_dir = manager.config.ink_dir / "summaries"
    for ch in range(1, 10):
        _write_summary(summaries_dir, ch, f"第{ch}章摘要")

    chapters_dir = manager.config.chapters_dir
    for ch in (7, 8, 9):
        _write_chapter(chapters_dir, ch, f"第{ch}章正文")

    pack = _build_pack(manager, 10)
    summary_chapters = {entry["chapter"] for entry in pack["core"]["recent_summaries"]}
    full_text_chapters = {entry["chapter"] for entry in pack["core"]["recent_full_texts"]}

    # Orthogonality: no overlap allowed
    assert summary_chapters.isdisjoint(full_text_chapters)
    # And full texts cover exactly n-1/n-2/n-3
    assert full_text_chapters == {7, 8, 9}


def test_early_chapters_have_no_summaries_and_empty_range(manager):
    pack = _build_pack(manager, 1)

    assert pack["core"]["recent_summaries"] == []
    assert pack["core"]["recent_full_texts"] == []
    policy = pack["meta"]["injection_policy"]
    assert policy["summary_range"] == [0, 0]


def test_chapter_equal_to_full_text_window_still_has_empty_summary_range(manager):
    """When chapter <= full_text_window, recent_summaries must stay empty."""
    summaries_dir = manager.config.ink_dir / "summaries"
    _write_summary(summaries_dir, 1, "第1章摘要")
    _write_summary(summaries_dir, 2, "第2章摘要")

    pack = _build_pack(manager, 3)

    assert pack["core"]["recent_summaries"] == []
    policy = pack["meta"]["injection_policy"]
    assert policy["summary_range"] == [0, 0]


def test_summary_range_reflects_actual_span_once_past_full_text_window(manager):
    pack = _build_pack(manager, 5)

    policy = pack["meta"]["injection_policy"]
    # full_text_window=3, so n-4 = 1; summary_range upper bound = 1
    # summary_range_start = max(0, 5 - 10) = 0
    assert policy["summary_range"] == [0, 1]


def test_injection_policy_propagates_to_assembled_payload(manager):
    payload = manager.build_context(
        chapter=6, use_snapshot=False, save_snapshot=False
    )
    policy = payload["meta"].get("injection_policy")
    assert isinstance(policy, dict)
    assert policy["full_text_window"] == 3
    assert policy["hard_inject"] is True
