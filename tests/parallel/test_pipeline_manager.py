"""Tests for PipelineManager: config, chapter results, reports, async flow."""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ink_writer.parallel.pipeline_manager import (
    ChapterResult,
    ChapterStatus,
    PipelineConfig,
    PipelineManager,
    PipelineReport,
)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    ink = tmp_path / ".ink"
    ink.mkdir()
    (ink / "state.json").write_text('{"progress":{"current_chapter":0}}', encoding="utf-8")
    (ink / "summaries").mkdir()
    (ink / "logs" / "auto").mkdir(parents=True)
    (tmp_path / "正文").mkdir()
    return tmp_path


@pytest.fixture
def plugin_root(tmp_path: Path) -> Path:
    scripts = tmp_path / "plugin" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "ink.py").write_text("# stub", encoding="utf-8")
    return tmp_path / "plugin"


@pytest.fixture
def config(project_root: Path, plugin_root: Path) -> PipelineConfig:
    return PipelineConfig(
        project_root=project_root,
        plugin_root=plugin_root,
        parallel=4,
        cooldown=0,
        checkpoint_cooldown=0,
        platform="claude",
    )


class TestPipelineConfig:
    def test_scripts_dir(self, config: PipelineConfig):
        assert config.scripts_dir.exists()
        assert config.scripts_dir.name == "scripts"

    def test_log_dir_created(self, config: PipelineConfig):
        log_dir = config.log_dir
        assert log_dir.exists()
        assert "auto" in str(log_dir)

    def test_ink_py_path(self, config: PipelineConfig):
        assert config.ink_py.endswith("ink.py")

    def test_default_values(self, project_root: Path, plugin_root: Path):
        cfg = PipelineConfig(project_root=project_root, plugin_root=plugin_root)
        assert cfg.parallel == 4
        assert cfg.cooldown == 10
        assert cfg.platform == "claude"


class TestChapterResult:
    def test_elapsed_calculation(self):
        r = ChapterResult(chapter=1, status=ChapterStatus.DONE)
        r.start_time = 100.0
        r.end_time = 130.0
        assert r.elapsed == 30.0

    def test_elapsed_zero_when_not_finished(self):
        r = ChapterResult(chapter=1, status=ChapterStatus.WRITING)
        assert r.elapsed == 0.0

    def test_status_enum_values(self):
        assert ChapterStatus.PENDING.value == "pending"
        assert ChapterStatus.WRITING.value == "writing"
        assert ChapterStatus.DONE.value == "done"
        assert ChapterStatus.FAILED.value == "failed"
        assert ChapterStatus.RETRYING.value == "retrying"


class TestPipelineReport:
    def test_empty_report(self):
        report = PipelineReport()
        assert report.completed == 0
        assert report.failed == 0
        assert report.speedup == 0.0

    def test_report_with_results(self):
        r1 = ChapterResult(
            chapter=1, status=ChapterStatus.DONE,
            start_time=0, end_time=30, word_count=3000,
        )
        r2 = ChapterResult(
            chapter=2, status=ChapterStatus.DONE,
            start_time=0, end_time=25, word_count=2800,
        )
        r3 = ChapterResult(
            chapter=3, status=ChapterStatus.FAILED,
            start_time=0, end_time=10, error="test",
        )
        report = PipelineReport(
            results=[r1, r2, r3],
            start_time=0, end_time=35,
            parallel=4,
        )
        assert report.completed == 2
        assert report.failed == 1
        assert report.serial_total == 55.0
        assert report.wall_time == 35.0
        assert abs(report.speedup - 55.0 / 35.0) < 0.01

    def test_to_dict(self):
        r = ChapterResult(
            chapter=1, status=ChapterStatus.DONE,
            start_time=0, end_time=30, word_count=3000,
        )
        report = PipelineReport(
            results=[r], start_time=0, end_time=30, parallel=2,
        )
        d = report.to_dict()
        assert d["parallel"] == 2
        assert d["completed"] == 1
        assert d["failed"] == 0
        assert len(d["chapters"]) == 1
        assert d["chapters"][0]["chapter"] == 1
        assert d["chapters"][0]["status"] == "done"

    def test_speedup_zero_on_zero_wall(self):
        report = PipelineReport(start_time=10, end_time=10)
        assert report.speedup == 0.0


