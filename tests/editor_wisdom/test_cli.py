"""Tests for editor-wisdom CLI subcommands."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ink_writer.editor_wisdom.cli import (
    PIPELINE_STEPS,
    SCRIPTS_DIR,
    cmd_query,
    cmd_rebuild,
    cmd_stats,
)

# ── rebuild tests ──


class TestRebuild:
    def test_rebuild_runs_all_steps_in_order(self, tmp_path: Path):
        call_log: list[str] = []

        def fake_run(args, **_kwargs):
            script = Path(args[1]).name
            call_log.append(script)
            return MagicMock(returncode=0)

        with patch("ink_writer.editor_wisdom.cli.subprocess.run", side_effect=fake_run):
            code = cmd_rebuild()

        assert code == 0
        expected = [s[0] for s in PIPELINE_STEPS]
        assert call_log == expected

    def test_rebuild_stops_on_failure(self):
        call_count = 0

        def fake_run(args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)

        with patch("ink_writer.editor_wisdom.cli.subprocess.run", side_effect=fake_run):
            code = cmd_rebuild()

        assert code != 0
        assert call_count == 3

    def test_rebuild_uses_python_executable(self):
        captured_args: list = []

        def fake_run(args, **_kwargs):
            captured_args.append(args)
            return MagicMock(returncode=0)

        with patch("ink_writer.editor_wisdom.cli.subprocess.run", side_effect=fake_run):
            cmd_rebuild()

        for args in captured_args:
            assert args[0] == sys.executable

    def test_rebuild_missing_script(self, tmp_path: Path):
        with patch("ink_writer.editor_wisdom.cli.SCRIPTS_DIR", tmp_path):
            code = cmd_rebuild()
        assert code == 1


# ── query tests ──


@dataclass
class FakeRule:
    id: str = "EW-0001"
    category: str = "opening"
    rule: str = "开篇必须有钩子"
    why: str = "吸引读者"
    severity: str = "hard"
    applies_to: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)


class TestQuery:
    def test_query_prints_results(self, capsys: pytest.CaptureFixture):
        fake_retriever = MagicMock()
        fake_retriever.return_value.retrieve.return_value = [
            FakeRule(),
            FakeRule(id="EW-0002", category="hook", rule="章末设悬念", severity="soft"),
        ]

        with (
            patch("ink_writer.editor_wisdom.cli.DATA_DIR", Path("/fake")),
            patch("ink_writer.editor_wisdom.retriever.Retriever", fake_retriever),
            patch.object(Path, "exists", return_value=True),
        ):
            from ink_writer.editor_wisdom import retriever as ret_mod
            orig = ret_mod.Retriever
            ret_mod.Retriever = fake_retriever
            try:
                code = cmd_query("开篇钩子", top_k=5)
            finally:
                ret_mod.Retriever = orig

        assert code == 0
        out = capsys.readouterr().out
        assert "EW-0001" in out
        assert "EW-0002" in out
        assert "opening" in out

    def test_query_no_index_returns_error(self, tmp_path: Path):
        with patch("ink_writer.editor_wisdom.cli.DATA_DIR", tmp_path):
            code = cmd_query("test")
        assert code == 1

    def test_query_empty_results(self, capsys: pytest.CaptureFixture):
        fake_retriever = MagicMock()
        fake_retriever.return_value.retrieve.return_value = []

        with patch("ink_writer.editor_wisdom.cli.DATA_DIR", Path("/fake")), patch.object(
            Path, "exists", return_value=True
        ):
            from ink_writer.editor_wisdom import retriever as ret_mod
            orig = ret_mod.Retriever
            ret_mod.Retriever = fake_retriever
            try:
                code = cmd_query("不存在的查询", top_k=5)
            finally:
                ret_mod.Retriever = orig

        assert code == 0
        out = capsys.readouterr().out
        assert "未找到" in out

    def test_query_respects_top_k(self):
        fake_retriever = MagicMock()
        fake_retriever.return_value.retrieve.return_value = [FakeRule()]

        with patch("ink_writer.editor_wisdom.cli.DATA_DIR", Path("/fake")), patch.object(
            Path, "exists", return_value=True
        ):
            from ink_writer.editor_wisdom import retriever as ret_mod
            orig = ret_mod.Retriever
            ret_mod.Retriever = fake_retriever
            try:
                cmd_query("test", top_k=3)
            finally:
                ret_mod.Retriever = orig

        fake_retriever.return_value.retrieve.assert_called_once_with(query="test", k=3)


# ── stats tests ──


class TestStats:
    def _write_rules(self, data_dir: Path, rules: list[dict]) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "rules.json").write_text(
            json.dumps(rules, ensure_ascii=False), encoding="utf-8"
        )

    def test_stats_no_rules_file(self, tmp_path: Path):
        with patch("ink_writer.editor_wisdom.cli.DATA_DIR", tmp_path):
            code = cmd_stats()
        assert code == 1

    def test_stats_shows_total_and_categories(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        rules = [
            {"id": "EW-0001", "category": "opening", "rule": "r1"},
            {"id": "EW-0002", "category": "opening", "rule": "r2"},
            {"id": "EW-0003", "category": "hook", "rule": "r3"},
        ]
        self._write_rules(tmp_path, rules)

        with patch("ink_writer.editor_wisdom.cli.DATA_DIR", tmp_path):
            code = cmd_stats()

        assert code == 0
        out = capsys.readouterr().out
        assert "3" in out
        assert "opening" in out
        assert "hook" in out

    def test_stats_with_index(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        rules = [{"id": "EW-0001", "category": "opening", "rule": "r1"}]
        self._write_rules(tmp_path, rules)

        index_dir = tmp_path / "vector_index"
        index_dir.mkdir()
        (index_dir / "metadata.json").write_text(
            json.dumps([{"id": "EW-0001"}]), encoding="utf-8"
        )
        (index_dir / "rules.faiss").write_text("dummy", encoding="utf-8")

        with patch("ink_writer.editor_wisdom.cli.DATA_DIR", tmp_path):
            code = cmd_stats()

        assert code == 0
        out = capsys.readouterr().out
        assert "1" in out
        assert "UTC" in out

    def test_stats_no_index_shows_zero(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        rules = [{"id": "EW-0001", "category": "opening", "rule": "r1"}]
        self._write_rules(tmp_path, rules)

        with patch("ink_writer.editor_wisdom.cli.DATA_DIR", tmp_path):
            code = cmd_stats()

        assert code == 0
        out = capsys.readouterr().out
        assert "0" in out


# ── argparse integration tests ──


class TestArgparse:
    def test_help_text_exists(self):
        subprocess.run(
            [sys.executable, "-c", "from ink_writer.core.cli.ink import main"],
            capture_output=True, text=True, timeout=10, check=False, encoding="utf-8",
        )

    def test_pipeline_steps_match_scripts(self):
        for script_name, _label in PIPELINE_STEPS:
            script_path = SCRIPTS_DIR / script_name
            assert script_path.exists(), f"Pipeline script missing: {script_path}"
