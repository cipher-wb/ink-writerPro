"""Tests for the Markdown / test-import reference scanners added to
``scripts/audit_architecture.py`` under US-023.

Motivation
----------
Prior to US-023 the audit only followed Python-level imports inside the
``ink_writer/`` and ``ink-writer/scripts/`` package roots. Modules reached
only via:

* ``from ink_writer.x.y import ...`` snippets embedded in SKILL.md /
  task docs / agent specs;
* ``python3 -m ink_writer.x.y`` invocations documented in Markdown;
* ``from ink_writer.x.y import ...`` in ``tests/`` (outside the scanned roots);

were falsely reported as "unused module candidates", inflating the number
from the project's real figure (~2) to 150+.

The tests below verify that the new scanners pick up each of these three
reference styles and that ``find_unused_modules`` honours them.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_architecture import (  # noqa: E402  (sys.path tweak above)
    build_import_graph,
    extract_md_module_references,
    extract_test_import_references,
    find_unused_modules,
    run_audit,
)


# ---------------------------------------------------------------------------
# Fixture: minimal fake project mimicking ink_writer layout
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_project(tmp_path: Path) -> Path:
    """Build a synthetic project with a package root, a tests dir, and MD files.

    Layout::

        <tmp_path>/
          ink_writer/
            __init__.py
            used_by_code.py    # imported by sibling module
            used_by_test.py    # imported only from tests/
            used_by_md.py      # imported only from SKILL.md
            used_by_dash_m.py  # referenced only via `python -m`
            entry.py           # imports used_by_code
            truly_unused.py    # no references at all
          tests/
            test_it.py
          ink-writer/
            skills/my-skill/SKILL.md
            agents/empty/     # dummy dir to satisfy run_audit
    """
    root = tmp_path
    pkg = root / "ink_writer"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "used_by_code.py").write_text("X = 1\n", encoding="utf-8")
    (pkg / "used_by_test.py").write_text("Y = 2\n", encoding="utf-8")
    (pkg / "used_by_md.py").write_text("Z = 3\n", encoding="utf-8")
    (pkg / "used_by_dash_m.py").write_text("W = 4\n", encoding="utf-8")
    (pkg / "entry.py").write_text(
        "from ink_writer.used_by_code import X\n"
    , encoding="utf-8")
    (pkg / "truly_unused.py").write_text("DEAD = 0\n", encoding="utf-8")

    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "test_it.py").write_text(
        "from ink_writer.used_by_test import Y\n"
    , encoding="utf-8")

    skill_dir = root / "ink-writer" / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(textwrap.dedent("""\
        # My Skill

        Run the pre-step:

        ```bash
        python3 -c "from ink_writer.used_by_md import Z; print(Z)"
        ```

        Or invoke the module directly:

        ```bash
        python -m ink_writer.used_by_dash_m --flag
        ```
    """), encoding="utf-8")

    # run_audit needs an agents directory to iterate (even if empty)
    (root / "ink-writer" / "agents").mkdir(parents=True)

    return root


# ---------------------------------------------------------------------------
# extract_md_module_references
# ---------------------------------------------------------------------------


class TestExtractMdModuleReferences:
    def test_picks_up_from_import_in_md(self, fake_project: Path) -> None:
        _, known = build_import_graph([fake_project / "ink_writer"])
        refs = extract_md_module_references(
            [fake_project / "ink-writer"], known
        )
        assert "used_by_md" in refs

    def test_picks_up_python_dash_m_invocations(self, fake_project: Path) -> None:
        _, known = build_import_graph([fake_project / "ink_writer"])
        refs = extract_md_module_references(
            [fake_project / "ink-writer"], known
        )
        assert "used_by_dash_m" in refs

    def test_does_not_report_unknown_modules(self, fake_project: Path) -> None:
        _, known = build_import_graph([fake_project / "ink_writer"])
        # Write an MD file that imports a non-existent module
        stray = fake_project / "ink-writer" / "skills" / "stray.md"
        stray.write_text("```python\nfrom ink_writer.ghost import foo\n```\n", encoding="utf-8")
        refs = extract_md_module_references(
            [fake_project / "ink-writer"], known
        )
        assert "ghost" not in refs

    def test_ignores_missing_root_directory(self, tmp_path: Path) -> None:
        # Must not raise when a configured md root doesn't exist.
        refs = extract_md_module_references([tmp_path / "missing"], {})
        assert refs == set()

    def test_handles_python3_minor_variants(
        self, fake_project: Path, tmp_path: Path
    ) -> None:
        _, known = build_import_graph([fake_project / "ink_writer"])
        md = fake_project / "ink-writer" / "skills" / "variants.md"
        md.write_text(textwrap.dedent("""\
            ```bash
            python3 -m ink_writer.used_by_md sub command
            python   -m   ink_writer.used_by_dash_m
            ```
        """), encoding="utf-8")
        refs = extract_md_module_references(
            [fake_project / "ink-writer"], known
        )
        assert {"used_by_md", "used_by_dash_m"}.issubset(refs)


# ---------------------------------------------------------------------------
# extract_test_import_references
# ---------------------------------------------------------------------------


class TestExtractTestImportReferences:
    def test_resolves_prefixed_imports(self, fake_project: Path) -> None:
        _, known = build_import_graph([fake_project / "ink_writer"])
        refs = extract_test_import_references(
            [fake_project / "tests"], known
        )
        assert "used_by_test" in refs

    def test_skips_non_existent_dir(self, tmp_path: Path) -> None:
        refs = extract_test_import_references([tmp_path / "nope"], {})
        assert refs == set()


# ---------------------------------------------------------------------------
# find_unused_modules with extra_references
# ---------------------------------------------------------------------------


class TestFindUnusedModulesWithExtraRefs:
    def test_md_and_test_refs_remove_false_positives(
        self, fake_project: Path
    ) -> None:
        graph, known = build_import_graph([fake_project / "ink_writer"])
        md_refs = extract_md_module_references(
            [fake_project / "ink-writer"], known
        )
        test_refs = extract_test_import_references(
            [fake_project / "tests"], known
        )
        unused = find_unused_modules(
            graph, known, extra_references=md_refs | test_refs
        )
        # Only the module that is truly unreferenced anywhere remains.
        assert "truly_unused" in unused
        for falsely_unused in (
            "used_by_code",
            "used_by_test",
            "used_by_md",
            "used_by_dash_m",
        ):
            assert falsely_unused not in unused, (
                f"{falsely_unused} is referenced somewhere and must not be "
                "flagged as unused"
            )

    def test_without_extra_refs_everything_external_is_unused(
        self, fake_project: Path
    ) -> None:
        graph, known = build_import_graph([fake_project / "ink_writer"])
        unused = find_unused_modules(graph, known)
        # Baseline behaviour: test/md-only modules WOULD be flagged without
        # the new scanners.
        assert "used_by_test" in unused
        assert "used_by_md" in unused
        assert "used_by_dash_m" in unused


# ---------------------------------------------------------------------------
# run_audit end-to-end — verifies the scanners are wired in
# ---------------------------------------------------------------------------


class TestRunAuditWiring:
    def test_run_audit_applies_md_and_test_scans(
        self, fake_project: Path
    ) -> None:
        output = fake_project / "audit.md"
        result = run_audit(
            fake_project,
            python_packages=[fake_project / "ink_writer"],
            agent_dirs=[fake_project / "ink-writer" / "agents"],
            md_dirs=[fake_project / "ink-writer"],
            test_dirs=[fake_project / "tests"],
            output_path=output,
        )
        unused = set(result["unused_modules"])
        assert "truly_unused" in unused
        assert "used_by_test" not in unused
        assert "used_by_md" not in unused
        assert "used_by_dash_m" not in unused

        # Result should expose what was scanned externally so consumers can
        # audit the scanner behaviour itself.
        assert "test_references" in result
        assert "md_references" in result
        assert "used_by_test" in result["test_references"]
        assert "used_by_md" in result["md_references"]
        assert "used_by_dash_m" in result["md_references"]

    def test_unused_count_below_threshold_on_live_project(self) -> None:
        """Guards the AC target: 'unused module candidates < 20'."""
        project_root = Path(__file__).resolve().parents[2]
        if not (project_root / "ink_writer").is_dir():
            pytest.skip("Live ink_writer package not available")
        output = project_root / "reports" / "architecture_audit.md"
        result = run_audit(project_root, output_path=output)
        unused = result["unused_modules"]
        assert len(unused) < 20, (
            f"Unused module candidates exploded to {len(unused)}: {unused}"
        )
