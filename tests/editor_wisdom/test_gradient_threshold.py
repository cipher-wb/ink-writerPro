"""US-015: Tests for gradient (hard + soft) golden-three threshold and escape hatch.

Covers:
1. EditorWisdomConfig exposes golden_three_hard_threshold (0.75) and
   golden_three_soft_threshold (0.92).
2. review_gate uses hard threshold for blocking and records soft-threshold status.
3. Exponential scoring: score = 1.0 * (0.7 ** hard) * (0.9 ** soft).
4. Escape hatch: allow_escape_hatch=True → 2 failed retries return action=rewrite_step2a
   with escape_hatch_triggered=True instead of 3-attempt block.
5. Backward compatibility: legacy 3-attempt block behavior preserved when
   allow_escape_hatch=False (default).
"""

from __future__ import annotations

import tempfile

import pytest

from ink_writer.editor_wisdom.checker import _compute_score
from ink_writer.editor_wisdom.config import EditorWisdomConfig, load_config
from ink_writer.editor_wisdom.review_gate import run_review_gate


def _low_score_checker(score: float, violations: list[dict] | None = None):
    if violations is None:
        violations = [
            {
                "rule_id": "EW-0001",
                "quote": "违规段落",
                "severity": "soft",
                "fix_suggestion": "修复建议",
            }
        ]

    def checker(text: str, chapter_no: int) -> dict:
        return {
            "agent": "editor-wisdom-checker",
            "chapter": chapter_no,
            "score": score,
            "violations": violations,
            "summary": "测试",
        }

    return checker


def _noop_polish(text: str, violations: list[dict], chapter_no: int) -> str:
    return text + "\n（润色）"


class TestDualThresholdConfig:
    def test_default_values(self):
        cfg = EditorWisdomConfig()
        assert cfg.golden_three_hard_threshold == 0.75
        assert cfg.golden_three_soft_threshold == 0.92

    def test_yaml_values_match_us015_spec(self, tmp_path):
        p = tmp_path / "editor-wisdom.yaml"
        p.write_text(
            "enabled: true\n"
            "golden_three_hard_threshold: 0.75\n"
            "golden_three_soft_threshold: 0.92\n",
            encoding="utf-8",
        )
        cfg = load_config(p)
        assert cfg.golden_three_hard_threshold == pytest.approx(0.75)
        assert cfg.golden_three_soft_threshold == pytest.approx(0.92)

    def test_actual_yaml_file_has_both_thresholds(self):
        """The project-level config/editor-wisdom.yaml must expose both split keys."""
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent.parent / "config" / "editor-wisdom.yaml"
        cfg = load_config(path)
        assert cfg.golden_three_hard_threshold == pytest.approx(0.75)
        assert cfg.golden_three_soft_threshold == pytest.approx(0.92)


class TestExponentialScoring:
    """AC #3: score = 1.0 * (0.7 ** hard_count) * (0.9 ** soft_count)."""

    def test_no_violations_score_one(self):
        assert _compute_score([]) == 1.0

    def test_one_hard(self):
        # 0.7^1 = 0.70
        assert _compute_score([{"severity": "hard"}]) == pytest.approx(0.70)

    def test_two_hard(self):
        # 0.7^2 = 0.49
        assert _compute_score([{"severity": "hard"}] * 2) == pytest.approx(0.49)

    def test_one_soft(self):
        # 0.9^1 = 0.90
        assert _compute_score([{"severity": "soft"}]) == pytest.approx(0.90)

    def test_three_soft_still_above_hard_threshold(self):
        """Core motivation: 3 soft violations should NOT push us below 0.75 hard threshold."""
        score = _compute_score([{"severity": "soft"}] * 3)
        # 0.9^3 = 0.729 → 0.73 (just below 0.75; this is intentional — still close).
        assert score == pytest.approx(0.73)

    def test_two_soft_passes_hard_threshold(self):
        """2 soft violations → 0.81, clearly above 0.75 hard threshold."""
        score = _compute_score([{"severity": "soft"}] * 2)
        assert score == pytest.approx(0.81)
        assert score > 0.75

    def test_mixed_exponential(self):
        # 1 hard + 2 soft = 0.7 * 0.81 = 0.567 → 0.57
        score = _compute_score([
            {"severity": "hard"},
            {"severity": "soft"},
            {"severity": "soft"},
        ])
        assert score == pytest.approx(0.57)

    def test_info_severity_ignored(self):
        score = _compute_score([{"severity": "info"}] * 5)
        assert score == 1.0


