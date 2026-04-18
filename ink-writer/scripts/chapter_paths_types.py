#!/usr/bin/env python3
"""
chapter_paths_types - Shared primitives for chapter path / outline resolution.

This module intentionally has **no** imports from `chapter_paths` or
`chapter_outline_loader`; it is the bottom layer that both sides depend on,
which breaks the historical `chapter_paths <-> chapter_outline_loader` import
cycle (US-025, F-012).

Contents:
    - Chapter-number regex constants
    - Volume-layout configuration (INK_CHAPTERS_PER_VOLUME)
    - `volume_num_for_chapter()` pure helper
    - `CHAPTER_TITLE_MAX_LENGTH` constant

Any helper that needs *both* chapter path logic *and* outline text parsing
belongs in `chapter_paths` or `chapter_outline_loader`, not here.
"""

from __future__ import annotations

import os
import re

# ---------------------------------------------------------------------------
# Volume layout configuration
# ---------------------------------------------------------------------------

_DEFAULT_CPV = int(os.environ.get("INK_CHAPTERS_PER_VOLUME", "50"))

# ---------------------------------------------------------------------------
# Filename / outline regex primitives (shared by both sides of the old cycle)
# ---------------------------------------------------------------------------

CHAPTER_NUM_RE = re.compile(r"第(?P<num>\d+)章")
OUTLINE_HEADING_RE = re.compile(
    r"^#{1,6}\s*第\s*(?P<num>\d+)\s*章[：:]\s*(?P<title>.+?)\s*$",
    re.MULTILINE,
)
SPLIT_OUTLINE_FILENAME_RE = re.compile(
    r"^第0*(?P<num>\d+)章[-—_ ]+(?P<title>.+?)\.md$"
)

CHAPTER_TITLE_MAX_LENGTH = 60  # 章节标题在文件名中的最大字符数


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def volume_num_for_chapter(
    chapter_num: int, *, chapters_per_volume: int = _DEFAULT_CPV
) -> int:
    """Return the 1-indexed volume number that owns ``chapter_num``.

    Pure function — no filesystem / outline dependencies. Used by both
    ``chapter_paths`` and ``chapter_outline_loader``.
    """
    if chapter_num <= 0:
        raise ValueError("chapter_num must be >= 1")
    return (chapter_num - 1) // chapters_per_volume + 1
