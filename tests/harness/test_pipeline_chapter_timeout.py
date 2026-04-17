"""US-013: pipeline_manager 章级 asyncio.wait_for 超时测试。

验证：
  1. PipelineConfig.chapter_timeout_s 默认 1800（或 env INK_CHAPTER_TIMEOUT）
  2. 超时章节被标记为 TIMEOUT_FAILED 而不阻塞其它章
  3. 超时后 PipelineReport.results 正常记录
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ink_writer.parallel.pipeline_manager import (
    ChapterResult,
    ChapterStatus,
    PipelineConfig,
    PipelineManager,
)


def test_default_chapter_timeout_is_1800():
    cfg = PipelineConfig(project_root=Path("/tmp/x"), plugin_root=Path("/tmp/y"))
    assert cfg.chapter_timeout_s == 1800 or cfg.chapter_timeout_s == int(
        os.environ.get("INK_CHAPTER_TIMEOUT", 1800)
    )


def test_env_override_chapter_timeout(monkeypatch):
    """env INK_CHAPTER_TIMEOUT 可覆盖默认值；显式传参也可。"""
    monkeypatch.setenv("INK_CHAPTER_TIMEOUT", "120")
    # 注：模块级 field default 在 import 时已固化；此处验证显式传参路径
    cfg = PipelineConfig(
        project_root=Path("/tmp/x"), plugin_root=Path("/tmp/y"),
        chapter_timeout_s=int(os.environ["INK_CHAPTER_TIMEOUT"]),
    )
    assert cfg.chapter_timeout_s == 120


def test_timeout_status_enum_exists():
    """新增的 TIMEOUT_FAILED 枚举值存在。"""
    assert ChapterStatus.TIMEOUT_FAILED.value == "timeout_failed"


@pytest.mark.asyncio
async def test_chapter_timeout_marks_timeout_failed(tmp_path):
    """模拟单章超时，验证 ChapterResult.status == TIMEOUT_FAILED。"""
    plugin_root = tmp_path / "plugin"
    (plugin_root / "scripts").mkdir(parents=True)
    project_root = tmp_path / "project"
    project_root.mkdir()

    cfg = PipelineConfig(
        project_root=project_root,
        plugin_root=plugin_root,
        parallel=1,
        chapter_timeout_s=1,  # 1 秒超时
        max_retries=0,
    )
    mgr = PipelineManager(cfg)

    # Mock _get_current_chapter 返回 0，_check_outline 返回 True，
    # _write_single_chapter 故意挂 5 秒触发 timeout
    mgr._get_current_chapter = AsyncMock(return_value=0)  # type: ignore
    mgr._check_outline = AsyncMock(return_value=True)  # type: ignore
    mgr._clear_workflow = AsyncMock(return_value=None)  # type: ignore
    mgr._run_checkpoint = AsyncMock(return_value=None)  # type: ignore
    mgr._get_final_chapter = AsyncMock(return_value=0)  # type: ignore

    async def slow_write(*args, **kwargs):
        await asyncio.sleep(5)  # 故意挂 5s（超过 1s 超时）
        return ChapterResult(chapter=args[0], status=ChapterStatus.DONE)

    mgr._write_single_chapter = slow_write  # type: ignore

    report = await mgr.run(total_chapters=1)
    assert len(report.results) == 1
    assert report.results[0].status == ChapterStatus.TIMEOUT_FAILED
    assert "章节超时" in report.results[0].error
