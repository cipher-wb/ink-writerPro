"""Tests for US-009: 8 Minor fixes consolidated."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from ink_writer.editor_wisdom.context_injection import build_editor_wisdom_section
from ink_writer.editor_wisdom.config import EditorWisdomConfig, InjectInto
from ink_writer.editor_wisdom.golden_three import GOLDEN_THREE_CATEGORIES
from ink_writer.editor_wisdom.retriever import Rule


class TestM1ReviewGateInitialization:
    """Covered in test_review_gate.py::TestReviewGateMaxRetriesZero."""
    pass


class TestM2ContextInjectionAllGoldenCategories:
    def test_chapter_1_queries_all_four_categories(self):
        """context_injection for ch<=3 must query all 4 golden-three categories."""
        queried_categories: list[str] = []

        def mock_retrieve(query: str, k: int = 5, category: str | None = None) -> list[Rule]:
            if category:
                queried_categories.append(category)
                return [Rule(id=f"EW-{category}", rule=f"rule-{category}", category=category, why="test", severity="hard")]
            return [Rule(id="EW-base", rule="base rule", category="pacing", why="test", severity="soft")]

        mock_retriever = MagicMock()
        mock_retriever.retrieve = mock_retrieve

        config = EditorWisdomConfig(inject_into=InjectInto(context=True))
        section = build_editor_wisdom_section(
            chapter_outline="测试大纲",
            chapter_no=1,
            config=config,
            retriever=mock_retriever,
        )

        assert not section.empty
        assert set(queried_categories) == set(GOLDEN_THREE_CATEGORIES)

    def test_chapter_5_does_not_query_golden_categories(self):
        """context_injection for ch>3 should NOT query golden-three categories."""
        queried_categories: list[str] = []

        def mock_retrieve(query: str, k: int = 5, category: str | None = None) -> list[Rule]:
            if category:
                queried_categories.append(category)
            return [Rule(id="EW-base", rule="base rule", category="pacing", why="test", severity="soft")]

        mock_retriever = MagicMock()
        mock_retriever.retrieve = mock_retrieve

        config = EditorWisdomConfig(inject_into=InjectInto(context=True))
        build_editor_wisdom_section(
            chapter_outline="测试大纲",
            chapter_no=5,
            config=config,
            retriever=mock_retriever,
        )

        assert queried_categories == []


class TestM3CheckerCodeFenceStripping:
    def test_fence_with_language_tag(self):
        """Code fence with ```json ... ``` should be stripped correctly."""
        raw = '```json\n{"violations": [], "summary": "ok"}\n```'
        match = re.match(r'^```(?:\w+)?\n([\s\S]*?)\n```$', raw)
        assert match is not None
        inner = match.group(1).strip()
        parsed = json.loads(inner)
        assert parsed["summary"] == "ok"

    def test_fence_without_language_tag(self):
        raw = '```\n{"violations": [], "summary": "ok"}\n```'
        match = re.match(r'^```(?:\w+)?\n([\s\S]*?)\n```$', raw)
        assert match is not None
        inner = match.group(1).strip()
        parsed = json.loads(inner)
        assert parsed["summary"] == "ok"

    def test_no_fence_passes_through(self):
        raw = '{"violations": [], "summary": "ok"}'
        match = re.match(r'^```(?:\w+)?\n([\s\S]*?)\n```$', raw)
        assert match is None

    def test_multiline_json_inside_fence(self):
        raw = '```json\n{\n  "violations": [\n    {"rule_id": "EW-01", "quote": "x", "severity": "hard", "fix_suggestion": "y"}\n  ],\n  "summary": "issues"\n}\n```'
        match = re.match(r'^```(?:\w+)?\n([\s\S]*?)\n```$', raw)
        assert match is not None
        parsed = json.loads(match.group(1).strip())
        assert len(parsed["violations"]) == 1


class TestM5CleanHashReproducibility:
    def test_minhash_is_deterministic(self):
        """blake2b-based minhash must be deterministic across runs."""
        import hashlib as _hashlib

        def _minhash_signature(ngrams: list[str], num_perm: int = 128) -> list[int]:
            if not ngrams:
                return [0] * num_perm
            sig = []
            for i in range(num_perm):
                min_val = min(
                    int.from_bytes(
                        _hashlib.blake2b(f"{i}:{ng}".encode(), digest_size=4).digest(),
                        "big",
                    )
                    for ng in ngrams
                )
                sig.append(min_val)
            return sig

        ngrams = ["测试", "试文", "文本"]
        sig1 = _minhash_signature(ngrams)
        sig2 = _minhash_signature(ngrams)
        assert sig1 == sig2
        assert len(sig1) == 128
        assert all(isinstance(v, int) for v in sig1)

    def test_no_builtin_hash_in_clean_script(self):
        """02_clean.py must not use builtin hash() for minhash."""
        script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "editor-wisdom" / "02_clean.py"
        source = script_path.read_text()
        import re as _re
        matches = _re.findall(r'\bhash\s*\(', source)
        assert len(matches) == 0, f"Found builtin hash() calls in 02_clean.py: {matches}"


class TestM7GitignoreLogsEditorWisdom:
    def test_logs_editor_wisdom_in_gitignore(self):
        gitignore = (Path(__file__).resolve().parent.parent.parent / ".gitignore").read_text()
        assert "logs/editor-wisdom/" in gitignore


class TestM8CliRebuildFromStep:
    def test_from_step_skips_earlier(self):
        from ink_writer.editor_wisdom.cli import cmd_rebuild, PIPELINE_STEPS

        executed_scripts: list[str] = []

        def mock_run(cmd, cwd=None):
            script = Path(cmd[1]).name
            executed_scripts.append(script)
            result = MagicMock()
            result.returncode = 0
            return result

        with patch("ink_writer.editor_wisdom.cli.subprocess.run", side_effect=mock_run):
            with patch("ink_writer.editor_wisdom.cli.SCRIPTS_DIR", Path(tempfile.mkdtemp())):
                # Create dummy script files
                scripts_dir = Path(tempfile.mkdtemp())
                for name, _ in PIPELINE_STEPS:
                    (scripts_dir / name).touch()

                with patch("ink_writer.editor_wisdom.cli.SCRIPTS_DIR", scripts_dir):
                    ret = cmd_rebuild(from_step=4)

        assert ret == 0
        assert len(executed_scripts) == 3
        assert executed_scripts[0] == "04_build_kb.py"
        assert executed_scripts[-1] == "06_build_index.py"

    def test_from_step_invalid_returns_error(self):
        from ink_writer.editor_wisdom.cli import cmd_rebuild
        assert cmd_rebuild(from_step=0) == 1
        assert cmd_rebuild(from_step=7) == 1

    def test_from_step_1_runs_all(self):
        from ink_writer.editor_wisdom.cli import cmd_rebuild, PIPELINE_STEPS

        executed_scripts: list[str] = []

        def mock_run(cmd, cwd=None):
            executed_scripts.append(Path(cmd[1]).name)
            result = MagicMock()
            result.returncode = 0
            return result

        scripts_dir = Path(tempfile.mkdtemp())
        for name, _ in PIPELINE_STEPS:
            (scripts_dir / name).touch()

        with patch("ink_writer.editor_wisdom.cli.subprocess.run", side_effect=mock_run):
            with patch("ink_writer.editor_wisdom.cli.SCRIPTS_DIR", scripts_dir):
                ret = cmd_rebuild(from_step=1)

        assert ret == 0
        assert len(executed_scripts) == 6
