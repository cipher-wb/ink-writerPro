"""Platform-aware load_word_limits tests."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from ink_writer.core.preferences import (
    load_word_limits,
    MIN_WORDS_FLOOR,
    MIN_WORDS_FLOOR_FANQIE,
    DEFAULT_MAX_WORDS_HARD,
    DEFAULT_MAX_WORDS_HARD_FANQIE,
)


def _make_project(tmp_path: Path, *, platform: str | None = None, chapter_words: int | None = None, corrupt_state: bool = False) -> Path:
    """Build a temp project with optional state.json + preferences.json."""
    (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)
    if platform is not None:
        state = {"project_info": {"platform": platform}, "progress": {"current_chapter": 0}}
        (tmp_path / ".ink" / "state.json").write_text(
            json.dumps(state, ensure_ascii=False) if not corrupt_state else "{not json",
            encoding="utf-8",
        )
    if chapter_words is not None:
        prefs = {"pacing": {"chapter_words": chapter_words}}
        (tmp_path / ".ink" / "preferences.json").write_text(
            json.dumps(prefs, ensure_ascii=False), encoding="utf-8",
        )
    return tmp_path


def test_constants_exist() -> None:
    assert MIN_WORDS_FLOOR == 2200
    assert MIN_WORDS_FLOOR_FANQIE == 1500
    assert DEFAULT_MAX_WORDS_HARD == 5000
    assert DEFAULT_MAX_WORDS_HARD_FANQIE == 2000


def test_qidian_with_chapter_words_3000(tmp_path: Path) -> None:
    p = _make_project(tmp_path, platform="qidian", chapter_words=3000)
    assert load_word_limits(p) == (2500, 3500)


def test_qidian_unchanged_default_when_no_preferences(tmp_path: Path) -> None:
    p = _make_project(tmp_path, platform="qidian")
    assert load_word_limits(p) == (2200, 5000)


def test_fanqie_with_chapter_words_1500(tmp_path: Path) -> None:
    p = _make_project(tmp_path, platform="fanqie", chapter_words=1500)
    assert load_word_limits(p) == (1500, 2000)


def test_fanqie_no_preferences_uses_platform_fallback(tmp_path: Path) -> None:
    p = _make_project(tmp_path, platform="fanqie")
    assert load_word_limits(p) == (1500, 2000)


def test_state_json_missing_defaults_qidian(tmp_path: Path) -> None:
    # No state.json at all → must default to qidian-strict
    assert load_word_limits(tmp_path) == (2200, 5000)


def test_state_json_corrupt_defaults_qidian(tmp_path: Path) -> None:
    p = _make_project(tmp_path, platform="qidian", corrupt_state=True)
    assert load_word_limits(p) == (2200, 5000)


def test_invalid_platform_value_falls_back_qidian(tmp_path: Path) -> None:
    p = _make_project(tmp_path, platform="windows")  # invalid value
    assert load_word_limits(p) == (2200, 5000)


def test_fanqie_high_chapter_words_overrides_floor(tmp_path: Path) -> None:
    # chapter_words=2000 → min=max(1500, 2000-500)=1500, max=2500
    p = _make_project(tmp_path, platform="fanqie", chapter_words=2000)
    assert load_word_limits(p) == (1500, 2500)


def test_fanqie_low_chapter_words_clamped_to_floor(tmp_path: Path) -> None:
    # chapter_words=1000 → min=max(1500, 500)=1500, max=1500 (defensive: max < min → max := min)
    p = _make_project(tmp_path, platform="fanqie", chapter_words=1000)
    assert load_word_limits(p) == (1500, 1500)
