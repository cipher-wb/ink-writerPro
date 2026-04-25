"""Tests for prompt template system (US-404)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "ink-writer" / "templates" / "prompts"
AGENTS_DIR = PROJECT_ROOT / "ink-writer" / "agents"
MANIFEST_PATH = TEMPLATES_DIR / "_manifest.json"

# [FIX-11] removed: sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

TEMPLATE_REF_PATTERN = re.compile(r"\{\{PROMPT_TEMPLATE:([^}]+)\}\}")
VERSION_PATTERN = re.compile(r"version:\s*([\d]+\.[\d]+\.[\d]+)")
TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+")


# ── Manifest Tests ──────────────────────────────────────────────────────────


class TestManifest:
    @pytest.fixture(scope="class")
    def manifest(self) -> dict:
        assert MANIFEST_PATH.exists(), f"Manifest not found: {MANIFEST_PATH}"
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_has_schema_version(self, manifest: dict) -> None:
        assert "schema_version" in manifest

    def test_manifest_has_templates(self, manifest: dict) -> None:
        assert "templates" in manifest
        assert len(manifest["templates"]) >= 1

    def test_each_template_has_required_fields(self, manifest: dict) -> None:
        for name, info in manifest["templates"].items():
            assert "file" in info, f"Template {name} missing 'file'"
            assert "version" in info, f"Template {name} missing 'version'"
            assert "consumers" in info, f"Template {name} missing 'consumers'"
            assert "changelog" in info, f"Template {name} missing 'changelog'"

    def test_each_template_file_exists(self, manifest: dict) -> None:
        for name, info in manifest["templates"].items():
            path = TEMPLATES_DIR / info["file"]
            assert path.exists(), f"Template file missing: {path}"

    def test_version_is_semver(self, manifest: dict) -> None:
        semver = re.compile(r"^\d+\.\d+\.\d+$")
        for name, info in manifest["templates"].items():
            assert semver.match(
                info["version"]
            ), f"Template {name} version {info['version']} is not semver"

    def test_consumers_reference_existing_agents(self, manifest: dict) -> None:
        agent_names = {p.stem for p in AGENTS_DIR.glob("*.md")}
        for name, info in manifest["templates"].items():
            for consumer in info["consumers"]:
                assert (
                    consumer in agent_names
                ), f"Template {name} consumer '{consumer}' has no agent spec"


# ── Template File Tests ─────────────────────────────────────────────────────


class TestTemplateFiles:
    @pytest.fixture(scope="class")
    def template_files(self) -> list[Path]:
        return sorted(TEMPLATES_DIR.glob("*.md"))

    def test_templates_dir_exists(self) -> None:
        assert TEMPLATES_DIR.is_dir()

    def test_at_least_5_templates(self, template_files: list[Path]) -> None:
        assert len(template_files) >= 5, f"Only {len(template_files)} templates"

    def test_each_template_has_version_header(
        self, template_files: list[Path]
    ) -> None:
        for tpl in template_files:
            content = tpl.read_text(encoding="utf-8")
            assert VERSION_PATTERN.search(
                content
            ), f"Template {tpl.name} missing version header"

    def test_each_template_has_changelog(self, template_files: list[Path]) -> None:
        for tpl in template_files:
            content = tpl.read_text(encoding="utf-8")
            assert (
                "changelog" in content.lower()
            ), f"Template {tpl.name} missing changelog"

    def test_template_not_empty(self, template_files: list[Path]) -> None:
        for tpl in template_files:
            content = tpl.read_text(encoding="utf-8").strip()
            tokens = TOKEN_PATTERN.findall(content)
            assert len(tokens) >= 5, f"Template {tpl.name} too short ({len(tokens)} tokens)"


# ── Agent Spec Tests ────────────────────────────────────────────────────────


class TestAgentTemplateReferences:
    @pytest.fixture(scope="class")
    def agent_specs(self) -> list[tuple[str, str]]:
        return [
            (p.stem, p.read_text(encoding="utf-8"))
            for p in sorted(AGENTS_DIR.glob("*.md"))
        ]

    def test_all_template_refs_resolve(
        self, agent_specs: list[tuple[str, str]]
    ) -> None:
        for name, content in agent_specs:
            refs = TEMPLATE_REF_PATTERN.findall(content)
            for ref in refs:
                path = TEMPLATES_DIR / ref.strip()
                assert path.exists(), f"Agent {name} references missing template: {ref}"

    def test_at_least_15_agents_have_refs(
        self, agent_specs: list[tuple[str, str]]
    ) -> None:
        agents_with_refs = sum(
            1 for _, c in agent_specs if TEMPLATE_REF_PATTERN.search(c)
        )
        assert agents_with_refs >= 15, f"Only {agents_with_refs}/19 agents use templates"

    def test_total_refs_at_least_25(
        self, agent_specs: list[tuple[str, str]]
    ) -> None:
        total = sum(
            len(TEMPLATE_REF_PATTERN.findall(c)) for _, c in agent_specs
        )
        assert total >= 25, f"Only {total} total refs (expected ≥25)"

    def test_no_legacy_shared_preamble_ref(
        self, agent_specs: list[tuple[str, str]]
    ) -> None:
        for name, content in agent_specs:
            assert (
                "{{SHARED_CHECKER_PREAMBLE}}" not in content
            ), f"Agent {name} still uses legacy {{{{SHARED_CHECKER_PREAMBLE}}}}"


# ── A/B Harness Tests ───────────────────────────────────────────────────────


class TestABPrompts:
    def test_script_exists(self) -> None:
        assert (PROJECT_ROOT / "scripts" / "ab_prompts.py").exists()

    def test_list_runs(self) -> None:
        import ab_prompts

        templates = ab_prompts.list_templates()
        assert len(templates) >= 5
        for t in templates:
            assert "name" in t
            assert "version" in t
            assert "token_count" in t
            assert t["token_count"] > 0

    def test_diff_all_runs(self) -> None:
        import ab_prompts

        results = ab_prompts.diff_all_agents()
        # v13 US-016：foreshadow-tracker + plotline-tracker 合并删除（24→22）
        # v22 US-005：新增 directness-checker（22→23）
        # M3 (2026-04-25)：新增 writer-self-check / conflict-skeleton-checker /
        # protagonist-agency-checker (23→26)
        assert len(results) == 26
        for r in results:
            assert "agent" in r
            assert "template_refs" in r
            assert "resolved_tokens" in r

    def test_resolve_agent_expands_templates(self) -> None:
        import ab_prompts

        agent_path = AGENTS_DIR / "consistency-checker.md"
        original = agent_path.read_text(encoding="utf-8")
        resolved = ab_prompts.resolve_agent(agent_path)
        assert len(resolved) > len(original)
        assert "{{PROMPT_TEMPLATE:" not in resolved

    def test_diff_template_identical(self) -> None:
        import ab_prompts

        tpl = (TEMPLATES_DIR / "checker-input-rules.md").read_text(encoding="utf-8")
        result = ab_prompts.diff_template(tpl, tpl)
        assert result["identical"] is True
        assert result["token_delta"] == 0

    def test_diff_template_different(self) -> None:
        import ab_prompts

        text_a = "Hello world"
        text_b = "Hello world, this is version B with more tokens"
        result = ab_prompts.diff_template(text_a, text_b)
        assert result["identical"] is False
        assert result["tokens_b"] > result["tokens_a"]


# ── Duplicate Elimination Tests ─────────────────────────────────────────────


class TestDuplicateElimination:
    @pytest.fixture(scope="class")
    def resolved_agents(self) -> dict[str, str]:
        import ab_prompts

        return {
            p.stem: ab_prompts.resolve_agent(p)
            for p in sorted(AGENTS_DIR.glob("*.md"))
        }

    def test_checker_input_rules_not_inline_in_checkers(self) -> None:
        # v13 US-016：foreshadow-tracker / plotline-tracker 已被 thread-lifecycle-tracker 合并替代并物理删除
        checker_names = [
            "consistency-checker", "continuity-checker", "ooc-checker",
            "high-point-checker", "pacing-checker", "emotion-curve-checker",
            "reader-simulator",
            "thread-lifecycle-tracker", "golden-three-checker",
            "editor-wisdom-checker", "reader-pull-checker",
        ]
        for name in checker_names:
            path = AGENTS_DIR / f"{name}.md"
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            assert "仅当审查包明确缺字段时" not in content or "PROMPT_TEMPLATE" in content, (
                f"{name} still has inline checker input rules"
            )

    def test_iron_laws_table_not_duplicated_in_writer(self) -> None:
        path = AGENTS_DIR / "writer-agent.md"
        content = path.read_text(encoding="utf-8")
        table_marker = "| **大纲即法律** |"
        count = content.count(table_marker)
        assert count == 0, f"writer-agent still has {count} inline iron-laws table rows"

    def test_responsibility_boundary_not_duplicated(self) -> None:
        for name in ["writer-agent", "polish-agent"]:
            path = AGENTS_DIR / f"{name}.md"
            content = path.read_text(encoding="utf-8")
            assert "Step 2A" not in content or "PROMPT_TEMPLATE" in content, (
                f"{name} still has inline responsibility boundary"
            )
