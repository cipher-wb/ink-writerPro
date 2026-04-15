"""Integration tests: run_review_gate is wired into step3_harness_gate orchestration."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ink-writer" / "scripts"))

from step3_harness_gate import (
    ChapterBlockedError,
    run_editor_wisdom_gate,
)

from ink_writer.editor_wisdom.config import EditorWisdomConfig


def _always_failing_checker(score: float = 0.1):
    calls: list[int] = []

    def checker(text: str, chapter_no: int) -> dict:
        calls.append(1)
        return {
            "agent": "editor-wisdom-checker",
            "chapter": chapter_no,
            "score": score,
            "violations": [
                {
                    "rule_id": "EW-0001",
                    "quote": "违规段落A",
                    "severity": "hard",
                    "fix_suggestion": "修复A",
                },
                {
                    "rule_id": "EW-0002",
                    "quote": "违规段落B",
                    "severity": "hard",
                    "fix_suggestion": "修复B",
                },
            ],
            "summary": "严重不达标",
        }

    return checker, calls


def _counting_polish():
    calls: list[int] = []

    def polish(text: str, violations: list[dict], chapter_no: int) -> str:
        calls.append(1)
        return text + f"\n润色第{len(calls)}次"

    return polish, calls


class TestReviewGateWiredBlocking:
    """Verify that run_review_gate is actually called through the orchestration entry."""

    def test_polish_called_three_times_then_blocked(self):
        checker_fn, checker_calls = _always_failing_checker(0.1)
        polish_fn, polish_calls = _counting_polish()

        config = EditorWisdomConfig(enabled=True, hard_gate_threshold=0.75)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "ink_writer.editor_wisdom.config.load_config", return_value=config
            ):
                with pytest.raises(ChapterBlockedError):
                    run_editor_wisdom_gate(
                        project_root=Path(tmpdir),
                        chapter_num=5,
                        chapter_text="这是一段质量很差的测试章节文本。",
                        checker_fn=checker_fn,
                        polish_fn=polish_fn,
                    )

            assert len(checker_calls) == 3
            assert len(polish_calls) == 2  # polish between attempts, not after last

    def test_blocked_md_exists_after_failure(self):
        checker_fn, _ = _always_failing_checker(0.1)
        polish_fn, _ = _counting_polish()

        config = EditorWisdomConfig(enabled=True, hard_gate_threshold=0.75)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "ink_writer.editor_wisdom.config.load_config", return_value=config
            ):
                with pytest.raises(ChapterBlockedError):
                    run_editor_wisdom_gate(
                        project_root=Path(tmpdir),
                        chapter_num=5,
                        chapter_text="测试章节。",
                        checker_fn=checker_fn,
                        polish_fn=polish_fn,
                    )

            blocked_path = Path(tmpdir) / "chapters" / "5" / "blocked.md"
            assert blocked_path.exists()
            content = blocked_path.read_text(encoding="utf-8")
            assert "EW-0001" in content
            assert "阻断" in content

    def test_final_chapter_not_emitted(self):
        checker_fn, _ = _always_failing_checker(0.1)
        polish_fn, _ = _counting_polish()

        config = EditorWisdomConfig(enabled=True, hard_gate_threshold=0.75)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "ink_writer.editor_wisdom.config.load_config", return_value=config
            ):
                with pytest.raises(ChapterBlockedError):
                    run_editor_wisdom_gate(
                        project_root=Path(tmpdir),
                        chapter_num=5,
                        chapter_text="测试章节。",
                        checker_fn=checker_fn,
                        polish_fn=polish_fn,
                    )

            chapter_dir = Path(tmpdir) / "chapters" / "5"
            chapter_files = [
                f for f in chapter_dir.iterdir()
                if f.name != "blocked.md"
            ] if chapter_dir.exists() else []
            assert len(chapter_files) == 0

    def test_raises_chapter_blocked_error(self):
        checker_fn, _ = _always_failing_checker(0.1)
        polish_fn, _ = _counting_polish()

        config = EditorWisdomConfig(enabled=True, hard_gate_threshold=0.75)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "ink_writer.editor_wisdom.config.load_config", return_value=config
            ):
                with pytest.raises(ChapterBlockedError, match=r"blocked after 3 attempts"):
                    run_editor_wisdom_gate(
                        project_root=Path(tmpdir),
                        chapter_num=5,
                        chapter_text="测试章节。",
                        checker_fn=checker_fn,
                        polish_fn=polish_fn,
                    )


class TestReviewGateWiredPassing:
    def test_passing_checker_returns_zero(self):
        def passing_checker(text: str, chapter_no: int) -> dict:
            return {
                "agent": "editor-wisdom-checker",
                "chapter": chapter_no,
                "score": 0.95,
                "violations": [],
                "summary": "达标",
            }

        polish_fn, polish_calls = _counting_polish()
        config = EditorWisdomConfig(enabled=True, hard_gate_threshold=0.75)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "ink_writer.editor_wisdom.config.load_config", return_value=config
            ):
                result = run_editor_wisdom_gate(
                    project_root=Path(tmpdir),
                    chapter_num=5,
                    chapter_text="高质量章节。",
                    checker_fn=passing_checker,
                    polish_fn=polish_fn,
                )

            assert result == 0
            assert len(polish_calls) == 0

    def test_disabled_config_skips_gate(self):
        config = EditorWisdomConfig(enabled=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "ink_writer.editor_wisdom.config.load_config", return_value=config
            ):
                result = run_editor_wisdom_gate(
                    project_root=Path(tmpdir),
                    chapter_num=5,
                )

            assert result == 0