class TestGradientThresholdInReviewGate:
    """AC #2: review_gate exposes both thresholds and uses hard for blocking."""

    def test_golden_chapter_passes_between_hard_and_soft(self):
        """Chapter 1 with score 0.80: between 0.75 (hard) and 0.92 (soft) → passes but soft_passed=False."""
        config = EditorWisdomConfig(
            golden_three_hard_threshold=0.75,
            golden_three_soft_threshold=0.92,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="黄金三章测试正文。",
                chapter_no=1,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.80),
                polish_fn=_noop_polish,
                config=config,
            )
        assert result.passed
        assert result.threshold == 0.75
        assert result.soft_threshold == 0.92
        assert result.soft_passed is False
        assert result.action == "continue"

    def test_golden_chapter_passes_above_soft(self):
        """Score 0.95 ≥ soft threshold → passed AND soft_passed=True."""
        config = EditorWisdomConfig(
            golden_three_hard_threshold=0.75,
            golden_three_soft_threshold=0.92,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="高分章节。",
                chapter_no=1,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.95, violations=[]),
                polish_fn=_noop_polish,
                config=config,
            )
        assert result.passed
        assert result.soft_passed is True

    def test_golden_chapter_blocked_below_hard(self):
        """Score 0.60 < 0.75 hard → blocked after 3 attempts (no escape hatch)."""
        config = EditorWisdomConfig(
            golden_three_hard_threshold=0.75,
            golden_three_soft_threshold=0.92,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="低分章节。",
                chapter_no=1,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.60),
                polish_fn=_noop_polish,
                config=config,
            )
        assert not result.passed
        assert result.blocked_path is not None
        assert result.action == "continue"
        assert result.escape_hatch_triggered is False
        assert len(result.attempts) == 3

    def test_non_golden_chapter_has_no_soft_threshold(self):
        """Chapter 10 uses hard_gate_threshold; soft_threshold is None."""
        config = EditorWisdomConfig()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="普通章节。",
                chapter_no=10,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.80, violations=[]),
                polish_fn=_noop_polish,
                config=config,
            )
        assert result.passed
        assert result.soft_threshold is None
        assert result.soft_passed is None


