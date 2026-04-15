"""Tests for US-401 agent topology refactor: thread-lifecycle-tracker merge."""

from __future__ import annotations

from pathlib import Path

import pytest


AGENTS_DIR = Path(__file__).resolve().parents[2] / "ink-writer" / "agents"
AGENTS_DIR_SECONDARY = Path(__file__).resolve().parents[2] / "agents" / "ink-writer"
REFERENCES_DIR = Path(__file__).resolve().parents[2] / "ink-writer" / "references"
DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"


class TestThreadLifecycleTrackerExists:
    def test_unified_tracker_spec_exists(self):
        assert (AGENTS_DIR / "thread-lifecycle-tracker.md").exists()

    def test_old_specs_retained_for_backward_compat(self):
        assert (AGENTS_DIR / "foreshadow-tracker.md").exists()
        assert (AGENTS_DIR / "plotline-tracker.md").exists()

    def test_unified_tracker_has_frontmatter(self):
        content = (AGENTS_DIR / "thread-lifecycle-tracker.md").read_text()
        assert "name: thread-lifecycle-tracker" in content
        assert "tools: Read" in content

    def test_unified_tracker_covers_both_thread_types(self):
        content = (AGENTS_DIR / "thread-lifecycle-tracker.md").read_text()
        assert "foreshadow" in content.lower()
        assert "plotline" in content.lower()
        assert "thread_type" in content

    def test_unified_tracker_has_state_machine(self):
        content = (AGENTS_DIR / "thread-lifecycle-tracker.md").read_text()
        assert "declared" in content or "planted" in content
        assert "active" in content
        assert "resolved" in content

    def test_unified_tracker_has_scoring(self):
        content = (AGENTS_DIR / "thread-lifecycle-tracker.md").read_text()
        assert "base_score = 100" in content
        assert "overall_score" in content

    def test_unified_tracker_has_forced_actions(self):
        content = (AGENTS_DIR / "thread-lifecycle-tracker.md").read_text()
        assert "forced_payoffs" in content
        assert "forced_advances" in content

    def test_unified_tracker_output_follows_checker_schema(self):
        content = (AGENTS_DIR / "thread-lifecycle-tracker.md").read_text()
        assert "checker-output-schema.md" in content
        for field in ["agent", "chapter", "overall_score", "pass", "issues", "metrics", "summary"]:
            assert f'"{field}"' in content


class TestSharedCheckerPreamble:
    def test_preamble_exists(self):
        assert (REFERENCES_DIR / "shared-checker-preamble.md").exists()

    def test_preamble_has_input_rules(self):
        content = (REFERENCES_DIR / "shared-checker-preamble.md").read_text()
        assert "review_bundle_file" in content
        assert "allowed_read_files" in content
        assert ".db" in content

    def test_preamble_has_output_rules(self):
        content = (REFERENCES_DIR / "shared-checker-preamble.md").read_text()
        assert "checker-output-schema.md" in content

    def test_preamble_has_scoring_rules(self):
        content = (REFERENCES_DIR / "shared-checker-preamble.md").read_text()
        assert "100" in content
        assert "critical" in content


class TestCheckerOutputSchemaCompleteness:
    def test_schema_has_all_checker_metrics(self):
        content = (REFERENCES_DIR / "checker-output-schema.md").read_text()
        expected_checkers = [
            "reader-pull-checker",
            "high-point-checker",
            "consistency-checker",
            "ooc-checker",
            "continuity-checker",
            "pacing-checker",
            "emotion-curve-checker",
            "anti-detection-checker",
            "proofreading-checker",
            "golden-three-checker",
            "thread-lifecycle-tracker",
            "editor-wisdom-checker",
        ]
        for checker in expected_checkers:
            assert checker in content, f"Missing metrics for {checker}"

    def test_summary_format_has_all_checkers(self):
        content = (REFERENCES_DIR / "checker-output-schema.md").read_text()
        assert "thread-lifecycle-tracker" in content
        assert "emotion-curve-checker" in content
        assert "anti-detection-checker" in content
        assert "editor-wisdom-checker" in content


class TestTopologyDocument:
    def test_topology_doc_exists(self):
        assert (DOCS_DIR / "agent_topology_v13.md").exists()

    def test_topology_has_before_after(self):
        content = (DOCS_DIR / "agent_topology_v13.md").read_text()
        assert "Before" in content
        assert "After" in content

    def test_topology_documents_merge(self):
        content = (DOCS_DIR / "agent_topology_v13.md").read_text()
        assert "thread-lifecycle-tracker" in content
        assert "MERGED" in content

    def test_topology_has_pipeline_diagram(self):
        content = (DOCS_DIR / "agent_topology_v13.md").read_text()
        assert "Pipeline" in content
        assert "Step 0" in content
        assert "Step 3" in content

    def test_topology_has_responsibility_matrix(self):
        content = (DOCS_DIR / "agent_topology_v13.md").read_text()
        assert "Responsibility Matrix" in content

    def test_topology_has_overlap_analysis(self):
        content = (DOCS_DIR / "agent_topology_v13.md").read_text()
        assert "Overlap Analysis" in content
        assert "Keep separate" in content


class TestAgentDirectoryIntegrity:
    def test_all_expected_agents_present(self):
        expected = [
            "writer-agent.md",
            "context-agent.md",
            "data-agent.md",
            "polish-agent.md",
            "consistency-checker.md",
            "continuity-checker.md",
            "ooc-checker.md",
            "anti-detection-checker.md",
            "proofreading-checker.md",
            "emotion-curve-checker.md",
            "high-point-checker.md",
            "pacing-checker.md",
            "reader-pull-checker.md",
            "reader-simulator.md",
            "golden-three-checker.md",
            "thread-lifecycle-tracker.md",
        ]
        for agent_file in expected:
            assert (AGENTS_DIR / agent_file).exists(), f"Missing agent: {agent_file}"

    def test_editor_wisdom_checker_in_secondary_dir(self):
        assert (AGENTS_DIR_SECONDARY / "editor-wisdom-checker.md").exists()

    def test_all_agent_specs_have_frontmatter(self):
        for md_file in AGENTS_DIR.glob("*.md"):
            content = md_file.read_text()
            assert content.startswith("---"), f"{md_file.name} missing frontmatter"
            assert "name:" in content.split("---")[1], f"{md_file.name} missing name in frontmatter"


class TestInkPlanReferences:
    def test_ink_plan_references_unified_tracker(self):
        skill_file = Path(__file__).resolve().parents[2] / "ink-writer" / "skills" / "ink-plan" / "SKILL.md"
        content = skill_file.read_text()
        assert "thread-lifecycle-tracker" in content
