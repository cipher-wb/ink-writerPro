"""FIX-18 P5c: character progression context injection helpers."""

from ink_writer.progression.context_injection import (
    DEFAULT_MAX_ROWS_PER_CHAR,
    build_progression_summary,
    render_progression_summary_md,
)

__all__ = [
    "DEFAULT_MAX_ROWS_PER_CHAR",
    "build_progression_summary",
    "render_progression_summary_md",
]
