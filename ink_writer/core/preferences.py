#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
User preferences loader (word-limit driver).

v23 引入：统一从 ``.ink/preferences.json`` 的 ``pacing.chapter_words`` 推导章节
字数区间 ``[min_words, max_words_hard]``，供 computational_checks / ink-auto /
writer-agent 全链路消费。这是 US-002 的核心：消除代码中硬编码 2200/4000/5000
的字数阈值，同时把 LLM 可自行豁免的“上限软警告”收紧为硬约束。

Invariants（零回归红线）:
    - min_words 永不低于 2200（硬下限，全链路护栏）
    - preferences.json 不存在 / JSON 损坏 / 字段缺失 → fallback 默认值 (2200, 5000)
    - 任何字段类型错误均 fallback，不抛异常
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

# Defaults - 与 US-001 的 check_word_count 默认参数保持一致
DEFAULT_MIN_WORDS: int = 2200
DEFAULT_MAX_WORDS_HARD: int = 5000
# preferences.json 的 chapter_words 是“目标字数”，±500 形成合理区间
WORD_LIMIT_SPREAD: int = 500
# 硬下限护栏：任何情况下 min_words 不得低于此值
MIN_WORDS_FLOOR: int = 2200


def load_word_limits(project_root: Path) -> Tuple[int, int]:
    """Return ``(min_words, max_words_hard)`` derived from preferences.json.

    Parameters
    ----------
    project_root:
        项目根目录。会读取 ``<project_root>/.ink/preferences.json``。

    Returns
    -------
    tuple[int, int]
        ``(min_words, max_words_hard)``。
        - 无 preferences.json / JSON 损坏 / 无 ``pacing.chapter_words`` 字段
          → ``(2200, 5000)``
        - ``pacing.chapter_words = N`` →
          ``(max(2200, N - 500), N + 500)``
    """
    default = (DEFAULT_MIN_WORDS, DEFAULT_MAX_WORDS_HARD)

    try:
        preferences_file = Path(project_root) / ".ink" / "preferences.json"
    except TypeError:
        return default

    if not preferences_file.exists():
        return default

    try:
        with open(preferences_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return default

    if not isinstance(data, dict):
        return default

    pacing = data.get("pacing")
    if not isinstance(pacing, dict):
        return default

    raw = pacing.get("chapter_words")
    if raw is None:
        return default

    # 接受 int；拒绝 bool（bool 是 int 的子类，需显式排除）与其它类型
    if isinstance(raw, bool) or not isinstance(raw, int):
        return default

    if raw <= 0:
        return default

    min_words = max(MIN_WORDS_FLOOR, raw - WORD_LIMIT_SPREAD)
    max_words_hard = raw + WORD_LIMIT_SPREAD
    # 防御：若 chapter_words 远低于硬下限，推导结果可能出现 min >= max
    # （例如 chapter_words=1000 → min=2200, max=1500）。这种情况我们把
    # max 至少提升到 min，让 check_word_count 的硬下限分支先触发。
    if max_words_hard < min_words:
        max_words_hard = min_words
    return min_words, max_words_hard
