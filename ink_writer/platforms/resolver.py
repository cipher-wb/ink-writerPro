"""Platform mode resolution.

Reads platform from state.json → project_info.platform.
Defaults to qidian when missing or state.json absent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PLATFORM_QIDIAN = "qidian"
PLATFORM_FANQIE = "fanqie"

VALID_PLATFORMS = {PLATFORM_QIDIAN, PLATFORM_FANQIE}

PLATFORM_LABELS = {
    PLATFORM_QIDIAN: "起点中文网",
    PLATFORM_FANQIE: "番茄小说",
}

PLATFORM_DEFAULTS = {
    PLATFORM_QIDIAN: {
        "target_chapters": 600,
        "target_words": 2_000_000,
        "chapter_word_count": 3000,
        "target_reader": "25-35岁男性老白读者",
    },
    PLATFORM_FANQIE: {
        "target_chapters": 800,
        "target_words": 1_200_000,
        "chapter_word_count": 1500,
        "target_reader": "35-55岁下沉市场男性",
    },
}


def get_platform(project_root: str | Path) -> str:
    """Read platform from state.json. Defaults to qidian."""
    root = Path(project_root)
    state_path = root / ".ink" / "state.json"
    if not state_path.exists():
        return PLATFORM_QIDIAN
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return PLATFORM_QIDIAN
    platform = (state.get("project_info") or {}).get("platform")
    if platform in VALID_PLATFORMS:
        return platform
    # Migrate legacy values
    if platform in ("起点", "起点中文网"):
        return PLATFORM_QIDIAN
    return PLATFORM_QIDIAN


def resolve_platform_config(
    raw: dict[str, Any],
    platform: str,
) -> dict[str, Any]:
    """Extract platform-specific config from a dict with optional `platforms:` block.

    If `raw` has a `platforms` key, merge `platforms.<platform>` over
    the top-level keys (platform values win). If `platforms` key is
    absent, return `raw` unchanged.
    """
    platforms_block = raw.get("platforms")
    if not isinstance(platforms_block, dict):
        return raw
    platform_overrides = platforms_block.get(platform)
    if not isinstance(platform_overrides, dict):
        return raw
    merged = dict(raw)
    merged.update(platform_overrides)
    return merged
