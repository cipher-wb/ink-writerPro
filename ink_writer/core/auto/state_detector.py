# ink_writer/core/auto/state_detector.py
"""Detect ink-writer project state in a working directory.

Used by ink-auto to decide whether to dispatch to init / plan / main loop.
"""
from __future__ import annotations

import enum
import json
from pathlib import Path


class ProjectState(enum.Enum):
    S0_UNINIT = "S0_UNINIT"
    S1_NO_OUTLINE = "S1_NO_OUTLINE"
    S2_WRITING = "S2_WRITING"
    S3_COMPLETED = "S3_COMPLETED"


def detect_project_state(cwd: Path | str) -> ProjectState:
    cwd = Path(cwd)
    state_path = cwd / ".ink" / "state.json"
    if not state_path.is_file():
        return ProjectState.S0_UNINIT

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ProjectState.S0_UNINIT

    progress = state.get("progress", {}) if isinstance(state, dict) else {}
    if progress.get("is_completed") is True:
        return ProjectState.S3_COMPLETED

    outline_dir = cwd / "大纲"
    if not outline_dir.is_dir():
        return ProjectState.S1_NO_OUTLINE
    # 必须存在实际章纲文件（第N章*.md），仅 爽点规划.md / 总纲.md 不算
    chapter_outlines = list(outline_dir.glob("第*章*.md"))
    if not chapter_outlines:
        return ProjectState.S1_NO_OUTLINE

    return ProjectState.S2_WRITING
