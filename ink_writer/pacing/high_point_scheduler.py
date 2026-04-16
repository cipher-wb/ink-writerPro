"""High-point scheduler: proactive cool-point recipe per chapter.

Decides each chapter's high-point type, intensity, and payoff window based on
chapter position, volume arc, and recent high-point history.  Wired into
ink-plan as a hard constraint before outline generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ── Cool-point type taxonomy (aligned with cool-points-guide.md) ────────────
HIGH_POINT_TYPES: list[str] = [
    "face_slap",          # 装逼打脸
    "hidden_strength",    # 扮猪吃虎
    "level_up_kill",      # 越级反杀
    "authority_challenge", # 打脸权威
    "villain_fail",       # 反派翻车
    "sweet_surprise",     # 甜蜜超预期
]

# ── Intensity levels ────────────────────────────────────────────────────────
INTENSITY_MINOR = "minor"        # 小爽点: single mode, daily face-slap
INTENSITY_COMBO = "combo"        # 组合爽点: 2+ modes stacked
INTENSITY_MILESTONE = "milestone"  # 里程碑爽点: changes protagonist status

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "high-point-scheduler.yaml"
)


@dataclass
class HighPointRecord:
    """A past chapter's high-point summary."""
    chapter_no: int
    high_point_type: str | None = None
    intensity: str | None = None
    had_high_point: bool = True


@dataclass
class HighPointRecipe:
    """Scheduler output: what this chapter should deliver."""
    high_point_type: str
    intensity: str
    payoff_window: int
    require_high_point: bool = True
    rationale: str = ""


@dataclass
class SchedulerConfig:
    max_consecutive_no_hp: int = 2
    combo_window: int = 5
    milestone_window: int = 12
    type_repeat_limit: int = 2
    climax_zone_start: float = 0.85
    climax_zone_end: float = 1.0
    opening_boost_chapters: int = 3

    @classmethod
    def from_yaml(cls, path: Path | str | None = None) -> SchedulerConfig:
        if path is None:
            path = DEFAULT_CONFIG_PATH
        path = Path(path)
        if not path.exists():
            return cls()
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return cls()
        return cls(
            max_consecutive_no_hp=int(raw.get("max_consecutive_no_hp", 2)),
            combo_window=int(raw.get("combo_window", 5)),
            milestone_window=int(raw.get("milestone_window", 12)),
            type_repeat_limit=int(raw.get("type_repeat_limit", 2)),
            climax_zone_start=float(raw.get("climax_zone_start", 0.85)),
            climax_zone_end=float(raw.get("climax_zone_end", 1.0)),
            opening_boost_chapters=int(raw.get("opening_boost_chapters", 3)),
        )


# ── Volume arc intensity curve ──────────────────────────────────────────────

def _base_intensity(volume_position: float, config: SchedulerConfig) -> str:
    """Determine base intensity from volume arc position."""
    if volume_position >= config.climax_zone_start:
        return INTENSITY_MILESTONE
    if volume_position <= 0.15:
        return INTENSITY_MINOR
    if 0.4 <= volume_position <= 0.6:
        return INTENSITY_COMBO
    return INTENSITY_MINOR


def _consecutive_no_hp(history: list[HighPointRecord]) -> int:
    """Count how many trailing chapters had no high-point."""
    count = 0
    for rec in reversed(history):
        if not rec.had_high_point or rec.high_point_type is None:
            count += 1
        else:
            break
    return count


def _chapters_since_intensity(
    history: list[HighPointRecord], target: str,
) -> int | None:
    """How many chapters ago the last occurrence of *target* intensity was."""
    for i, rec in enumerate(reversed(history)):
        if rec.intensity == target:
            return i + 1
    return None


def _recent_type_counts(
    history: list[HighPointRecord], window: int = 5,
) -> dict[str, int]:
    """Count high-point types in the most recent *window* chapters."""
    counts: dict[str, int] = {}
    for rec in history[-window:]:
        if rec.high_point_type:
            counts[rec.high_point_type] = counts.get(rec.high_point_type, 0) + 1
    return counts


