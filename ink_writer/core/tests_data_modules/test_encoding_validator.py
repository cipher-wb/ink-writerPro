#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""encoding_validator.py 单元测试"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

# 将 scripts/ 加入搜索路径
SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "ink-writer" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from encoding_validator import find_mojibake  # noqa: E402


class TestFindMojibake:
    """find_mojibake 函数测试"""

    def test_clean_text_returns_empty(self):
        text = "这是一段正常的中文文本，没有任何乱码。"
        assert find_mojibake(text) == []

    def test_empty_text_returns_empty(self):
        assert find_mojibake("") == []

    def test_single_mojibake_group(self):
        text = "风把地\ufffd\ufffd\ufffd的萝卜皮吹出去"
        results = find_mojibake(text)
        assert len(results) == 1
        r = results[0]
        assert r["line"] == 1
        assert r["column"] == 4  # "风把地" = 3 chars, column starts at 4
        assert r["count"] == 3
        assert r["context_before"] == "风把地"
        assert r["context_after"] == "的萝卜皮吹出去"

    def test_multiple_mojibake_groups_same_line(self):
        text = "前文\ufffd\ufffd\ufffd中间文字\ufffd\ufffd\ufffd后文"
        results = find_mojibake(text)
        assert len(results) == 2
        assert results[0]["context_before"] == "前文"
        assert results[0]["context_after"].startswith("中间文字")
        assert results[1]["context_after"] == "后文"

    def test_mojibake_on_different_lines(self):
        text = "第一行\ufffd\ufffd\ufffd正常\n第二行正常\n第三行\ufffd\ufffd\ufffd结尾"
        results = find_mojibake(text)
        assert len(results) == 2
        assert results[0]["line"] == 1
        assert results[1]["line"] == 3

    def test_single_replacement_char(self):
        text = "这里有一个\ufffd字符"
        results = find_mojibake(text)
        assert len(results) == 1
        assert results[0]["count"] == 1

    def test_context_radius_limit(self):
        long_prefix = "啊" * 30
        text = f"{long_prefix}\ufffd\ufffd\ufffd后文"
        results = find_mojibake(text)
        assert len(results) == 1
        assert len(results[0]["context_before"]) == 20

    def test_mojibake_at_line_start(self):
        text = "\ufffd\ufffd\ufffd这是行首乱码"
        results = find_mojibake(text)
        assert len(results) == 1
        assert results[0]["column"] == 1
        assert results[0]["context_before"] == ""

    def test_mojibake_at_line_end(self):
        text = "这是行尾乱码\ufffd\ufffd\ufffd"
        results = find_mojibake(text)
        assert len(results) == 1
        assert results[0]["context_after"] == ""


class TestCLI:
    """CLI 集成测试"""

    def test_clean_file_exit_code_0(self, tmp_path):
        f = tmp_path / "clean.md"
        f.write_text("这是正常文本。\n没有乱码。", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "encoding_validator.py"), "--file", str(f)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["has_mojibake"] is False
        assert data["count"] == 0

    def test_mojibake_file_exit_code_1(self, tmp_path):
        f = tmp_path / "bad.md"
        f.write_text("风把地\ufffd\ufffd\ufffd的萝卜皮", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "encoding_validator.py"), "--file", str(f)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert data["has_mojibake"] is True
        assert data["count"] == 1
        assert data["issues"][0]["context_before"] == "风把地"

    def test_missing_file_exit_code_2(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "encoding_validator.py"),
                "--file",
                str(tmp_path / "nonexistent.md"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2

    def test_project_root_chapter_lookup(self, tmp_path):
        chapter_dir = tmp_path / "正文"
        chapter_dir.mkdir()
        f = chapter_dir / "第0003章-测试标题.md"
        f.write_text("正常文本\ufffd乱码", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "encoding_validator.py"),
                "--project-root",
                str(tmp_path),
                "--chapter",
                "3",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert data["has_mojibake"] is True