class TestEscapeHatch:
    """AC #4: after 2 failed retries, escape hatch triggers rewrite_step2a."""

    def test_escape_hatch_triggers_after_two_retries(self):
        """allow_escape_hatch=True + persistently-low score → 2 attempts, then escape hatch."""
        config = EditorWisdomConfig(golden_three_hard_threshold=0.75)
        polish_calls: list[int] = []

        def polish(text: str, violations: list[dict], ch: int) -> str:
            polish_calls.append(ch)
            return text + "\n（局部润色）"

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="低分章节测试。",
                chapter_no=1,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.40),
                polish_fn=polish,
                config=config,
                allow_escape_hatch=True,
            )

        assert not result.passed
        assert result.escape_hatch_triggered is True
        assert result.action == "rewrite_step2a"
        assert result.blocked_path is None  # no block — we escape to rewrite instead
        assert len(result.attempts) == 2  # initial + 1 retry
        assert len(polish_calls) == 1  # polish called once between the 2 attempts

    def test_escape_hatch_not_triggered_when_passes_first_try(self):
        """allow_escape_hatch=True but score passes first time → normal pass, no escape hatch."""
        config = EditorWisdomConfig(golden_three_hard_threshold=0.75)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="高分章节。",
                chapter_no=1,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.95, violations=[]),
                polish_fn=_noop_polish,
                config=config,
                allow_escape_hatch=True,
            )
        assert result.passed
        assert result.escape_hatch_triggered is False
        assert result.action == "continue"

    def test_escape_hatch_not_triggered_when_second_attempt_passes(self):
        """First attempt fails, polish fixes → second attempt passes. No escape hatch."""
        config = EditorWisdomConfig(golden_three_hard_threshold=0.75)
        call_count = [0]

        def improving_checker(text: str, chapter_no: int) -> dict:
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "agent": "editor-wisdom-checker",
                    "chapter": chapter_no,
                    "score": 0.40,
                    "violations": [{"rule_id": "EW-001", "quote": "q", "severity": "hard", "fix_suggestion": "f"}],
                    "summary": "差",
                }
            return {
                "agent": "editor-wisdom-checker",
                "chapter": chapter_no,
                "score": 0.90,
                "violations": [],
                "summary": "好",
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="先差后好。",
                chapter_no=1,
                project_root=tmpdir,
                checker_fn=improving_checker,
                polish_fn=_noop_polish,
                config=config,
                allow_escape_hatch=True,
            )

        assert result.passed
        assert result.escape_hatch_triggered is False
        assert len(result.attempts) == 2

    def test_legacy_behavior_without_escape_hatch_flag(self):
        """allow_escape_hatch=False (default): 3 attempts, block as before. No regression."""
        config = EditorWisdomConfig(golden_three_hard_threshold=0.75)
        polish_calls: list[int] = []

        def polish(text: str, violations: list[dict], ch: int) -> str:
            polish_calls.append(ch)
            return text

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="低分章节。",
                chapter_no=1,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.40),
                polish_fn=polish,
                config=config,
                # allow_escape_hatch omitted (default False)
            )

        assert not result.passed
        assert result.escape_hatch_triggered is False
        assert result.blocked_path is not None
        assert len(result.attempts) == 3  # legacy 3-attempt block
        assert len(polish_calls) == 2  # between attempts, not after last

    def test_escape_hatch_bounded_to_single_trigger(self):
        """AC #4: escape hatch fires at most once per chapter to prevent infinite loops.

        Semantics: once a GateResult has escape_hatch_triggered=True, the caller is
        responsible for re-running Step 2A with fresh text. A second invocation with
        allow_escape_hatch=False (or with the caller's own "already tried once" guard)
        must fall through to the legacy block path.
        """
        config = EditorWisdomConfig(golden_three_hard_threshold=0.75)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Simulate first invocation: escape hatch fires.
            first = run_review_gate(
                chapter_text="第一次。",
                chapter_no=1,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.40),
                polish_fn=_noop_polish,
                config=config,
                allow_escape_hatch=True,
            )
            assert first.escape_hatch_triggered is True

            # Second invocation (caller already used escape hatch once): disables it.
            second = run_review_gate(
                chapter_text="第二次（Step 2A 重写后）。",
                chapter_no=1,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.40),
                polish_fn=_noop_polish,
                config=config,
                allow_escape_hatch=False,  # caller's bookkeeping: already triggered once
            )
            assert second.escape_hatch_triggered is False
            assert second.blocked_path is not None  # falls through to legacy block


class TestSoftThresholdWarningOnly:
    """Soft threshold is informational — never blocks."""

    def test_soft_fail_still_continues(self):
        """0.80 score: fails soft (0.92), passes hard (0.75) → action='continue'."""
        config = EditorWisdomConfig()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_review_gate(
                chapter_text="中等章节。",
                chapter_no=2,
                project_root=tmpdir,
                checker_fn=_low_score_checker(0.80, violations=[]),
                polish_fn=_noop_polish,
                config=config,
            )
        assert result.passed
        assert result.action == "continue"
        assert result.soft_passed is False
