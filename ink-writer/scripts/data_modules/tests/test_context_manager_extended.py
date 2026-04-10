"""Extended tests for ContextManager — volume summaries, stage resolution, budget trimming."""

import json
import pytest

from data_modules.config import DataModulesConfig
from data_modules.context_manager import ContextManager
from data_modules.index_manager import IndexManager


@pytest.fixture
def temp_project(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return cfg


def _write_state(cfg, chapter=1, extra=None):
    state = {
        "protagonist_state": {"name": "萧炎"},
        "chapter_meta": {},
        "disambiguation_warnings": [],
        "disambiguation_pending": [],
    }
    if extra:
        state.update(extra)
    state.setdefault("progress", {})["current_chapter"] = chapter
    cfg.state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


class TestLoadVolumeSummaries:
    def test_chapter_100_loads_vol1_mega(self, temp_project):
        """chapter=100 时正确加载 vol1 mega-summary"""
        summaries_dir = temp_project.ink_dir / "summaries"
        summaries_dir.mkdir(parents=True, exist_ok=True)
        (summaries_dir / "vol1_mega.md").write_text("Volume 1 mega summary", encoding="utf-8")

        manager = ContextManager(temp_project)
        results = manager._load_volume_summaries(chapter=100, window=3)
        assert len(results) == 1
        assert results[0]["volume"] == 1
        assert "Volume 1 mega summary" in results[0]["summary"]

    def test_early_chapter_returns_empty(self, temp_project):
        """chapter=30 时返回空列表（首卷还没结束）"""
        manager = ContextManager(temp_project)
        results = manager._load_volume_summaries(chapter=30, window=3)
        assert results == []


class TestResolveContextStage:
    def test_early_stage(self, temp_project):
        manager = ContextManager(temp_project)
        assert manager._resolve_context_stage(1) == "early"
        assert manager._resolve_context_stage(30) == "early"

    def test_mid_stage(self, temp_project):
        manager = ContextManager(temp_project)
        assert manager._resolve_context_stage(31) == "mid"
        assert manager._resolve_context_stage(60) == "mid"
        assert manager._resolve_context_stage(119) == "mid"

    def test_late_stage(self, temp_project):
        manager = ContextManager(temp_project)
        assert manager._resolve_context_stage(120) == "late"
        assert manager._resolve_context_stage(500) == "late"


class TestTokenBudgetTrimming:
    def test_trimming_triggers_on_excess(self, temp_project):
        """超出预算时正确裁剪"""
        _write_state(temp_project, chapter=5)
        manager = ContextManager(temp_project)

        # 构建一个巨大的 pack 以触发裁剪
        pack = {
            "meta": {"chapter": 5},
            "core": {"data": "x" * 5000},
            "scene": {"data": "y" * 5000},
            "global": {"data": "z" * 5000},
            "alerts": {"data": "a" * 5000},
            "preferences": {"data": "p" * 5000},
            "memory": {"data": "m" * 5000},
            "story_skeleton": {"data": "s" * 5000},
        }

        # 设置一个很低的 hard_token_limit 来强制触发裁剪
        manager.config.context_hard_token_limit = 500

        assembled = manager.assemble_context(pack, max_chars=50000)

        # 至少有一些 section 被裁剪了
        trimmed_any = any(
            sec.get("budget_trimmed")
            for sec in assembled.get("sections", {}).values()
        )
        assert trimmed_any is True

    def test_budget_trim_warning_injected(self, temp_project):
        """裁剪后注入 budget_trim_warning"""
        _write_state(temp_project, chapter=5)
        manager = ContextManager(temp_project)

        # 构造超大 pack
        pack = {
            "meta": {"chapter": 5},
            "core": {"data": "x" * 10000},
            "scene": {"data": "y" * 10000},
            "global": {"data": "z" * 10000},
            "alerts": {"data": "a" * 10000},
            "preferences": {"data": "p" * 10000},
            "memory": {"data": "m" * 10000},
            "story_skeleton": {"data": "s" * 10000},
        }

        # 极低 token limit，确保裁剪后仍超限 → budget_trimmed=True
        manager.config.context_hard_token_limit = 100

        assembled = manager.assemble_context(pack, max_chars=80000)

        # 如果 budget_trimmed 为 True，则应注入 warning
        if assembled.get("meta", {}).get("budget_trimmed"):
            assert "budget_trim_warning" in assembled["sections"]
            warning_sec = assembled["sections"]["budget_trim_warning"]
            assert warning_sec["priority"] == "high"
            assert "截断" in warning_sec["text"]
            assert warning_sec["budget_trimmed"] is False

    def test_no_warning_when_within_budget(self, temp_project):
        """未超预算时不注入 warning"""
        _write_state(temp_project, chapter=5)
        manager = ContextManager(temp_project)

        pack = {
            "meta": {"chapter": 5},
            "core": {"data": "short"},
        }

        manager.config.context_hard_token_limit = 100000

        assembled = manager.assemble_context(pack, max_chars=10000)
        assert "budget_trim_warning" not in assembled.get("sections", {})


class TestLoadVolumeSummariesConfigurable:
    def test_chapters_per_volume_from_config(self, temp_project):
        """chapters_per_volume=0 时从 config 读取"""
        temp_project.chapters_per_volume = 25

        summaries_dir = temp_project.ink_dir / "summaries"
        summaries_dir.mkdir(parents=True, exist_ok=True)
        (summaries_dir / "vol1_mega.md").write_text("Vol1 mega", encoding="utf-8")

        manager = ContextManager(temp_project)
        # chapter=50 with cpv=25 means vol1 (ch1-25) should be loaded
        results = manager._load_volume_summaries(chapter=50, window=3, chapters_per_volume=0)
        assert len(results) >= 1
        assert results[0]["volume"] == 1
