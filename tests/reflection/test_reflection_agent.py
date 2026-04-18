"""US-022: Reflection agent tests (macro-review every N chapters)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ink_writer.core.context.memory_compressor import (
    compress_chapter_window,
    save_l1_summary,
)
from ink_writer.reflection import load_reflections, run_reflection
from ink_writer.reflection.reflection_agent import (
    ReflectionResult,
    should_trigger,
)


def _write_summary(root: Path, chapter: int, body: str, frontmatter: dict | None = None) -> None:
    summaries = root / ".ink" / "summaries"
    summaries.mkdir(parents=True, exist_ok=True)
    fm = frontmatter or {"chapter": str(chapter)}
    fm_txt = "\n".join(f'{k}: "{v}"' for k, v in fm.items())
    (summaries / f"ch{chapter:04d}.md").write_text(
        f"---\n{fm_txt}\n---\n{body}\n", encoding="utf-8"
    )


def _write_progressions(root: Path, rows: list[dict]) -> None:
    ink = root / ".ink"
    ink.mkdir(parents=True, exist_ok=True)
    (ink / "progressions.json").write_text(
        json.dumps(rows, ensure_ascii=False), encoding="utf-8"
    )


def _write_foreshadow(root: Path, items: list[dict]) -> None:
    ink = root / ".ink"
    ink.mkdir(parents=True, exist_ok=True)
    (ink / "foreshadow.json").write_text(
        json.dumps(items, ensure_ascii=False), encoding="utf-8"
    )


class TestShouldTrigger:
    def test_triggers_on_multiples_of_interval(self):
        assert should_trigger(50, 50) is True
        assert should_trigger(100, 50) is True
        assert should_trigger(49, 50) is False
        assert should_trigger(25, 50) is False

    def test_never_triggers_before_first_interval(self):
        assert should_trigger(10, 50) is False


class TestRunReflection:
    def test_empty_project_returns_bullets(self, tmp_path):
        result = run_reflection(tmp_path, current_chapter=50, window=50, write=False)
        assert isinstance(result, ReflectionResult)
        assert 3 <= len(result.bullets) <= 5

    def test_recurring_entities_surfaced(self, tmp_path):
        # 50 chapters all mentioning 萧尘 and 林渊 frequently.
        for ch in range(1, 51):
            _write_summary(tmp_path, ch, f"第{ch}章萧尘和林渊再次交手，萧尘占上风。")
        result = run_reflection(tmp_path, current_chapter=50, window=50, write=False)
        joined = "\n".join(result.bullets)
        assert "高频实体" in joined or "实体" in joined

    def test_foreshadow_density_warning(self, tmp_path):
        for ch in range(1, 51):
            _write_summary(tmp_path, ch, "普通章节")
        # 5 unresolved foreshadow items planted in window.
        foreshadows = [
            {"id": f"F{i}", "planted_chapter": 10 + i, "status": "open"}
            for i in range(5)
        ]
        _write_foreshadow(tmp_path, foreshadows)
        result = run_reflection(tmp_path, current_chapter=50, window=50, write=False)
        joined = "\n".join(result.bullets)
        assert "伏笔" in joined

    def test_progression_hotspot_bullet(self, tmp_path):
        for ch in range(1, 51):
            _write_summary(tmp_path, ch, "章节内容")
        progressions = [
            {"chapter_no": 10, "entity_id": "char:萧尘", "dimension": "武力"},
            {"chapter_no": 20, "entity_id": "char:萧尘", "dimension": "心境"},
            {"chapter_no": 30, "entity_id": "char:萧尘", "dimension": "武力"},
        ]
        _write_progressions(tmp_path, progressions)
        result = run_reflection(tmp_path, current_chapter=50, window=50, write=False)
        joined = "\n".join(result.bullets)
        assert "演进" in joined or "萧尘" in joined

    def test_writes_reflections_file_with_history(self, tmp_path):
        for ch in range(1, 51):
            _write_summary(tmp_path, ch, "章节内容")
        run_reflection(tmp_path, current_chapter=50, window=50, write=True)
        run_reflection(tmp_path, current_chapter=100, window=50, write=True)

        payload = load_reflections(tmp_path)
        assert payload is not None
        assert "latest" in payload
        assert payload["latest"]["chapter"] == 100
        assert len(payload["history"]) == 2

    def test_bullets_count_in_range(self, tmp_path):
        for ch in range(1, 51):
            _write_summary(tmp_path, ch, f"第{ch}章普通内容")
        result = run_reflection(tmp_path, current_chapter=50, window=50, write=False)
        assert 3 <= len(result.bullets) <= 5

    def test_load_reflections_missing(self, tmp_path):
        assert load_reflections(tmp_path) is None

    def test_load_reflections_corrupt(self, tmp_path):
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".ink" / "reflections.json").write_text("{ not json", encoding="utf-8")
        assert load_reflections(tmp_path) is None


class TestL1Compressor:
    def test_compress_returns_bullet_range(self, tmp_path):
        for ch in range(1, 9):
            _write_summary(tmp_path, ch, f"第{ch}章发生了关键事件。萧尘取得新进展。")
        result = compress_chapter_window(tmp_path, end_chapter=8, window=8, bullet_target=3)
        assert result["mode"] == "heuristic"
        assert 3 <= len(result["bullets"]) <= 5
        assert result["chapter_range"] == [1, 8]

    def test_compress_respects_min_max(self, tmp_path):
        for ch in range(1, 9):
            _write_summary(tmp_path, ch, f"ch{ch} body")
        # bullet_target below 3 clamps to 3.
        r = compress_chapter_window(tmp_path, end_chapter=8, window=8, bullet_target=1)
        assert len(r["bullets"]) >= 3
        # bullet_target above 5 clamps to 5.
        r2 = compress_chapter_window(tmp_path, end_chapter=8, window=8, bullet_target=99)
        assert len(r2["bullets"]) <= 5

    def test_compress_llm_mode_returns_prompt(self, tmp_path):
        for ch in range(1, 9):
            _write_summary(tmp_path, ch, f"第{ch}章重要事件")
        result = compress_chapter_window(
            tmp_path, end_chapter=8, window=8, bullet_target=3, use_llm=True
        )
        assert result["mode"] == "llm_prompt"
        assert "prompt" in result
        assert "压缩" in result["prompt"]

    def test_compress_empty_window(self, tmp_path):
        result = compress_chapter_window(tmp_path, end_chapter=8, window=8, bullet_target=3)
        # no summaries exist
        assert result["bullets"] == []
        assert result["source_chapters"] == []

    def test_save_l1_summary_persists_file(self, tmp_path):
        result = {"chapter_range": [1, 8], "bullets": ["a", "b", "c"], "mode": "heuristic"}
        p = save_l1_summary(tmp_path, end_chapter=8, result=result)
        assert p.exists()
        loaded = json.loads(p.read_text(encoding="utf-8"))
        assert loaded["bullets"] == ["a", "b", "c"]


class TestContextAgentIntegration:
    """Verify the context-agent memory section picks up reflections.json."""

    def test_context_manager_injects_reflections_into_memory(self, tmp_path):
        # Write a reflections payload directly.
        (tmp_path / ".ink").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".ink" / "reflections.json").write_text(
            json.dumps(
                {
                    "latest": {
                        "chapter": 100,
                        "window": 50,
                        "bullets": [
                            "高频实体：萧尘×12",
                            "角色演进热点：char:林渊",
                            "跨度观察：近 50 章累积 50 条摘要",
                        ],
                        "mode": "heuristic",
                    },
                    "history": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        from ink_writer.core.context.context_manager import ContextManager
        from ink_writer.core.infra.config import DataModulesConfig

        cfg = DataModulesConfig(project_root=tmp_path)
        mgr = ContextManager.__new__(ContextManager)
        mgr.config = cfg
        payload = mgr._load_reflections()
        assert payload["chapter"] == 100
        assert len(payload["bullets"]) == 3
        assert payload["source"].endswith("reflections.json")

    def test_context_manager_no_reflections_returns_empty(self, tmp_path):
        from ink_writer.core.context.context_manager import ContextManager
        from ink_writer.core.infra.config import DataModulesConfig

        cfg = DataModulesConfig(project_root=tmp_path)
        mgr = ContextManager.__new__(ContextManager)
        mgr.config = cfg
        payload = mgr._load_reflections()
        assert payload == {}