def _pick_type(
    history: list[HighPointRecord],
    config: SchedulerConfig,
    volume_position: float,
) -> str:
    """Pick a high-point type avoiding recent repetition."""
    counts = _recent_type_counts(history, window=config.combo_window)

    overused = {
        t for t, c in counts.items() if c >= config.type_repeat_limit
    }
    candidates = [t for t in HIGH_POINT_TYPES if t not in overused]
    if not candidates:
        candidates = list(HIGH_POINT_TYPES)

    if volume_position >= config.climax_zone_start:
        preferred = ["level_up_kill", "villain_fail", "face_slap"]
        for p in preferred:
            if p in candidates:
                return p

    if volume_position <= 0.15:
        preferred = ["hidden_strength", "face_slap", "sweet_surprise"]
        for p in preferred:
            if p in candidates:
                return p

    last_used = None
    for rec in reversed(history):
        if rec.high_point_type:
            last_used = rec.high_point_type
            break

    for c in candidates:
        if c != last_used:
            return c
    return candidates[0]


def _payoff_window(intensity: str) -> int:
    """How many chapters the payoff chain should span."""
    if intensity == INTENSITY_MILESTONE:
        return 3
    if intensity == INTENSITY_COMBO:
        return 2
    return 1


# ── Public API ──────────────────────────────────────────────────────────────

def schedule_high_point(
    chapter_no: int,
    volume_position: float,
    last_5_chapter_high_points: list[dict[str, Any] | HighPointRecord],
    *,
    config: SchedulerConfig | None = None,
) -> HighPointRecipe:
    """Decide this chapter's high-point recipe.

    Args:
        chapter_no: Current chapter number (1-based).
        volume_position: 0.0 (volume start) to 1.0 (volume end).
        last_5_chapter_high_points: Recent history (up to 5 entries).
            Each entry is either a HighPointRecord or a dict with keys:
            chapter_no, high_point_type, intensity, had_high_point.
        config: Scheduler configuration (loaded from YAML if None).

    Returns:
        HighPointRecipe with type, intensity, payoff_window, and rationale.
    """
    if config is None:
        config = SchedulerConfig.from_yaml()

    volume_position = max(0.0, min(1.0, volume_position))

    history: list[HighPointRecord] = []
    for item in last_5_chapter_high_points:
        if isinstance(item, HighPointRecord):
            history.append(item)
        elif isinstance(item, dict):
            history.append(HighPointRecord(
                chapter_no=item.get("chapter_no", 0),
                high_point_type=item.get("high_point_type"),
                intensity=item.get("intensity"),
                had_high_point=item.get("had_high_point", True),
            ))

    consecutive_gap = _consecutive_no_hp(history)
    force_hp = consecutive_gap >= config.max_consecutive_no_hp
    is_opening = chapter_no <= config.opening_boost_chapters
    is_climax = volume_position >= config.climax_zone_start

    rationale_parts: list[str] = []

    # Determine intensity
    intensity = _base_intensity(volume_position, config)

    # Upgrade if combo/milestone overdue
    since_combo = _chapters_since_intensity(history, INTENSITY_COMBO)
    since_milestone = _chapters_since_intensity(history, INTENSITY_MILESTONE)

    if since_combo is None or since_combo >= config.combo_window:
        if intensity == INTENSITY_MINOR:
            intensity = INTENSITY_COMBO
            rationale_parts.append(
                f"升级为组合爽点：距上次组合已过{since_combo or '5+'}章"
            )

    if since_milestone is None or since_milestone >= config.milestone_window:
        intensity = INTENSITY_MILESTONE
        rationale_parts.append(
            f"升级为里程碑爽点：距上次里程碑已过{since_milestone or '12+'}章"
        )

    if is_climax:
        intensity = INTENSITY_MILESTONE
        rationale_parts.append("高潮区间：强制里程碑爽点")

    if is_opening:
        if intensity == INTENSITY_MINOR:
            intensity = INTENSITY_COMBO
        rationale_parts.append(f"开篇黄金{config.opening_boost_chapters}章加强")

    # Force high-point if gap too long
    require_hp = True
    if force_hp:
        rationale_parts.append(
            f"已连续{consecutive_gap}章无爽点，强制要求"
        )
    elif not is_opening and not is_climax and not force_hp:
        if 0.15 < volume_position < 0.85 and consecutive_gap == 0:
            require_hp = True
            rationale_parts.append("常规章节：建议保持爽点")

    hp_type = _pick_type(history, config, volume_position)
    pw = _payoff_window(intensity)

    if not rationale_parts:
        rationale_parts.append("常规调度")

    return HighPointRecipe(
        high_point_type=hp_type,
        intensity=intensity,
        payoff_window=pw,
        require_high_point=require_hp,
        rationale="；".join(rationale_parts),
    )