class TestPipelineManager:
    def test_init(self, config: PipelineConfig):
        mgr = PipelineManager(config)
        assert mgr.config.parallel == 4
        assert not mgr._interrupted

    @pytest.mark.asyncio
    async def test_verify_chapter_missing_file(self, config: PipelineConfig):
        mgr = PipelineManager(config)
        assert not await mgr._verify_chapter(1)

    @pytest.mark.asyncio
    async def test_verify_chapter_success(self, config: PipelineConfig):
        text_dir = config.project_root / "正文"
        chapter_file = text_dir / "第0001章测试.md"
        chapter_file.write_text("x" * 3000, encoding="utf-8")

        summary_dir = config.project_root / ".ink" / "summaries"
        (summary_dir / "ch0001.md").write_text("summary", encoding="utf-8")

        mgr = PipelineManager(config)
        assert await mgr._verify_chapter(1)

    @pytest.mark.asyncio
    async def test_verify_chapter_too_short(self, config: PipelineConfig):
        text_dir = config.project_root / "正文"
        chapter_file = text_dir / "第0001章测试.md"
        chapter_file.write_text("x" * 100, encoding="utf-8")

        summary_dir = config.project_root / ".ink" / "summaries"
        (summary_dir / "ch0001.md").write_text("summary", encoding="utf-8")

        mgr = PipelineManager(config)
        assert not await mgr._verify_chapter(1)

    @pytest.mark.asyncio
    async def test_verify_chapter_no_summary(self, config: PipelineConfig):
        text_dir = config.project_root / "正文"
        chapter_file = text_dir / "第0001章测试.md"
        chapter_file.write_text("x" * 3000, encoding="utf-8")

        mgr = PipelineManager(config)
        assert not await mgr._verify_chapter(1)

    @pytest.mark.asyncio
    async def test_get_word_count(self, config: PipelineConfig):
        text_dir = config.project_root / "正文"
        content = "测试内容" * 500
        (text_dir / "第0001章测试章.md").write_text(content, encoding="utf-8")

        mgr = PipelineManager(config)
        wc = await mgr._get_word_count(1)
        assert wc == len(content)

    @pytest.mark.asyncio
    async def test_get_word_count_missing(self, config: PipelineConfig):
        mgr = PipelineManager(config)
        assert await mgr._get_word_count(99) == 0


class TestPipelineManagerIntegration:
    """Integration tests with mocked CLI processes."""

    @pytest.mark.asyncio
    async def test_run_with_mock_chapters(self, config: PipelineConfig):
        mgr = PipelineManager(config)
        config.parallel = 2

        chapters_written = []

        async def mock_get_current():
            return 0

        async def mock_check_outline(ch):
            return True

        async def mock_clear_workflow():
            pass

        async def mock_run_cli(prompt, log_file):
            return 0

        async def mock_verify(ch):
            return ch in chapters_written

        async def mock_get_wc(ch):
            return 3000

        async def mock_write_single(ch, batch, pos, bs):
            chapters_written.append(ch)
            await asyncio.sleep(0.05)
            return ChapterResult(
                chapter=ch, status=ChapterStatus.DONE,
                start_time=time.time() - 0.05, end_time=time.time(),
                word_count=3000,
            )

        async def mock_checkpoint(ch):
            pass

        async def mock_final():
            return 0

        mgr._get_current_chapter = mock_get_current
        mgr._check_outline = mock_check_outline
        mgr._clear_workflow = mock_clear_workflow
        mgr._run_cli = mock_run_cli
        mgr._verify_chapter = mock_verify
        mgr._get_word_count = mock_get_wc
        mgr._write_single_chapter = mock_write_single
        mgr._run_checkpoint = mock_checkpoint
        mgr._get_final_chapter = mock_final

        report = await mgr.run(total_chapters=6)

        assert report.completed == 6
        assert report.failed == 0
        assert report.parallel == 2
        assert len(report.results) == 6
        assert all(r.status == ChapterStatus.DONE for r in report.results)

    @pytest.mark.asyncio
    async def test_run_stops_on_outline_failure(self, config: PipelineConfig):
        mgr = PipelineManager(config)
        config.parallel = 2

        async def mock_get_current():
            return 0

        async def mock_check_outline(ch):
            return False

        async def mock_auto_outline(ch):
            return False

        async def mock_final():
            return 0

        async def mock_clear():
            pass

        mgr._get_current_chapter = mock_get_current
        mgr._check_outline = mock_check_outline
        mgr._auto_generate_outline = mock_auto_outline
        mgr._get_final_chapter = mock_final
        mgr._clear_workflow = mock_clear

        report = await mgr.run(total_chapters=4)

        assert report.completed == 0
        assert report.failed == 1
        assert report.results[0].error == "大纲生成失败"

    @pytest.mark.asyncio
    async def test_speedup_calculation(self, config: PipelineConfig):
        config.parallel = 4

        results = []
        for i in range(1, 5):
            results.append(ChapterResult(
                chapter=i, status=ChapterStatus.DONE,
                start_time=0, end_time=30, word_count=3000,
            ))

        report = PipelineReport(
            results=results,
            start_time=0,
            end_time=35,
            parallel=4,
        )

        assert report.serial_total == 120.0
        assert report.wall_time == 35.0
        assert report.speedup > 2.5

    @pytest.mark.asyncio
    async def test_batch_failure_stops_pipeline(self, config: PipelineConfig):
        mgr = PipelineManager(config)
        config.parallel = 2

        async def mock_get_current():
            return 0

        async def mock_check_outline(ch):
            return True

        async def mock_clear_workflow():
            pass

        async def mock_final():
            return 0

        async def mock_write_single(ch, batch, pos, bs):
            if ch == 2:
                return ChapterResult(
                    chapter=ch, status=ChapterStatus.FAILED,
                    start_time=time.time(), end_time=time.time(),
                    error="模拟失败",
                )
            return ChapterResult(
                chapter=ch, status=ChapterStatus.DONE,
                start_time=time.time() - 0.01, end_time=time.time(),
                word_count=3000,
            )

        mgr._get_current_chapter = mock_get_current
        mgr._check_outline = mock_check_outline
        mgr._clear_workflow = mock_clear_workflow
        mgr._write_single_chapter = mock_write_single
        mgr._get_final_chapter = mock_final

        report = await mgr.run(total_chapters=6)

        assert report.completed == 1
        assert report.failed == 1
        assert len(report.results) == 2
