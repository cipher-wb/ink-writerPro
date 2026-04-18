"""
ink_writer.chapter_paths_types - Shared primitives for chapter path / outline
resolution (US-025, F-012).

This module lives inside the ``ink_writer`` package so code that already uses
the canonical ``from ink_writer.X import Y`` style can pull the shared
primitives without reaching into the legacy ``ink-writer/scripts/`` tree.

The authoritative implementation lives in ``ink-writer/scripts/chapter_paths_types.py``.
We re-export its public API here so both consumers resolve to the same
``volume_num_for_chapter`` / regex constants.

US-025 note: the whole point of this module is to *break* the historical
``chapter_paths <-> chapter_outline_loader`` import cycle. It intentionally
has **no** dependency on either side of that cycle.
"""

from __future__ import annotations

import os
import re

# ---------------------------------------------------------------------------
# Volume layout configuration
# ---------------------------------------------------------------------------

_DEFAULT_CPV = int(os.environ.get("INK_CHAPTERS_PER_VOLUME", "50"))

# ---------------------------------------------------------------------------
# Filename / outline regex primitives
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

    Pure function — no filesystem / outline dependencies. Mirrors the helper
    exported by ``scripts/chapter_paths_types.py`` so both the
    ``ink_writer.*`` and legacy ``scripts.*`` import paths share semantics.
    """
    if chapter_num <= 0:
        raise ValueError("chapter_num must be >= 1")
    return (chapter_num - 1) // chapters_per_volume + 1


__all__ = [
    "CHAPTER_NUM_RE",
    "CHAPTER_TITLE_MAX_LENGTH",
    "OUTLINE_HEADING_RE",
    "SPLIT_OUTLINE_FILENAME_RE",
    "volume_num_for_chapter",
]
