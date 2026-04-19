"""Tests for scripts/audit_architecture.py using fake fixture projects."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from audit_architecture import (
    build_import_graph,
    detect_agent_overlaps,
    find_cycles,
    find_repeated_prompt_fragments,
    find_unused_modules,
    generate_report,
    parse_agents,
    run_audit,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fixture_project(tmp_path: Path) -> Path:
    """Create a minimal fake project with known cycles and agents."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "mod_a.py").write_text("import mod_b\n", encoding="utf-8")
    (pkg / "mod_b.py").write_text("import mod_c\n", encoding="utf-8")
    (pkg / "mod_c.py").write_text("import mod_a\n", encoding="utf-8")
    (pkg / "mod_d.py").write_text("import os\n", encoding="utf-8")

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "checker-a.md").write_text(textwrap.dedent("""\
        ---
        name: checker-a
        description: 检查章节质量，输出结构化报告供润色步骤参考
        tools: Read
        ---

        # checker-a

        ## 输入
        - chapter_text: 章节正文
        - chapter_no: 章节号

        ## 输出格式
        ```json
        {"agent": "checker-a", "score": 0.8}
        ```

        ## 核心职责
        审查包中的正文和上章摘要进行质量检查。
        禁止读取 .db 文件和目录路径。
    """), encoding="utf-8")
    (agents_dir / "checker-b.md").write_text(textwrap.dedent("""\
        ---
        name: checker-b
        description: 检查章节质量，输出结构化报告供润色步骤参考
        tools: Read
        ---

        # checker-b

        ## 输入
        - chapter_text: 章节正文
        - chapter_no: 章节号

        ## 输出格式
        ```json
        {"agent": "checker-b", "score": 0.9}
        ```

        ## 核心职责
        审查包中的正文和上章摘要进行质量检查。
        禁止读取 .db 文件和目录路径。
    """), encoding="utf-8")
    (agents_dir / "writer.md").write_text(textwrap.dedent("""\
        ---
        name: writer
        description: 起草Agent，消费创作执行包生成符合大纲的章节草稿
        tools: Read, Write, Bash
        ---

        # writer

        ## 输入
        - project_root: 项目根目录
        - chapter: 章节号

        ## 输出格式
        - 章节草稿文件
    """), encoding="utf-8")
    return tmp_path


