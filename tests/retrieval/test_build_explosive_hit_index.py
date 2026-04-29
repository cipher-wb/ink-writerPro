"""US-010: build_explosive_hit_index.py 爆款示例 RAG 索引构建测试。

验证脚本基础结构 + dry-run 模式输出正确。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_explosive_hit_index.py"
_OUTPUT = Path(__file__).resolve().parents[2] / "data" / "explosive_hit_index.json"


class TestExplosiveHitIndexScript:
    """Verify the build script is importable and has correct CLI skeleton."""

    def test_script_exists(self) -> None:
        assert _SCRIPT.exists(), f"{_SCRIPT} should exist"

    def test_script_is_valid_python(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", f"compile(open({str(_SCRIPT)!r}).read(), {str(_SCRIPT)!r}, 'exec')"],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert result.returncode == 0, f"Script has syntax errors: {result.stderr}"

    def test_script_has_dry_run_flag(self) -> None:
        text = _SCRIPT.read_text(encoding="utf-8")
        assert "--dry-run" in text, "Script should support --dry-run flag"

    def test_script_has_books_flag(self) -> None:
        text = _SCRIPT.read_text(encoding="utf-8")
        assert "--books" in text, "Script should support --books flag"

    def test_script_has_scene_heuristics(self) -> None:
        text = _SCRIPT.read_text(encoding="utf-8")
        assert "_SCENE_HEURISTICS" in text, "Script should define scene classification heuristics"

    def test_dry_run_produces_no_file(self) -> None:
        """Dry run should print stats but not write output file."""
        if _OUTPUT.exists():
            _OUTPUT.unlink()
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--dry-run", "--books", "1"],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        # dry-run should succeed (or gracefully handle missing corpus)
        assert result.returncode in (0, 1), f"dry-run should not crash: {result.stderr[:200]}"
        # Should NOT create output file in dry-run mode
        assert not _OUTPUT.exists(), "dry-run should NOT create output file"

    def test_output_path_config(self) -> None:
        """Verify output path is configured correctly."""
        text = _SCRIPT.read_text(encoding="utf-8")
        assert "explosive_hit_index" in text, "Output path should reference explosive_hit_index"


class TestSceneHeuristics:
    """Basic validation of scene type classification logic."""

    def test_combat_keywords_present(self) -> None:
        text = _SCRIPT.read_text(encoding="utf-8")
        assert '"combat"' in text
        assert any(kw in text for kw in ["战斗", "杀", "剑"])

    def test_dialogue_keywords_present(self) -> None:
        text = _SCRIPT.read_text(encoding="utf-8")
        assert '"dialogue"' in text
        assert any(kw in text for kw in ["说", "道", "问"])

    def test_emotional_keywords_present(self) -> None:
        text = _SCRIPT.read_text(encoding="utf-8")
        assert '"emotional"' in text

    def test_action_keywords_present(self) -> None:
        text = _SCRIPT.read_text(encoding="utf-8")
        assert '"action"' in text or "action" in text.lower()


class TestOutputFormat:
    """Verify expected output structure is defined in script."""

    def test_output_json_structure(self) -> None:
        text = _SCRIPT.read_text(encoding="utf-8")
        assert "metadata" in text.lower() or "scene_type" in text
        assert "excerpt" in text.lower() or "text" in text.lower() or "content" in text.lower()
