"""v16 US-020：Skill/Agent frontmatter completeness 守卫单测。

规则（verify_docs.py 中实现）：
  1. ``ink-writer/skills/*/SKILL.md`` 必须含 name/description/allowed-tools；
  2. ``ink-writer/agents/*.md`` 必须含 name/description/tools；
  3. 若新增 agent 默认声明的 tools 包含 Bash/Write/Edit 等高权限工具且
     description 中无 "需要"/"因为"/"since"/"requires" 等理由关键字 → CI warn（ok=True）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from verify_docs import (
    AGENT_REQUIRED_FIELDS,
    SKILL_REQUIRED_FIELDS,
    check_agent_frontmatter,
    check_skill_frontmatter,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_skill(skills_dir: Path, name: str, frontmatter: str) -> Path:
    d = skills_dir / name
    d.mkdir(parents=True, exist_ok=True)
    path = d / "SKILL.md"
    path.write_text(f"---\n{frontmatter}\n---\n\nbody\n", encoding="utf-8")
    return path


def _write_agent(agents_dir: Path, name: str, frontmatter: str) -> Path:
    path = agents_dir / f"{name}.md"
    path.write_text(f"---\n{frontmatter}\n---\n\nbody\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Skill frontmatter tests
# ---------------------------------------------------------------------------


class TestSkillFrontmatter:
    def test_complete_frontmatter_passes(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        skills.mkdir()
        _write_skill(
            skills,
            "ink-plan",
            "name: ink-plan\n"
            "description: plan stuff\n"
            "allowed-tools: Read Bash AskUserQuestion",
        )

        findings = check_skill_frontmatter(skills)

        assert findings and all(f.ok for f in findings)

    def test_missing_allowed_tools_fails(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        skills.mkdir()
        _write_skill(
            skills,
            "ink-plan",
            "name: ink-plan\ndescription: plan stuff",
        )

        findings = check_skill_frontmatter(skills)

        assert findings
        failing = [f for f in findings if not f.ok]
        assert failing, "缺 allowed-tools 必须被标记"
        assert "allowed-tools" in failing[0].actual

    def test_missing_description_fails(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        skills.mkdir()
        _write_skill(
            skills,
            "ink-plan",
            "name: ink-plan\nallowed-tools: Read",
        )

        findings = check_skill_frontmatter(skills)

        failing = [f for f in findings if not f.ok]
        assert failing and "description" in failing[0].actual

    def test_empty_dir_is_noop(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills-empty"
        skills.mkdir()
        assert check_skill_frontmatter(skills) == []

    def test_required_fields_tuple(self) -> None:
        assert SKILL_REQUIRED_FIELDS == ("name", "description", "allowed-tools")


# ---------------------------------------------------------------------------
# Agent frontmatter tests
# ---------------------------------------------------------------------------


class TestAgentFrontmatter:
    def test_complete_frontmatter_passes(self, tmp_path: Path) -> None:
        agents = tmp_path / "agents"
        agents.mkdir()
        _write_agent(
            agents,
            "context-agent",
            "name: context-agent\n"
            "description: gather context\n"
            "tools: Read, Grep",
        )

        findings = check_agent_frontmatter(agents)

        assert findings and all(f.ok for f in findings)

    def test_missing_tools_fails(self, tmp_path: Path) -> None:
        agents = tmp_path / "agents"
        agents.mkdir()
        _write_agent(
            agents,
            "rogue",
            "name: rogue\ndescription: no tools declared",
        )

        findings = check_agent_frontmatter(agents)

        failing = [f for f in findings if not f.ok]
        assert failing and "tools" in failing[0].actual

    def test_high_privilege_tools_warns_not_fails(self, tmp_path: Path) -> None:
        """未声明理由的高权限工具 → warn，但 ok=True（CI 不 fail）。"""
        agents = tmp_path / "agents"
        agents.mkdir()
        _write_agent(
            agents,
            "risky",
            "name: risky\n"
            "description: does stuff\n"
            "tools: Read, Bash, Write",
        )

        findings = check_agent_frontmatter(agents)

        assert findings
        # 所有 finding 都 ok=True（warn-only 不 fail CI）
        assert all(f.ok for f in findings)
        # 但文本里必须提到高权限工具
        assert any("high-priv" in f.claim for f in findings)

    def test_high_privilege_with_justification_no_warn(self, tmp_path: Path) -> None:
        agents = tmp_path / "agents"
        agents.mkdir()
        _write_agent(
            agents,
            "justified",
            "name: justified\n"
            "description: 需要写入文件以修复审查问题\n"
            "tools: Read, Write, Edit",
        )

        findings = check_agent_frontmatter(agents)

        assert findings and all(f.ok for f in findings)
        assert all("high-priv" not in f.claim for f in findings)

    def test_empty_dir_is_noop(self, tmp_path: Path) -> None:
        agents = tmp_path / "agents-empty"
        agents.mkdir()
        assert check_agent_frontmatter(agents) == []

    def test_required_fields_tuple(self) -> None:
        assert AGENT_REQUIRED_FIELDS == ("name", "description", "tools")


# ---------------------------------------------------------------------------
# Live repo sanity: 本仓库所有 SKILL.md / agent .md 全量通过规则
# （US-020 AC 要求 ink-plan 补齐 allowed-tools 后零回归）
# ---------------------------------------------------------------------------


def test_real_repo_skills_all_pass() -> None:
    findings = check_skill_frontmatter()
    failing = [f for f in findings if not f.ok]
    assert not failing, f"SKILL.md 有缺字段: {[f.render() for f in failing]}"


def test_real_repo_agents_all_pass() -> None:
    findings = check_agent_frontmatter()
    failing = [f for f in findings if not f.ok]
    assert not failing, f"agent .md 有缺字段: {[f.render() for f in failing]}"
