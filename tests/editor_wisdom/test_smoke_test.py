"""Tests for scripts/editor-wisdom/smoke_test.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "editor-wisdom"


@pytest.fixture
def smoke_module():
    """Import smoke_test.py as a module."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        if "smoke_test" in sys.modules:
            mod = importlib.reload(sys.modules["smoke_test"])
        else:
            mod = importlib.import_module("smoke_test")
        yield mod
    finally:
        sys.path.pop(0)


class TestApiKeyCheck:
    def test_missing_key_returns_false(self, smoke_module):
        with patch.dict("os.environ", {}, clear=True), patch("shutil.which", return_value=None):
            assert smoke_module._check_api_key() is False

    def test_present_key_returns_true(self, smoke_module):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            assert smoke_module._check_api_key() is True

    def test_empty_key_returns_false(self, smoke_module):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}), patch("shutil.which", return_value=None):
            assert smoke_module._check_api_key() is False

    def test_cli_fallback_returns_true(self, smoke_module):
        with patch.dict("os.environ", {}, clear=True), patch("shutil.which", return_value="/usr/bin/claude"):
            assert smoke_module._check_api_key() is True


class TestSkippedWithoutApiKey:
    def test_main_exits_0_when_no_key(self, smoke_module, tmp_path):
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(smoke_module, "PROJECT_ROOT", tmp_path),
        ):
            rc = smoke_module.main()
            assert rc == 0
            report = (tmp_path / "reports" / "editor-wisdom-smoke-report.md")
            assert report.exists()
            content = report.read_text()
            assert "skipped" in content.lower()
            assert "ANTHROPIC_API_KEY" in content


class TestWriteReport:
    def test_report_contains_status_and_lines(self, smoke_module, tmp_path):
        with patch.object(smoke_module, "PROJECT_ROOT", tmp_path):
            lines = ["- step A done", "- step B done"]
            path = smoke_module._write_report(lines, "PASS")
            assert path.exists()
            content = path.read_text()
            assert "**Status**: PASS" in content
            assert "- step A done" in content
            assert "- step B done" in content


class TestBadChapterText:
    def test_bad_chapter_is_non_empty(self, smoke_module):
        assert len(smoke_module.BAD_CHAPTER) > 100

    def test_bad_chapter_contains_obvious_violations(self, smoke_module):
        text = smoke_module.BAD_CHAPTER
        assert "重生" in text
        assert "无敌" in text


class TestEnsureIndex:
    def test_existing_index_skips_rebuild(self, smoke_module, tmp_path):
        with patch.object(smoke_module, "PROJECT_ROOT", tmp_path):
            index_dir = tmp_path / "data" / "editor-wisdom" / "vector_index"
            index_dir.mkdir(parents=True)
            (index_dir / "rules.faiss").touch()
            lines: list[str] = []
            result = smoke_module._ensure_index(lines)
            assert result is True
            assert any("already exists" in l for l in lines)

    def test_missing_index_triggers_rebuild(self, smoke_module, tmp_path):
        with (
            patch.object(smoke_module, "PROJECT_ROOT", tmp_path),
            patch(
                "ink_writer.editor_wisdom.cli.cmd_rebuild", return_value=0
            ) as mock_rebuild,
        ):
            lines: list[str] = []
            result = smoke_module._ensure_index(lines)
            assert result is True
            mock_rebuild.assert_called_once()
            assert any("Rebuild finished" in l for l in lines)


class TestRunGateIntegration:
    def test_gate_blocks_with_mocked_checker(self, smoke_module, tmp_path):
        """Mock checker to always return low score; verify gate blocks."""
        call_count = 0

        def fake_checker(text, ch_no):
            nonlocal call_count
            call_count += 1
            return {
                "score": 0.1,
                "violations": [
                    {
                        "rule_id": "R001",
                        "severity": "hard",
                        "quote": "test",
                        "fix_suggestion": "fix it",
                    }
                ],
            }

        def fake_polish(text, violations, ch_no):
            return text

        from ink_writer.editor_wisdom.config import EditorWisdomConfig
        from ink_writer.editor_wisdom.review_gate import run_review_gate

        config = EditorWisdomConfig(enabled=True)

        result = run_review_gate(
            chapter_text=smoke_module.BAD_CHAPTER,
            chapter_no=1,
            project_root=str(tmp_path),
            checker_fn=fake_checker,
            polish_fn=fake_polish,
            config=config,
            max_retries=3,
        )

        assert not result.passed
        assert call_count == 3
        blocked_path = tmp_path / "chapters" / "1" / "blocked.md"
        assert blocked_path.exists()
