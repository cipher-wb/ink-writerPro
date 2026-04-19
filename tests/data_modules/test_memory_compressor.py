"""Tests for memory_compressor module."""
import json
import os
from pathlib import Path

import pytest


class TestCheckCompressionNeeded:
    def test_early_chapter_no_compression(self, tmp_path):
        """50 章以内不需要压缩"""
        from ink_writer.core.context.memory_compressor import check_compression_needed
        # 创建最小项目结构
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        (ink_dir / "state.json").write_text('{"progress": {"current_chapter": 30}}', encoding="utf-8")
        result = check_compression_needed(tmp_path, 30)
        assert result["needed"] is False

    def test_past_volume_needs_compression(self, tmp_path):
        """超过 50 章且无 mega-summary 时需要压缩"""
        from ink_writer.core.context.memory_compressor import check_compression_needed
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        summaries_dir = ink_dir / "summaries"
        summaries_dir.mkdir()
        # 创建 50 个章节摘要
        for i in range(1, 51):
            (summaries_dir / f"ch{i:04d}.md").write_text(f"---\nchapter: {i}\n---\nSummary of chapter {i}", encoding="utf-8")
        result = check_compression_needed(tmp_path, 55)
        assert result["needed"] is True
        assert result["volume_to_compress"] == 1

    def test_existing_mega_no_compression(self, tmp_path):
        """已有 mega-summary 时不需要再压缩"""
        from ink_writer.core.context.memory_compressor import check_compression_needed
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        summaries_dir = ink_dir / "summaries"
        summaries_dir.mkdir()
        for i in range(1, 51):
            (summaries_dir / f"ch{i:04d}.md").write_text(f"Summary {i}", encoding="utf-8")
        (summaries_dir / "vol1_mega.md").write_text("Volume 1 mega summary", encoding="utf-8")
        result = check_compression_needed(tmp_path, 55)
        assert result["needed"] is False

    def test_no_summaries_dir(self, tmp_path):
        """没有 summaries 目录时不需要压缩"""
        from ink_writer.core.context.memory_compressor import check_compression_needed
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        result = check_compression_needed(tmp_path, 80)
        assert result["needed"] is False

    def test_custom_chapters_per_volume(self, tmp_path):
        """自定义 chapters_per_volume 参数"""
        from ink_writer.core.context.memory_compressor import check_compression_needed
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()
        summaries_dir = ink_dir / "summaries"
        summaries_dir.mkdir()
        # 用 chapters_per_volume=20, 创建 20 个章节摘要
        for i in range(1, 21):
            (summaries_dir / f"ch{i:04d}.md").write_text(f"---\nchapter: {i}\n---\nSummary {i}", encoding="utf-8")
        result = check_compression_needed(tmp_path, 25, chapters_per_volume=20)
        assert result["needed"] is True
        assert result["volume_to_compress"] == 1


class TestLoadVolumeSummaries:
    def test_load_volume_summaries(self, tmp_path):
        from ink_writer.core.context.memory_compressor import load_volume_summaries
        ink_dir = tmp_path / ".ink"
        summaries_dir = ink_dir / "summaries"
        summaries_dir.mkdir(parents=True)
        for i in range(1, 6):
            (summaries_dir / f"ch{i:04d}.md").write_text(
                f"---\nchapter: {i}\ntitle: Chapter {i}\n---\nContent of chapter {i}"
            , encoding="utf-8")
        result = load_volume_summaries(tmp_path, 1)
        assert len(result) >= 5

    def test_load_volume_summaries_with_custom_cpv(self, tmp_path):
        from ink_writer.core.context.memory_compressor import load_volume_summaries
        ink_dir = tmp_path / ".ink"
        summaries_dir = ink_dir / "summaries"
        summaries_dir.mkdir(parents=True)
        for i in range(1, 11):
            (summaries_dir / f"ch{i:04d}.md").write_text(
                f"---\nchapter: {i}\n---\nContent {i}"
            , encoding="utf-8")
        result = load_volume_summaries(tmp_path, 1, chapters_per_volume=10)
        assert len(result) == 10


class TestBuildMegaSummaryPrompt:
    def test_prompt_structure(self, tmp_path):
        from ink_writer.core.context.memory_compressor import build_mega_summary_prompt
        summaries = [
            {"chapter": 1, "title": "Ch1", "body": "Content 1"},
            {"chapter": 2, "title": "Ch2", "body": "Content 2"},
        ]
        prompt = build_mega_summary_prompt(summaries, 1)
        assert "第1卷" in prompt or "卷1" in prompt or "vol" in prompt.lower()
        assert isinstance(prompt, str)
        assert len(prompt) > 0


class TestSaveMegaSummary:
    def test_save_creates_file(self, tmp_path):
        from ink_writer.core.context.memory_compressor import save_mega_summary
        ink_dir = tmp_path / ".ink"
        summaries_dir = ink_dir / "summaries"
        summaries_dir.mkdir(parents=True)
        save_mega_summary(tmp_path, 1, "This is the mega summary for volume 1")
        mega_file = summaries_dir / "vol1_mega.md"
        assert mega_file.exists()
        assert "mega summary" in mega_file.read_text(encoding="utf-8")


class TestDefaultChaptersPerVolumeEnvVar:
    def test_env_var_override(self, monkeypatch):
        """环境变量 INK_CHAPTERS_PER_VOLUME 能覆盖默认值"""
        monkeypatch.setenv("INK_CHAPTERS_PER_VOLUME", "100")
        # 需要重新导入以获取新的环境变量
        import importlib
        import ink_writer.core.context.memory_compressor as mc
        importlib.reload(mc)
        assert mc.DEFAULT_CHAPTERS_PER_VOLUME == 100
        # 恢复
        monkeypatch.delenv("INK_CHAPTERS_PER_VOLUME", raising=False)
        importlib.reload(mc)
