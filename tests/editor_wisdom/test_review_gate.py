"""Tests for editor-wisdom hard gate: review_gate.py."""

from __future__ import annotations

import os
import tempfile

from ink_writer.editor_wisdom.config import EditorWisdomConfig
from ink_writer.editor_wisdom.review_gate import run_review_gate


def _low_score_checker(score: float = 0.3):
    """Return a checker that always returns the given low score."""
    def checker(text: str, chapter_no: int) -> dict:
        return {
            "agent": "editor-wisdom-checker",
            "chapter": chapter_no,
            "score": score,
            "violations": [
                {
                    "rule_id": "EW-0001",
                    "quote": "测试违规段落",
                    "severity": "hard",
                    "fix_suggestion": "修复建议A",
                },
                {
                    "rule_id": "EW-0002",
                    "quote": "另一处违规",
                    "severity": "soft",
                    "fix_suggestion": "修复建议B",
                },
            ],
            "summary": "质量不达标",
        }
    return checker


def _passing_checker(score: float = 0.9):
    """Return a checker that always passes."""
    def checker(text: str, chapter_no: int) -> dict:
        return {
            "agent": "editor-wisdom-checker",
            "chapter": chapter_no,
            "score": score,
            "violations": [],
            "summary": "质量达标",
        }
    return checker


def _noop_polish(text: str, violations: list[dict], chapter_no: int) -> str:
    return text + "\n（已润色）"


def _counting_polish():
    """Return a polish fn that counts calls."""
    calls: list[int] = []

    def polish(text: str, violations: list[dict], chapter_no: int) -> str:
        calls.append(1)
        return text + f"\n润色第{len(calls)}次"

    return polish, calls


class TestReviewGateAlwaysFails:
    def test_three_polish_attempts(self):
        """Checker always returns low score → 3 attempts, blocked.md exists."""
        polish_fn, polish_calls = _counting_polish()
        config = EditorWisdomConfig(hard_gate_threshold=0.75)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="测试章节正文内容。",
                chapter_no=5,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.3),
                polish_fn=polish_fn,
                config=config,
            )

            assert not result.passed
            assert len(result.attempts) == 3
            assert len(polish_calls) == 2  # polish called between attempts, not after last
            assert result.final_text is None

    def test_blocked_md_exists(self):
        """After 3 failures, blocked.md is created."""
        config = EditorWisdomConfig(hard_gate_threshold=0.75)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="测试章节正文内容。",
                chapter_no=5,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.3),
                polish_fn=_noop_polish,
                config=config,
            )

            assert result.blocked_path is not None
            assert os.path.exists(result.blocked_path)
            assert result.blocked_path.endswith("blocked.md")

            with open(result.blocked_path, encoding="utf-8") as f:
                content = f.read()
            assert "EW-0001" in content
            assert "阻断" in content

    def test_no_final_chapter_emitted(self):
        """When blocked, final_text is None (chapter not emitted)."""
        config = EditorWisdomConfig(hard_gate_threshold=0.75)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="测试章节正文内容。",
                chapter_no=5,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.3),
                polish_fn=_noop_polish,
                config=config,
            )

            assert result.final_text is None

    def test_log_file_created(self):
        """Each attempt is logged to logs/editor-wisdom/chapter_{n}.log."""
        config = EditorWisdomConfig(hard_gate_threshold=0.75)

        with tempfile.TemporaryDirectory() as tmpdir:
            run_review_gate(
                chapter_text="测试章节正文内容。",
                chapter_no=5,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.3),
                polish_fn=_noop_polish,
                config=config,
            )

            log_path = os.path.join(tmpdir, "logs", "editor-wisdom", "chapter_5.log")
            assert os.path.exists(log_path)
            with open(log_path, encoding="utf-8") as f:
                log_content = f.read()
            assert "第 1 次检查" in log_content
            assert "第 2 次检查" in log_content
            assert "第 3 次检查" in log_content
            assert "阻断" in log_content


