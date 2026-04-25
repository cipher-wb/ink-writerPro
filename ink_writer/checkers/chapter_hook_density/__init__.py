"""chapter-hook-density-checker — M4 ink-plan 策划期卷骨架钩子密度检查（spec §3.7）。"""

from ink_writer.checkers.chapter_hook_density.checker import (
    check_chapter_hook_density,
)
from ink_writer.checkers.chapter_hook_density.models import (
    ChapterHookDensityReport,
)

__all__ = [
    "ChapterHookDensityReport",
    "check_chapter_hook_density",
]
