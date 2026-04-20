#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
US-002: tests for load_word_limits (preferences.json → (min, max_hard) 推导)

零回归红线验证：
- 无配置 / preferences.json 损坏 → (2200, 5000)
- 硬下限 2200 永不低于（即便 chapter_words 很小）
- UTF-8 编码严格（Windows 兼容守则）
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ink_writer.core.preferences import load_word_limits


def _write_prefs(project_root: Path, payload) -> Path:
    ink_dir = project_root / ".ink"
    ink_dir.mkdir(parents=True, exist_ok=True)
    prefs = ink_dir / "preferences.json"
    if isinstance(payload, str):
        prefs.write_text(payload, encoding="utf-8")
    else:
        prefs.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return prefs


def test_no_preferences_file_returns_default(tmp_path: Path) -> None:
    """preferences.json 完全不存在 → 默认 (2200, 5000)。"""
    assert load_word_limits(tmp_path) == (2200, 5000)


def test_no_ink_dir_returns_default(tmp_path: Path) -> None:
    """即便 .ink 目录不存在也不应抛异常。"""
    assert load_word_limits(tmp_path) == (2200, 5000)


def test_chapter_words_3000_derives_interval(tmp_path: Path) -> None:
    """chapter_words=3000 → (2500, 3500)。"""
    _write_prefs(tmp_path, {"pacing": {"chapter_words": 3000}})
    assert load_word_limits(tmp_path) == (2500, 3500)


def test_chapter_words_below_hard_floor_clamped(tmp_path: Path) -> None:
    """chapter_words=2000 (N-500=1500 < 2200) → 硬下限红线保持 2200。"""
    _write_prefs(tmp_path, {"pacing": {"chapter_words": 2000}})
    min_words, max_hard = load_word_limits(tmp_path)
    # 硬下限 2200 不可被 preferences 弱化
    assert min_words == 2200, f"min_words must never drop below 2200, got {min_words}"
    # max 仍由 chapter_words+500 推导
    assert max_hard == 2500


def test_chapter_words_4500_derives_interval(tmp_path: Path) -> None:
    """chapter_words=4500 → (4000, 5000)。"""
    _write_prefs(tmp_path, {"pacing": {"chapter_words": 4500}})
    assert load_word_limits(tmp_path) == (4000, 5000)


def test_corrupted_json_returns_default(tmp_path: Path) -> None:
    """preferences.json 是非法 JSON → 回退默认不抛异常。"""
    _write_prefs(tmp_path, "{not valid json[")
    assert load_word_limits(tmp_path) == (2200, 5000)


def test_missing_pacing_section_returns_default(tmp_path: Path) -> None:
    """preferences.json 存在但无 pacing 段 → 默认。"""
    _write_prefs(tmp_path, {"tone": "热血"})
    assert load_word_limits(tmp_path) == (2200, 5000)


def test_missing_chapter_words_returns_default(tmp_path: Path) -> None:
    """pacing 存在但无 chapter_words → 默认。"""
    _write_prefs(tmp_path, {"pacing": {"cliffhanger": True}})
    assert load_word_limits(tmp_path) == (2200, 5000)


def test_non_int_chapter_words_returns_default(tmp_path: Path) -> None:
    """chapter_words 不是 int → 默认，不抛异常。"""
    _write_prefs(tmp_path, {"pacing": {"chapter_words": "3000"}})
    assert load_word_limits(tmp_path) == (2200, 5000)


def test_bool_chapter_words_returns_default(tmp_path: Path) -> None:
    """bool 是 int 子类，但语义上是布尔不是字数 → 拒绝。"""
    _write_prefs(tmp_path, {"pacing": {"chapter_words": True}})
    assert load_word_limits(tmp_path) == (2200, 5000)


def test_zero_or_negative_chapter_words_returns_default(tmp_path: Path) -> None:
    """非正数 chapter_words 无意义 → 默认。"""
    _write_prefs(tmp_path, {"pacing": {"chapter_words": 0}})
    assert load_word_limits(tmp_path) == (2200, 5000)
    _write_prefs(tmp_path, {"pacing": {"chapter_words": -100}})
    assert load_word_limits(tmp_path) == (2200, 5000)


def test_pacing_not_dict_returns_default(tmp_path: Path) -> None:
    """pacing 字段类型错误（比如字符串）→ 默认。"""
    _write_prefs(tmp_path, {"pacing": "fast"})
    assert load_word_limits(tmp_path) == (2200, 5000)


def test_return_type_is_tuple_of_ints(tmp_path: Path) -> None:
    """签名契约：返回 tuple[int, int]。"""
    _write_prefs(tmp_path, {"pacing": {"chapter_words": 3000}})
    result = load_word_limits(tmp_path)
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert all(isinstance(x, int) for x in result)


def test_utf8_encoded_preferences_reads_correctly(tmp_path: Path) -> None:
    """包含中文的 preferences.json 必须按 UTF-8 正确读取（Windows 守则）。"""
    _write_prefs(tmp_path, {"tone": "热血沸腾", "pacing": {"chapter_words": 3500}})
    assert load_word_limits(tmp_path) == (3000, 4000)