class TestReviewGateMaxRetriesZero:
    def test_max_retries_zero_no_unbound_error(self):
        """max_retries=0 must not raise UnboundLocalError for violations/score."""
        config = EditorWisdomConfig(hard_gate_threshold=0.75)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="测试内容。",
                chapter_no=5,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.3),
                polish_fn=_noop_polish,
                config=config,
                max_retries=0,
            )

            assert not result.passed
            assert len(result.attempts) == 0
            assert result.blocked_path is not None
            assert os.path.exists(result.blocked_path)
            assert result.final_score == 1.0


class TestReviewGatePasses:
    def test_first_attempt_pass(self):
        """Checker passes on first attempt → no polish calls."""
        polish_fn, polish_calls = _counting_polish()
        config = EditorWisdomConfig(hard_gate_threshold=0.75)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="高质量章节。",
                chapter_no=1,
                project_root=tmpdir,
                checker_fn=_passing_checker(0.9),
                polish_fn=polish_fn,
                config=config,
            )

            assert result.passed
            assert len(result.attempts) == 1
            assert len(polish_calls) == 0
            assert result.blocked_path is None
            assert result.final_text is not None

    def test_pass_after_retry(self):
        """Fails first, passes on second attempt."""
        call_count = [0]

        def improving_checker(text: str, chapter_no: int) -> dict:
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "agent": "editor-wisdom-checker",
                    "chapter": chapter_no,
                    "score": 0.5,
                    "violations": [{"rule_id": "EW-0001", "quote": "问题", "severity": "hard", "fix_suggestion": "修"}],
                    "summary": "需要修复",
                }
            return {
                "agent": "editor-wisdom-checker",
                "chapter": chapter_no,
                "score": 0.9,
                "violations": [],
                "summary": "已改善",
            }

        config = EditorWisdomConfig(hard_gate_threshold=0.75)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="章节内容。",
                chapter_no=10,
                project_root=tmpdir,
                checker_fn=improving_checker,
                polish_fn=_noop_polish,
                config=config,
            )

            assert result.passed
            assert len(result.attempts) == 2
            assert result.attempts[0].passed is False
            assert result.attempts[1].passed is True


class TestGoldenThreeThreshold:
    def test_chapters_1_3_use_golden_threshold(self):
        """Chapters 1-3 use golden_three_hard_threshold instead of hard_gate_threshold.

        US-015: switched to dual-threshold API; golden_three_hard_threshold is the
        blocking bar. This test forces the hard threshold to 0.85 to verify routing.
        """
        config = EditorWisdomConfig(
            hard_gate_threshold=0.75,
            golden_three_hard_threshold=0.85,
        )

        def score_80_checker(text: str, chapter_no: int) -> dict:
            return {
                "agent": "editor-wisdom-checker",
                "chapter": chapter_no,
                "score": 0.80,
                "violations": [{"rule_id": "EW-0001", "quote": "问题", "severity": "soft", "fix_suggestion": "修"}],
                "summary": "中等质量",
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            result_ch1 = run_review_gate(
                chapter_text="第一章内容。",
                chapter_no=1,
                project_root=tmpdir,
                checker_fn=score_80_checker,
                polish_fn=_noop_polish,
                config=config,
            )
            assert not result_ch1.passed
            assert result_ch1.threshold == 0.85

        with tempfile.TemporaryDirectory() as tmpdir:
            result_ch10 = run_review_gate(
                chapter_text="第十章内容。",
                chapter_no=10,
                project_root=tmpdir,
                checker_fn=score_80_checker,
                polish_fn=_noop_polish,
                config=config,
            )
            assert result_ch10.passed
            assert result_ch10.threshold == 0.75


class TestAttemptTracking:
    def test_attempts_record_scores(self):
        config = EditorWisdomConfig(hard_gate_threshold=0.75)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="内容。",
                chapter_no=5,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.3),
                polish_fn=_noop_polish,
                config=config,
            )

            for attempt in result.attempts:
                assert attempt.score == 0.3
                assert not attempt.passed
                assert len(attempt.violations) == 2

    def test_blocked_md_contains_violations(self):
        config = EditorWisdomConfig(hard_gate_threshold=0.75)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="内容。",
                chapter_no=7,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.3),
                polish_fn=_noop_polish,
                config=config,
            )

            with open(result.blocked_path, encoding="utf-8") as f:
                content = f.read()
            assert "EW-0001" in content
            assert "EW-0002" in content
            assert "0.3" in content
            assert "0.75" in content
