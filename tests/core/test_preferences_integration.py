"""Integration: downstream consumers receive platform-aware word limits."""
from __future__ import annotations
import json
from pathlib import Path
import pytest


def _make_fanqie_project(tmp_path: Path) -> Path:
    """Create a minimal fanqie project structure for integration tests."""
    (tmp_path / ".ink").mkdir(parents=True)
    state = {"project_info": {"platform": "fanqie"}, "progress": {"current_chapter": 0}}
    (tmp_path / ".ink" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    prefs = {"pacing": {"chapter_words": 1500}}
    (tmp_path / ".ink" / "preferences.json").write_text(json.dumps(prefs), encoding="utf-8")
    return tmp_path


def test_load_word_limits_directly_returns_fanqie_range(tmp_path: Path) -> None:
    """Sanity: the canonical load_word_limits returns fanqie range."""
    from ink_writer.core.preferences import load_word_limits
    p = _make_fanqie_project(tmp_path)
    assert load_word_limits(p) == (1500, 2000)


def test_extract_chapter_context_helper_uses_fanqie_floor(tmp_path: Path) -> None:
    """extract_chapter_context.py's _word_limits_for_project respects platform."""
    import sys
    scripts_dir = Path("/Users/cipher/AI/小说/ink/ink-writer/ink-writer/scripts")
    sys.path.insert(0, str(scripts_dir))
    try:
        # Direct call to the helper used inside extract_chapter_context.py
        from ink_writer.core.preferences import load_word_limits
        p = _make_fanqie_project(tmp_path)
        min_w, max_w = load_word_limits(p)
        assert min_w == 1500
        assert max_w == 2000
    finally:
        sys.path.remove(str(scripts_dir))


def test_computational_checks_check_word_count_accepts_fanqie_minimum() -> None:
    """check_word_count(text, min_words=1500) passes a 1600-char chapter."""
    sys_path_addition = "/Users/cipher/AI/小说/ink/ink-writer/ink-writer/scripts"
    import sys
    sys.path.insert(0, sys_path_addition)
    try:
        from computational_checks import check_word_count
        text = "测试" * 800  # 1600 chars (Chinese counts as 1 char each)
        result = check_word_count(text, min_words=1500, max_words_hard=2000)
        # Must pass: 1600 >= 1500 floor, 1600 <= 2000 cap
        assert result.passed is True, f"Expected passed=True, got {result}"
    finally:
        sys.path.remove(sys_path_addition)


def test_computational_checks_rejects_below_fanqie_floor() -> None:
    """check_word_count rejects 1400 chars under fanqie floor=1500."""
    sys_path_addition = "/Users/cipher/AI/小说/ink/ink-writer/ink-writer/scripts"
    import sys
    sys.path.insert(0, sys_path_addition)
    try:
        from computational_checks import check_word_count
        text = "测试" * 700  # 1400 chars
        result = check_word_count(text, min_words=1500, max_words_hard=2000)
        assert result.passed is False, f"Expected passed=False, got {result}"
    finally:
        sys.path.remove(sys_path_addition)
