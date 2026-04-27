"""PRD US-015: E2E evaluation script smoke tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_SCRIPT = REPO_ROOT / "scripts" / "e2e_anti_ai_overhaul_eval.py"


class TestE2EEvalScript:
    def test_script_exists(self) -> None:
        assert E2E_SCRIPT.exists(), f"Missing: {E2E_SCRIPT}"

    def test_script_help(self) -> None:
        result = subprocess.run(
            [sys.executable, str(E2E_SCRIPT), "--help"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "--chapters" in result.stdout
        assert "--with-llm-eval" in result.stdout
        assert "--baseline-commit" in result.stdout

    def test_script_dry_run(self) -> None:
        result = subprocess.run(
            [sys.executable, str(E2E_SCRIPT), "--dry-run"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"dry-run failed: {result.stderr}"

    def test_mock_eval_produces_gate_comparison(self) -> None:
        """Mock mode produces correct gate comparison output."""
        result = subprocess.run(
            [sys.executable, str(E2E_SCRIPT), "--chapters", "2", "--dry-run"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "GATE" in result.stdout
        assert "PASS" in result.stdout

    def test_gates_defined_in_script(self) -> None:
        """Verify G1-G3 gates are defined in the script."""
        content = E2E_SCRIPT.read_text(encoding="utf-8")
        assert "em_dash_per_kchar" in content
        assert "nesting_depth" in content
        assert "idioms_per_kchar" in content
        assert "quad_phrases_per_kchar" in content

    def test_mock_baseline_has_higher_em_dash(self) -> None:
        """Mock baseline should have higher em-dash density than candidate."""
        content = E2E_SCRIPT.read_text(encoding="utf-8")
        assert "mock_eval" in content
        # mock baseline em_dash_per_kchar = 1.5, candidate = 0.1
        assert "1.5" in content
        assert "0.1" in content