@pytest.fixture()
def no_cycle_project(tmp_path: Path) -> Path:
    """Project with no import cycles."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "mod_a.py").write_text("import os\n", encoding="utf-8")
    (pkg / "mod_b.py").write_text("import mod_a\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Import graph & cycle detection
# ---------------------------------------------------------------------------


class TestImportCycles:
    def test_detects_cycle(self, fixture_project: Path) -> None:
        graph, known = build_import_graph([fixture_project / "pkg"])
        cycles = find_cycles(graph)
        assert len(cycles) >= 1
        cycle_modules = {m for c in cycles for m in c}
        assert "mod_a" in cycle_modules or "pkg.mod_a" in cycle_modules

    def test_no_cycle(self, no_cycle_project: Path) -> None:
        graph, _ = build_import_graph([no_cycle_project / "pkg"])
        cycles = find_cycles(graph)
        assert cycles == []

    def test_graph_contains_known_modules(self, fixture_project: Path) -> None:
        _, known = build_import_graph([fixture_project / "pkg"])
        names = set(known.keys())
        assert "mod_a" in names
        assert "mod_b" in names
        assert "mod_c" in names
        assert "mod_d" in names


# ---------------------------------------------------------------------------
# Unused modules
# ---------------------------------------------------------------------------


class TestUnusedModules:
    def test_finds_unused(self, fixture_project: Path) -> None:
        graph, known = build_import_graph([fixture_project / "pkg"])
        unused = find_unused_modules(graph, known)
        assert "mod_d" in unused

    def test_cycle_members_not_unused(self, fixture_project: Path) -> None:
        graph, known = build_import_graph([fixture_project / "pkg"])
        unused = find_unused_modules(graph, known)
        assert "mod_a" not in unused
        assert "mod_b" not in unused
        assert "mod_c" not in unused


# ---------------------------------------------------------------------------
# Agent parsing
# ---------------------------------------------------------------------------


class TestAgentParsing:
    def test_parses_agents(self, fixture_project: Path) -> None:
        agents = parse_agents([fixture_project / "agents"])
        assert len(agents) == 3
        names = {a["name"] for a in agents}
        assert names == {"checker-a", "checker-b", "writer"}

    def test_extracts_io(self, fixture_project: Path) -> None:
        agents = parse_agents([fixture_project / "agents"])
        checker = next(a for a in agents if a["name"] == "checker-a")
        assert "chapter_text" in checker["inputs_raw"]
        assert "score" in checker["outputs_raw"]

    def test_extracts_tools(self, fixture_project: Path) -> None:
        agents = parse_agents([fixture_project / "agents"])
        writer = next(a for a in agents if a["name"] == "writer")
        assert "Write" in writer["tools"]

    def test_empty_dir(self, tmp_path: Path) -> None:
        agents = parse_agents([tmp_path / "nonexistent"])
        assert agents == []


# ---------------------------------------------------------------------------
# Agent overlaps
# ---------------------------------------------------------------------------


class TestAgentOverlaps:
    def test_detects_overlap(self, fixture_project: Path) -> None:
        agents = parse_agents([fixture_project / "agents"])
        overlaps = detect_agent_overlaps(agents)
        overlap_pairs = {(o["agent_a"], o["agent_b"]) for o in overlaps}
        assert ("checker-a", "checker-b") in overlap_pairs

    def test_writer_not_overlapping_with_checker(self, fixture_project: Path) -> None:
        agents = parse_agents([fixture_project / "agents"])
        overlaps = detect_agent_overlaps(agents)
        for o in overlaps:
            pair = {o["agent_a"], o["agent_b"]}
            if "writer" in pair:
                assert o["overlap_ratio"] < 0.35, "writer should not overlap with checkers"


# ---------------------------------------------------------------------------
# Prompt fragment dedup
# ---------------------------------------------------------------------------


class TestPromptDupes:
    def test_finds_shared_fragments(self, fixture_project: Path) -> None:
        agents = parse_agents([fixture_project / "agents"])
        dupes = find_repeated_prompt_fragments(agents, ngram_size=4)
        assert len(dupes) > 0
        has_checker_pair = any(
            "checker-a" in d["agents"] and "checker-b" in d["agents"]
            for d in dupes
        )
        assert has_checker_pair

    def test_unique_agents_no_dupes(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "alpha.md").write_text(textwrap.dedent("""\
            ---
            name: alpha
            description: completely unique description about stars
            tools: Read
            ---
            # alpha
            Stars and galaxies in the cosmos.
        """), encoding="utf-8")
        (agents_dir / "beta.md").write_text(textwrap.dedent("""\
            ---
            name: beta
            description: totally different about rivers
            tools: Write
            ---
            # beta
            Rivers and mountains on earth.
        """), encoding="utf-8")
        agents = parse_agents([agents_dir])
        dupes = find_repeated_prompt_fragments(agents, ngram_size=4)
        assert len(dupes) == 0


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


class TestReportGeneration:
    def test_report_is_valid_markdown(self, fixture_project: Path) -> None:
        graph, known = build_import_graph([fixture_project / "pkg"])
        cycles = find_cycles(graph)
        unused = find_unused_modules(graph, known)
        agents = parse_agents([fixture_project / "agents"])
        overlaps = detect_agent_overlaps(agents)
        dupes = find_repeated_prompt_fragments(agents)
        report = generate_report(cycles, unused, agents, overlaps, dupes, known)
        assert "# Architecture Audit Report" in report
        assert "## Summary" in report
        assert "## 3. Agent IO Contract Table" in report
        assert "| Agent |" in report

    def test_report_includes_cycle_info(self, fixture_project: Path) -> None:
        graph, known = build_import_graph([fixture_project / "pkg"])
        cycles = find_cycles(graph)
        report = generate_report(cycles, [], [], [], [], known)
        assert "mod_a" in report or "mod_b" in report or "mod_c" in report


# ---------------------------------------------------------------------------
# End-to-end run_audit
# ---------------------------------------------------------------------------


class TestRunAudit:
    def test_e2e(self, fixture_project: Path) -> None:
        output = fixture_project / "report.md"
        result = run_audit(
            fixture_project,
            python_packages=[fixture_project / "pkg"],
            agent_dirs=[fixture_project / "agents"],
            output_path=output,
        )
        assert output.exists()
        assert result["modules_scanned"] == 4
        assert len(result["agents"]) == 3
        assert len(result["cycles"]) >= 1
        assert isinstance(result["unused_modules"], list)
        assert isinstance(result["overlaps"], list)
        assert isinstance(result["prompt_duplicates"], list)

    def test_e2e_no_agents(self, no_cycle_project: Path) -> None:
        output = no_cycle_project / "report.md"
        result = run_audit(
            no_cycle_project,
            python_packages=[no_cycle_project / "pkg"],
            agent_dirs=[no_cycle_project / "nonexistent"],
            output_path=output,
        )
        assert output.exists()
        assert len(result["agents"]) == 0
        assert result["cycles"] == []

    def test_result_schema(self, fixture_project: Path) -> None:
        output = fixture_project / "report.md"
        result = run_audit(
            fixture_project,
            python_packages=[fixture_project / "pkg"],
            agent_dirs=[fixture_project / "agents"],
            output_path=output,
        )
        required_keys = {
            "cycles", "unused_modules", "agents", "overlaps",
            "prompt_duplicates", "modules_scanned", "report_path",
        }
        assert required_keys.issubset(set(result.keys()))
        for agent in result["agents"]:
            assert "name" in agent
            assert "description" in agent
            assert "tools" in agent


# ---------------------------------------------------------------------------
# Live project audit (integration)
# ---------------------------------------------------------------------------


class TestLiveProject:
    @pytest.mark.skipif(
        not (Path(__file__).resolve().parents[2] / "ink-writer" / "agents").is_dir(),
        reason="Live project agents not available",
    )
    def test_live_audit_runs(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        output = project_root / "reports" / "architecture_audit.md"
        result = run_audit(project_root, output_path=output)
        assert result["modules_scanned"] > 0
        assert len(result["agents"]) >= 14
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "Agent IO Contract Table" in content
