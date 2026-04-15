#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for reader-pull hook retry gate and fix_prompt builder."""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ink_writer.reader_pull.config import ReaderPullConfig, load_config
from ink_writer.reader_pull.fix_prompt_builder import (
    VIOLATION_FIX_TEMPLATES,
    build_fix_prompt,
    normalize_checker_output,
)
from ink_writer.reader_pull.hook_retry_gate import (
    HookGateAttempt,
    HookGateResult,
    run_hook_gate,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    (tmp_path / "chapters").mkdir()
    (tmp_path / "logs").mkdir()
    return tmp_path


@pytest.fixture()
def default_config() -> ReaderPullConfig:
    return ReaderPullConfig(
        enabled=True,
        score_threshold=70.0,
        golden_three_threshold=80.0,
        max_retries=2,
    )


SAMPLE_CHECKER_PASS = {
    "agent": "reader-pull-checker",
    "chapter": 10,
    "overall_score": 85,
    "pass": True,
    "issues": [],
    "hard_violations": [],
    "soft_suggestions": [],
    "fix_prompt": "",
    "metrics": {"hook_present": True, "hook_type": "危机钩"},
    "summary": "通过",
}

SAMPLE_CHECKER_FAIL = {
    "agent": "reader-pull-checker",
    "chapter": 10,
    "overall_score": 45,
    "pass": False,
    "issues": [],
    "hard_violations": [
        {
            "id": "HARD-004",
            "severity": "critical",
            "location": "全章",
            "description": "整章无冲突",
            "must_fix": True,
            "fix_suggestion": "加入核心冲突",
        }
    ],
    "soft_suggestions": [
        {
            "id": "SOFT_HOOK_STRENGTH",
            "severity": "medium",
            "location": "章末",
            "description": "钩子强度为weak",
            "suggestion": "将章末改为悬念",
        }
    ],
    "fix_prompt": "",
    "metrics": {"hook_present": False},
    "summary": "多项违规",
}

SAMPLE_CHECKER_BORDERLINE = {
    "agent": "reader-pull-checker",
    "chapter": 10,
    "overall_score": 60,
    "pass": False,
    "issues": [],
    "hard_violations": [],
    "soft_suggestions": [
        {
            "id": "SOFT_MICROPAYOFF",
            "severity": "medium",
            "location": "全章",
            "description": "微兑现0个，要求≥1",
            "suggestion": "添加能力或认可兑现",
        }
    ],
    "fix_prompt": "",
    "metrics": {"micropayoff_count": 0},
    "summary": "微兑现不足",
}

CHAPTER_TEXT = "这是一段测试正文。" * 100


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestConfig:
    def test_default_config(self) -> None:
        config = ReaderPullConfig()
        assert config.enabled is True
        assert config.score_threshold == 70.0
        assert config.golden_three_threshold == 80.0
        assert config.max_retries == 2

    def test_load_config_missing_file(self, tmp_path: Path) -> None:
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config == ReaderPullConfig()

    def test_load_config_from_yaml(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "reader-pull.yaml"
        yaml_path.write_text(
            "enabled: true\nscore_threshold: 65.0\nmax_retries: 3\n",
            encoding="utf-8",
        )
        config = load_config(yaml_path)
        assert config.score_threshold == 65.0
        assert config.max_retries == 3

    def test_load_config_invalid_yaml(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "bad.yaml"
        yaml_path.write_text("just a string", encoding="utf-8")
        config = load_config(yaml_path)
        assert config == ReaderPullConfig()


# ---------------------------------------------------------------------------
# fix_prompt_builder tests
# ---------------------------------------------------------------------------


class TestBuildFixPrompt:
    def test_empty_violations(self) -> None:
        assert build_fix_prompt([]) == ""

    def test_single_hard_violation(self) -> None:
        violations = [
            {
                "id": "HARD-004",
                "severity": "critical",
                "description": "整章无冲突",
                "fix_suggestion": "加入核心冲突",
            }
        ]
        prompt = build_fix_prompt(violations)
        assert "HARD-004" in prompt
        assert "冲突真空" in prompt
        assert "加入核心冲突" in prompt
        assert "追读力修复指令" in prompt

    def test_soft_violation_with_detail_template(self) -> None:
        violations = [
            {
                "id": "SOFT_HOOK_STRENGTH",
                "severity": "medium",
                "description": "weak",
                "suggestion": "改为悬念钩",
            }
        ]
        prompt = build_fix_prompt(violations)
        assert "SOFT_HOOK_STRENGTH" in prompt
        assert "钩子强度不足" in prompt

    def test_multiple_violations(self) -> None:
        violations = [
            {"id": "HARD-005", "severity": "high", "description": "开篇无张力"},
            {"id": "SOFT_MICROPAYOFF", "severity": "medium", "description": "0个"},
        ]
        prompt = build_fix_prompt(violations)
        assert "1." in prompt
        assert "2." in prompt
        assert "HARD-005" in prompt
        assert "SOFT_MICROPAYOFF" in prompt

    def test_unknown_violation_id(self) -> None:
        violations = [
            {"id": "CUSTOM_CHECK", "severity": "low", "description": "自定义问题"}
        ]
        prompt = build_fix_prompt(violations)
        assert "CUSTOM_CHECK" in prompt
        assert "自定义问题" in prompt

    def test_fix_prompt_footer(self) -> None:
        violations = [{"id": "HARD-001", "severity": "critical"}]
        prompt = build_fix_prompt(violations)
        assert "不得改变剧情事实" in prompt


class TestNormalizeCheckerOutput:
    def test_normalize_pass(self) -> None:
        result = normalize_checker_output(SAMPLE_CHECKER_PASS)
        assert result["score"] == 85.0
        assert result["violations"] == []
        assert result["fix_prompt"] == ""

    def test_normalize_fail_with_violations(self) -> None:
        result = normalize_checker_output(SAMPLE_CHECKER_FAIL)
        assert result["score"] == 45.0
        assert len(result["violations"]) == 2
        assert result["violations"][0]["id"] == "HARD-004"
        assert result["violations"][0]["must_fix"] is True
        assert result["violations"][1]["id"] == "SOFT_HOOK_STRENGTH"
        assert "追读力修复指令" in result["fix_prompt"]

    def test_normalize_uses_overall_score_fallback(self) -> None:
        raw = {"overall_score": 72, "hard_violations": [], "soft_suggestions": []}
        result = normalize_checker_output(raw)
        assert result["score"] == 72.0

    def test_normalize_prefers_score_over_overall_score(self) -> None:
        raw = {"score": 60, "overall_score": 72}
        result = normalize_checker_output(raw)
        assert result["score"] == 60.0

    def test_normalize_preserves_existing_fix_prompt(self) -> None:
        raw = {
            "overall_score": 50,
            "fix_prompt": "自定义修复指令",
            "hard_violations": [{"id": "HARD-001", "severity": "critical"}],
        }
        result = normalize_checker_output(raw)
        assert result["fix_prompt"] == "自定义修复指令"

    def test_normalize_issues_field(self) -> None:
        raw = {
            "overall_score": 55,
            "hard_violations": [],
            "soft_suggestions": [],
            "issues": [
                {"type": "structure_repetition", "severity": "medium", "description": "冲突模式重复"}
            ],
        }
        result = normalize_checker_output(raw)
        assert len(result["violations"]) == 1
        assert result["violations"][0]["id"] == "structure_repetition"

    def test_normalize_already_normalized(self) -> None:
        raw = {
            "score": 80,
            "violations": [{"id": "SOFT_NEXT_REASON", "severity": "medium"}],
            "fix_prompt": "already built",
        }
        result = normalize_checker_output(raw)
        assert result["score"] == 80.0
        assert len(result["violations"]) == 1
        assert result["fix_prompt"] == "already built"


# ---------------------------------------------------------------------------
# hook_retry_gate tests
# ---------------------------------------------------------------------------


class TestRunHookGate:
    def test_pass_on_first_check(
        self, tmp_project: Path, default_config: ReaderPullConfig
    ) -> None:
        checker_fn = MagicMock(return_value=SAMPLE_CHECKER_PASS)
        polish_fn = MagicMock(return_value="polished text")

        result = run_hook_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        assert result.passed is True
        assert result.final_score == 85.0
        assert len(result.attempts) == 1
        assert result.blocked_path is None
        assert result.final_text == CHAPTER_TEXT
        checker_fn.assert_called_once()
        polish_fn.assert_not_called()

    def test_fail_then_pass_after_polish(
        self, tmp_project: Path, default_config: ReaderPullConfig
    ) -> None:
        pass_result = dict(SAMPLE_CHECKER_PASS)
        pass_result["overall_score"] = 75

        checker_fn = MagicMock(
            side_effect=[SAMPLE_CHECKER_BORDERLINE, pass_result]
        )
        polish_fn = MagicMock(return_value="improved text")

        result = run_hook_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        assert result.passed is True
        assert len(result.attempts) == 2
        assert result.attempts[0].passed is False
        assert result.attempts[1].passed is True
        assert result.blocked_path is None
        assert result.final_text == "improved text"
        assert checker_fn.call_count == 2
        assert polish_fn.call_count == 1
        _, args, _ = polish_fn.mock_calls[0]
        assert args[0] == CHAPTER_TEXT
        assert "追读力修复指令" in args[1]

    def test_fail_twice_creates_hook_blocked(
        self, tmp_project: Path, default_config: ReaderPullConfig
    ) -> None:
        checker_fn = MagicMock(return_value=SAMPLE_CHECKER_FAIL)
        polish_fn = MagicMock(return_value="still bad text")

        result = run_hook_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        assert result.passed is False
        assert len(result.attempts) == 2
        assert result.blocked_path is not None
        assert result.blocked_path.endswith("hook_blocked.md")
        assert result.final_text is None

        assert os.path.exists(result.blocked_path)
        content = Path(result.blocked_path).read_text(encoding="utf-8")
        assert "追读力门禁阻断" in content
        assert "HARD-004" in content
        assert "45" in content

        assert checker_fn.call_count == 2
        assert polish_fn.call_count == 1

    def test_golden_three_uses_higher_threshold(
        self, tmp_project: Path, default_config: ReaderPullConfig
    ) -> None:
        score_75 = dict(SAMPLE_CHECKER_PASS)
        score_75["overall_score"] = 75

        checker_fn = MagicMock(return_value=score_75)
        polish_fn = MagicMock(return_value="polished")

        result_ch1 = run_hook_gate(
            CHAPTER_TEXT, 1, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )
        assert result_ch1.threshold == 80.0
        assert result_ch1.passed is False

        checker_fn.reset_mock()
        polish_fn.reset_mock()
        checker_fn.return_value = score_75

        result_ch10 = run_hook_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )
        assert result_ch10.threshold == 70.0
        assert result_ch10.passed is True

    def test_disabled_config_passes_immediately(
        self, tmp_project: Path
    ) -> None:
        config = ReaderPullConfig(enabled=False)
        checker_fn = MagicMock()
        polish_fn = MagicMock()

        result = run_hook_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=config,
        )

        assert result.passed is True
        assert result.final_score == 100.0
        checker_fn.assert_not_called()
        polish_fn.assert_not_called()

    def test_polish_fn_receives_fix_prompt(
        self, tmp_project: Path, default_config: ReaderPullConfig
    ) -> None:
        pass_result = dict(SAMPLE_CHECKER_PASS)
        pass_result["overall_score"] = 80

        checker_fn = MagicMock(
            side_effect=[SAMPLE_CHECKER_FAIL, pass_result]
        )
        polish_fn = MagicMock(return_value="fixed text")

        run_hook_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        polish_fn.assert_called_once()
        call_args = polish_fn.call_args
        fix_prompt_arg = call_args[0][1]
        assert "HARD-004" in fix_prompt_arg
        assert "冲突真空" in fix_prompt_arg

    def test_hook_blocked_contains_fix_prompt(
        self, tmp_project: Path, default_config: ReaderPullConfig
    ) -> None:
        checker_fn = MagicMock(return_value=SAMPLE_CHECKER_FAIL)
        polish_fn = MagicMock(return_value="still bad")

        result = run_hook_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        content = Path(result.blocked_path).read_text(encoding="utf-8")
        assert "修复提示" in content
        assert "追读力修复指令" in content

    def test_log_file_created(
        self, tmp_project: Path, default_config: ReaderPullConfig
    ) -> None:
        checker_fn = MagicMock(return_value=SAMPLE_CHECKER_PASS)
        polish_fn = MagicMock()

        run_hook_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        log_path = tmp_project / "logs" / "reader-pull" / "chapter_10.log"
        assert log_path.exists()
        log_content = log_path.read_text(encoding="utf-8")
        assert "追读力门禁检查" in log_content

    def test_attempts_recorded_correctly(
        self, tmp_project: Path, default_config: ReaderPullConfig
    ) -> None:
        checker_fn = MagicMock(return_value=SAMPLE_CHECKER_FAIL)
        polish_fn = MagicMock(return_value="polished")

        result = run_hook_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        assert len(result.attempts) == 2
        for i, attempt in enumerate(result.attempts, 1):
            assert attempt.attempt == i
            assert attempt.score == 45.0
            assert attempt.passed is False
            assert len(attempt.violations) > 0
            assert attempt.fix_prompt != ""

    def test_chapter_dir_created_for_blocked(
        self, tmp_project: Path, default_config: ReaderPullConfig
    ) -> None:
        checker_fn = MagicMock(return_value=SAMPLE_CHECKER_FAIL)
        polish_fn = MagicMock(return_value="bad")

        result = run_hook_gate(
            CHAPTER_TEXT, 99, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )

        assert (tmp_project / "chapters" / "99" / "hook_blocked.md").exists()


# ---------------------------------------------------------------------------
# Integration test: monkey-patch checker → assert polish called 2x → blocked
# ---------------------------------------------------------------------------


class TestIntegrationMonkeyPatch:
    def test_score_0_1_triggers_2_retries_then_blocked(
        self, tmp_project: Path
    ) -> None:
        """US-103 acceptance: checker returns score=0.1 → polish called
        up to max_retries-1 times → hook_blocked.md exists."""
        config = ReaderPullConfig(
            enabled=True,
            score_threshold=70.0,
            golden_three_threshold=80.0,
            max_retries=2,
        )

        low_score_result = {
            "overall_score": 10,
            "hard_violations": [
                {
                    "id": "HARD-004",
                    "severity": "critical",
                    "description": "冲突真空",
                    "fix_suggestion": "加冲突",
                }
            ],
            "soft_suggestions": [
                {
                    "id": "SOFT_HOOK_ANCHOR",
                    "severity": "high",
                    "description": "无期待锚点",
                    "suggestion": "加悬念",
                }
            ],
        }

        checker_fn = MagicMock(return_value=low_score_result)
        polish_calls: list[tuple[str, str, int]] = []

        def mock_polish(text: str, fix_prompt: str, chapter_no: int) -> str:
            polish_calls.append((text, fix_prompt, chapter_no))
            return text + "\n（已润色）"

        result = run_hook_gate(
            CHAPTER_TEXT, 5, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=mock_polish,
            config=config,
        )

        assert result.passed is False
        assert checker_fn.call_count == 2
        assert len(polish_calls) == 1

        assert result.blocked_path is not None
        blocked = Path(result.blocked_path)
        assert blocked.exists()
        assert blocked.name == "hook_blocked.md"

        content = blocked.read_text(encoding="utf-8")
        assert "追读力门禁阻断" in content
        assert "HARD-004" in content

        for _, fix_prompt, _ in polish_calls:
            assert "追读力修复指令" in fix_prompt
            assert "HARD-004" in fix_prompt


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_checker_returns_exactly_threshold(
        self, tmp_project: Path, default_config: ReaderPullConfig
    ) -> None:
        exact = {"overall_score": 70.0, "hard_violations": [], "soft_suggestions": []}
        checker_fn = MagicMock(return_value=exact)
        polish_fn = MagicMock()

        result = run_hook_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )
        assert result.passed is True
        polish_fn.assert_not_called()

    def test_checker_returns_just_below_threshold(
        self, tmp_project: Path, default_config: ReaderPullConfig
    ) -> None:
        below = {
            "overall_score": 69.9,
            "hard_violations": [],
            "soft_suggestions": [
                {"id": "SOFT_NEXT_REASON", "severity": "medium", "description": "弱"}
            ],
        }
        pass_result = {"overall_score": 75.0, "hard_violations": [], "soft_suggestions": []}
        checker_fn = MagicMock(side_effect=[below, pass_result])
        polish_fn = MagicMock(return_value="improved")

        result = run_hook_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )
        assert result.passed is True
        assert len(result.attempts) == 2

    def test_empty_checker_result(
        self, tmp_project: Path, default_config: ReaderPullConfig
    ) -> None:
        empty = {}
        checker_fn = MagicMock(return_value=empty)
        polish_fn = MagicMock(return_value="polished")

        result = run_hook_gate(
            CHAPTER_TEXT, 10, str(tmp_project),
            checker_fn=checker_fn,
            polish_fn=polish_fn,
            config=default_config,
        )
        assert result.passed is False
        assert result.final_score == 0.0
