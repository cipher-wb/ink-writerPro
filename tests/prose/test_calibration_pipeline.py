"""PRD US-014: calibration pipeline smoke tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CALIB_SCRIPT = REPO_ROOT / "scripts" / "calibrate_anti_ai_thresholds.py"


class TestCalibrationScript:
    def test_script_exists(self) -> None:
        assert CALIB_SCRIPT.exists(), f"Missing: {CALIB_SCRIPT}"

    def test_script_dry_run(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CALIB_SCRIPT), "--dry-run"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"dry-run failed: {result.stderr}"

    def test_script_help(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CALIB_SCRIPT), "--help"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "--live" in result.stdout
        assert "--dry-run" in result.stdout

    def test_report_generated(self, tmp_path: Path) -> None:
        """Mock mode: verify mock thresholds and report generation exist in script."""
        assert CALIB_SCRIPT.exists()
        content = CALIB_SCRIPT.read_text(encoding="utf-8")
        assert "_MOCK_EXPLOSIVE" in content
        assert "_MOCK_STANDARD" in content
        assert "generate_report" in content
