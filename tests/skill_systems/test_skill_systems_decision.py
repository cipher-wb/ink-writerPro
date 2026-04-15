"""Tests for US-403: ink-writer vs webnovel-writer skill system decision."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INK_SKILLS_DIR = PROJECT_ROOT / "ink-writer" / "skills"
INK_AGENTS_DIR = PROJECT_ROOT / "ink-writer" / "agents"
DECISION_DOC = PROJECT_ROOT / "docs" / "skill_systems_decision.md"
MIGRATE_SCRIPT = PROJECT_ROOT / "ink-writer" / "scripts" / "migrate_webnovel_to_ink.sh"


class TestDecisionDocumentExists:
    def test_decision_doc_exists(self):
        assert DECISION_DOC.exists(), "docs/skill_systems_decision.md must exist"

    def test_decision_doc_has_decision(self):
        text = DECISION_DOC.read_text(encoding="utf-8")
        assert "决策" in text
        assert "合并" in text or "保留" in text

    def test_decision_doc_has_rationale(self):
        text = DECISION_DOC.read_text(encoding="utf-8")
        assert "理由" in text or "原因" in text

    def test_decision_doc_has_migration_plan(self):
        text = DECISION_DOC.read_text(encoding="utf-8")
        assert "迁移" in text

    def test_decision_doc_has_timeline(self):
        text = DECISION_DOC.read_text(encoding="utf-8")
        assert "Phase A" in text or "阶段" in text


class TestMigrationScriptExists:
    def test_migrate_script_exists(self):
        assert MIGRATE_SCRIPT.exists(), "migrate_webnovel_to_ink.sh must exist"

    def test_migrate_script_is_executable_content(self):
        text = MIGRATE_SCRIPT.read_text(encoding="utf-8")
        assert text.startswith("#!/bin/bash")
        assert ".webnovel" in text
        assert ".ink" in text


class TestInkWriterSkillCompleteness:
    """Verify ink-writer has all skills that webnovel-writer provides."""

    WEBNOVEL_SKILL_CONCEPTS = [
        "init",
        "plan",
        "write",
        "review",
        "query",
        "resume",
        "learn",
        "dashboard",
    ]

    def test_ink_skills_directory_exists(self):
        assert INK_SKILLS_DIR.exists()

    @pytest.mark.parametrize("concept", WEBNOVEL_SKILL_CONCEPTS)
    def test_ink_has_equivalent_skill(self, concept: str):
        skill_files = list(INK_SKILLS_DIR.glob(f"ink-{concept}*"))
        assert len(skill_files) >= 1, (
            f"ink-writer must have a skill covering '{concept}' "
            f"(expected ink-{concept}* in {INK_SKILLS_DIR})"
        )

    def test_ink_has_more_skills_than_webnovel(self):
        ink_skills = list(INK_SKILLS_DIR.glob("ink-*"))
        assert len(ink_skills) >= 14, (
            f"ink-writer should have >=14 skills (found {len(ink_skills)})"
        )


class TestInkWriterAgentCompleteness:
    """Verify ink-writer agents are a superset of webnovel-writer agents."""

    WEBNOVEL_AGENT_NAMES = [
        "context-agent",
        "data-agent",
        "consistency-checker",
        "continuity-checker",
        "ooc-checker",
        "reader-pull-checker",
        "high-point-checker",
        "pacing-checker",
    ]

    def test_agents_directory_exists(self):
        assert INK_AGENTS_DIR.exists()

    @pytest.mark.parametrize("agent", WEBNOVEL_AGENT_NAMES)
    def test_ink_has_agent(self, agent: str):
        agent_file = INK_AGENTS_DIR / f"{agent}.md"
        assert agent_file.exists(), (
            f"ink-writer must have agent '{agent}' at {agent_file}"
        )

    def test_ink_has_more_agents(self):
        agent_files = list(INK_AGENTS_DIR.glob("*.md"))
        assert len(agent_files) >= 19, (
            f"ink-writer should have >=19 agents (found {len(agent_files)})"
        )


class TestDecisionDocStructure:
    """Validate decision doc covers all required sections."""

    def test_has_comparison_table(self):
        text = DECISION_DOC.read_text(encoding="utf-8")
        assert "重叠度" in text or "Overlap" in text or "对比" in text

    def test_has_risk_section(self):
        text = DECISION_DOC.read_text(encoding="utf-8")
        assert "风险" in text or "Risk" in text

    def test_mentions_both_systems(self):
        text = DECISION_DOC.read_text(encoding="utf-8")
        assert "ink-writer" in text
        assert "webnovel-writer" in text

    def test_deprecation_timeline(self):
        text = DECISION_DOC.read_text(encoding="utf-8")
        assert "废弃" in text or "deprecat" in text.lower()
