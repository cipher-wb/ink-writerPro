#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""US-006 E2E fixture: preferences.json → load_word_limits → check_word_count 全链路

验收场景（来自 PRD tasks/prd-chapter-word-limit-hard-cap.md, AC #6）：

    创建 test fixture 项目 preferences.json 配置 chapter_words=3000，
    构造 3800 字章节正文，走 check_word_count 应得 severity='hard'；
    构造 2800 字应通过。

同时守护零回归红线：硬下限 2200 行为在全链路保持字节级一致，
任何低于 2200 字的样本都必须以 severity='hard' 被阻断（与 v22 及之前版本一致）。
"""
from __future__ import annotations

import json
from pathlib import Path

from computational_checks import check_word_count
from ink_writer.core.preferences import load_word_limits


def _write_prefs(project_root: Path, payload: dict) -> Path:
    ink_dir = project_root / ".ink"
    ink_dir.mkdir(parents=True, exist_ok=True)
    prefs = ink_dir / "preferences.json"
    prefs.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return prefs


def test_e2e_chapter_words_3000_3800_chars_hard_fail(tmp_path: Path) -> None:
    """fixture 项目 preferences chapter_words=3000，3800 字正文 → severity='hard'."""
    _write_prefs(tmp_path, {"pacing": {"chapter_words": 3000}})
    min_words, max_hard = load_word_limits(tmp_path)
    assert (min_words, max_hard) == (2500, 3500)

    text = "字" * 3800  # 超出 max_hard=3500
    result = check_word_count(text, min_words=min_words, max_words_hard=max_hard)
    assert result.passed is False
    assert result.severity == "hard"
    assert "3800" in result.message
    assert "3500" in result.message


def test_e2e_chapter_words_3000_2800_chars_pass(tmp_path: Path) -> None:
    """fixture 项目 preferences chapter_words=3000，2800 字正文 → 通过（区间内）."""
    _write_prefs(tmp_path, {"pacing": {"chapter_words": 3000}})
    min_words, max_hard = load_word_limits(tmp_path)

    text = "字" * 2800  # 2500 <= 2800 <= 3500
    result = check_word_count(text, min_words=min_words, max_words_hard=max_hard)
    assert result.passed is True


def test_e2e_chapter_words_3000_below_min_hard_fail(tmp_path: Path) -> None:
    """零回归：低于 min_words 仍以 severity='hard' 阻断（下限红线不得弱化）."""
    _write_prefs(tmp_path, {"pacing": {"chapter_words": 3000}})
    min_words, max_hard = load_word_limits(tmp_path)

    text = "字" * 2400  # < min_words=2500
    result = check_word_count(text, min_words=min_words, max_words_hard=max_hard)
    assert result.passed is False
    assert result.severity == "hard"


def test_e2e_no_preferences_uses_default_2200_5000(tmp_path: Path) -> None:
    """无 preferences.json → 默认 (2200, 5000) 对齐 US-001/US-002 默认态."""
    min_words, max_hard = load_word_limits(tmp_path)
    assert (min_words, max_hard) == (2200, 5000)

    # 5200 字 → hard（v23 替换旧的 soft 警告）
    result = check_word_count("字" * 5200, min_words=min_words, max_words_hard=max_hard)
    assert result.passed is False
    assert result.severity == "hard"

    # 2199 字 → hard（零回归：硬下限 2200 字节级保留）
    result = check_word_count("字" * 2199, min_words=min_words, max_words_hard=max_hard)
    assert result.passed is False
    assert result.severity == "hard"


def test_e2e_chapter_words_2000_clamped_to_2200_floor(tmp_path: Path) -> None:
    """preferences 配得很小（chapter_words=2000）也不能让硬下限降到 2200 以下."""
    _write_prefs(tmp_path, {"pacing": {"chapter_words": 2000}})
    min_words, max_hard = load_word_limits(tmp_path)
    # MIN_WORDS_FLOOR=2200 红线保留
    assert min_words == 2200
    assert max_hard == 2500

    # 2199 字 → 仍以 hard 被阻断
    result = check_word_count("字" * 2199, min_words=min_words, max_words_hard=max_hard)
    assert result.passed is False
    assert result.severity == "hard"

    # 2200 字 → 通过（下限边界）
    result = check_word_count("字" * 2200, min_words=min_words, max_words_hard=max_hard)
    assert result.passed is True
