#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for sync_plugin_version.py — version synchronization across plugin files.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

import sync_plugin_version as spv


# ---------------------------------------------------------------------------
# Helpers — build a realistic temp file tree
# ---------------------------------------------------------------------------

README_TEMPLATE = textwrap.dedent("""\
    # ink-writer

    Some intro text.

    | 版本 | 说明 |
    |------|------|
    | **v1.0.0 (当前)** | Initial release |
    | **v0.9.0** | Beta release |

    Footer text.
""")


def _make_plugin_json(path: Path, version: str = "1.0.0") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"name": "ink-writer", "version": version}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _make_marketplace_json(path: Path, version: str = "1.0.0") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "plugins": [
            {"name": "ink-writer", "version": version, "description": "test"},
            {"name": "other-plugin", "version": "0.1.0"},
        ]
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _make_gemini_json(path: Path, version: str = "1.0.0") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": version}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _make_init_py(path: Path, version: str = "1.0.0") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'__version__ = "{version}"\n', encoding="utf-8")


def _make_readme(path: Path, content: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or README_TEMPLATE, encoding="utf-8")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Set up a complete fake file tree and monkeypatch module-level paths."""
    plugin_json = tmp_path / "ink-writer" / ".claude-plugin" / "plugin.json"
    marketplace_json = tmp_path / ".claude-plugin" / "marketplace.json"
    gemini_json = tmp_path / "gemini-extension.json"
    scripts_init = tmp_path / "ink-writer" / "scripts" / "__init__.py"
    readme = tmp_path / "README.md"

    _make_plugin_json(plugin_json)
    _make_marketplace_json(marketplace_json)
    _make_gemini_json(gemini_json)
    _make_init_py(scripts_init)
    _make_readme(readme)

    monkeypatch.setattr(spv, "ROOT", tmp_path)
    monkeypatch.setattr(spv, "PLUGIN_JSON_PATH", plugin_json)
    monkeypatch.setattr(spv, "MARKETPLACE_JSON_PATH", marketplace_json)
    monkeypatch.setattr(spv, "GEMINI_EXTENSION_PATH", gemini_json)
    monkeypatch.setattr(spv, "SCRIPTS_INIT_PATH", scripts_init)
    monkeypatch.setattr(spv, "README_PATH", readme)

    return {
        "root": tmp_path,
        "plugin_json": plugin_json,
        "marketplace_json": marketplace_json,
        "gemini_json": gemini_json,
        "scripts_init": scripts_init,
        "readme": readme,
    }


# ---------------------------------------------------------------------------
# load_json / save_json
# ---------------------------------------------------------------------------


class TestLoadSaveJson:
    def test_load_json(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text('{"key": "value"}', encoding="utf-8")
        assert spv.load_json(p) == {"key": "value"}

    def test_save_json_creates_valid_file(self, tmp_path):
        p = tmp_path / "out.json"
        spv.save_json(p, {"hello": "世界"})
        raw = p.read_text(encoding="utf-8")
        assert raw.endswith("\n")
        assert json.loads(raw) == {"hello": "世界"}
        # ensure_ascii=False means the Chinese character is preserved literally
        assert "世界" in raw

    def test_roundtrip(self, tmp_path):
        p = tmp_path / "rt.json"
        data = {"a": 1, "b": [2, 3]}
        spv.save_json(p, data)
        assert spv.load_json(p) == data


# ---------------------------------------------------------------------------
# load_text / save_text
# ---------------------------------------------------------------------------


class TestLoadSaveText:
    def test_roundtrip(self, tmp_path):
        p = tmp_path / "text.txt"
        spv.save_text(p, "hello\nworld\n")
        assert spv.load_text(p) == "hello\nworld\n"

    def test_unicode(self, tmp_path):
        p = tmp_path / "uni.txt"
        content = "中文内容\n"
        spv.save_text(p, content)
        assert spv.load_text(p) == content


# ---------------------------------------------------------------------------
# get_marketplace_plugin
# ---------------------------------------------------------------------------


class TestGetMarketplacePlugin:
    def test_found(self):
        payload = {"plugins": [{"name": "ink-writer", "version": "1.0.0"}]}
        result = spv.get_marketplace_plugin(payload)
        assert result["version"] == "1.0.0"

    def test_not_found_raises(self):
        payload = {"plugins": [{"name": "other", "version": "1.0.0"}]}
        with pytest.raises(ValueError, match="not found"):
            spv.get_marketplace_plugin(payload)

    def test_empty_plugins(self):
        with pytest.raises(ValueError):
            spv.get_marketplace_plugin({"plugins": []})

    def test_missing_plugins_key(self):
        with pytest.raises(ValueError):
            spv.get_marketplace_plugin({})


# ---------------------------------------------------------------------------
# parse_readme_rows
# ---------------------------------------------------------------------------


class TestParseReadmeRows:
    def test_parses_current_and_non_current(self):
        lines = [
            "| 版本 | 说明 |",
            "|------|------|",
            "| **v2.0.0 (当前)** | New release |",
            "| **v1.0.0** | Old release |",
        ]
        rows = spv.parse_readme_rows(lines)
        assert len(rows) == 2
        assert rows[0]["version"] == "2.0.0"
        assert rows[0]["is_current"] is True
        assert rows[0]["notes"] == "New release"
        assert rows[1]["version"] == "1.0.0"
        assert rows[1]["is_current"] is False

    def test_no_matching_rows(self):
        lines = ["just some text", "no table here"]
        assert spv.parse_readme_rows(lines) == []

    def test_index_is_correct(self):
        lines = ["preamble", "| **v3.0.0 (当前)** | notes |", "postamble"]
        rows = spv.parse_readme_rows(lines)
        assert rows[0]["index"] == 1


# ---------------------------------------------------------------------------
# format_readme_row
# ---------------------------------------------------------------------------


class TestFormatReadmeRow:
    def test_current(self):
        result = spv.format_readme_row("2.0.0", "Big update", True)
        assert result == "| **v2.0.0 (当前)** | Big update |"

    def test_not_current(self):
        result = spv.format_readme_row("1.0.0", "Old", False)
        assert result == "| **v1.0.0** | Old |"


# ---------------------------------------------------------------------------
# get_readme_current_version
# ---------------------------------------------------------------------------


class TestGetReadmeCurrentVersion:
    def test_returns_current(self):
        assert spv.get_readme_current_version(README_TEMPLATE) == "1.0.0"

    def test_no_current_raises(self):
        content = "| **v1.0.0** | No current marker |\n"
        with pytest.raises(ValueError, match="exactly one"):
            spv.get_readme_current_version(content)

    def test_multiple_current_raises(self):
        content = (
            "| **v2.0.0 (当前)** | A |\n"
            "| **v1.0.0 (当前)** | B |\n"
        )
        with pytest.raises(ValueError, match="exactly one"):
            spv.get_readme_current_version(content)


# ---------------------------------------------------------------------------
# update_readme_release
# ---------------------------------------------------------------------------


class TestUpdateReadmeRelease:
    def test_updates_existing_version(self):
        result = spv.update_readme_release(README_TEMPLATE, "0.9.0", "Promoted beta")
        lines = result.splitlines()
        # 0.9.0 should now be current
        rows = spv.parse_readme_rows(lines)
        current = [r for r in rows if r["is_current"]]
        assert len(current) == 1
        assert current[0]["version"] == "0.9.0"
        # 1.0.0 should no longer be current
        non_current = [r for r in rows if not r["is_current"]]
        assert any(r["version"] == "1.0.0" for r in non_current)

    def test_inserts_new_version(self):
        result = spv.update_readme_release(README_TEMPLATE, "2.0.0", "Brand new version")
        rows = spv.parse_readme_rows(result.splitlines())
        versions = [r["version"] for r in rows]
        assert "2.0.0" in versions
        current = [r for r in rows if r["is_current"]]
        assert current[0]["version"] == "2.0.0"

    def test_new_version_requires_release_notes(self):
        with pytest.raises(ValueError, match="Release notes are required"):
            spv.update_readme_release(README_TEMPLATE, "9.9.9", None)

    def test_missing_header_raises(self):
        with pytest.raises(ValueError, match="header not found"):
            spv.update_readme_release("No table here\n", "1.0.0", "notes")

    def test_missing_separator_raises(self):
        bad = "| 版本 | 说明 |\nNot a separator\n"
        with pytest.raises(ValueError, match="separator not found"):
            spv.update_readme_release(bad, "1.0.0", "notes")

    def test_existing_version_keeps_notes_when_none(self):
        result = spv.update_readme_release(README_TEMPLATE, "1.0.0", None)
        rows = spv.parse_readme_rows(result.splitlines())
        row = next(r for r in rows if r["version"] == "1.0.0")
        assert row["notes"] == "Initial release"
        assert row["is_current"] is True


# ---------------------------------------------------------------------------
# sync_versions
# ---------------------------------------------------------------------------


class TestSyncVersions:
    def test_sync_to_new_version(self, env):
        prev, target, changed = spv.sync_versions(version="2.0.0", release_notes="Major update")
        assert prev == "1.0.0"
        assert target == "2.0.0"
        assert changed is True

        # Verify all files updated
        assert spv.load_json(env["plugin_json"])["version"] == "2.0.0"
        mp = spv.load_json(env["marketplace_json"])
        assert spv.get_marketplace_plugin(mp)["version"] == "2.0.0"
        assert spv.load_json(env["gemini_json"])["version"] == "2.0.0"
        init_text = spv.load_text(env["scripts_init"])
        assert '__version__ = "2.0.0"' in init_text
        readme_text = spv.load_text(env["readme"])
        assert spv.get_readme_current_version(readme_text) == "2.0.0"

    def test_sync_no_change(self, env):
        prev, target, changed = spv.sync_versions(version="1.0.0")
        assert prev == "1.0.0"
        assert target == "1.0.0"
        assert changed is False

    def test_sync_without_version_uses_plugin_version(self, env):
        prev, target, changed = spv.sync_versions()
        assert target == "1.0.0"
        assert changed is False

    def test_sync_without_gemini(self, env, monkeypatch):
        # Remove gemini file
        env["gemini_json"].unlink()
        monkeypatch.setattr(spv, "GEMINI_EXTENSION_PATH", env["root"] / "nonexistent.json")
        prev, target, changed = spv.sync_versions(version="2.0.0", release_notes="Update")
        assert changed is True
        assert target == "2.0.0"
        # gemini file should not be created
        assert not (env["root"] / "nonexistent.json").exists()

    def test_sync_updates_init_py(self, env):
        _make_init_py(env["scripts_init"], "0.5.0")
        spv.sync_versions(version="1.0.0")
        init_text = spv.load_text(env["scripts_init"])
        assert '__version__ = "1.0.0"' in init_text

    def test_sync_with_mismatched_files(self, env):
        # Create a scenario where files have different versions
        _make_plugin_json(env["plugin_json"], "1.0.0")
        _make_marketplace_json(env["marketplace_json"], "0.9.0")
        _make_gemini_json(env["gemini_json"], "0.8.0")
        _make_init_py(env["scripts_init"], "0.7.0")

        prev, target, changed = spv.sync_versions(version="2.0.0", release_notes="Align all")
        assert changed is True
        assert target == "2.0.0"
        assert spv.load_json(env["plugin_json"])["version"] == "2.0.0"


# ---------------------------------------------------------------------------
# check_versions
# ---------------------------------------------------------------------------


class TestCheckVersions:
    def test_all_in_sync(self, env, capsys):
        result = spv.check_versions()
        assert result == 0
        captured = capsys.readouterr()
        assert "in sync" in captured.out.lower() or "Versions are in sync" in captured.out

    def test_mismatch_plugin_marketplace(self, env, capsys):
        _make_marketplace_json(env["marketplace_json"], "0.9.0")
        result = spv.check_versions()
        assert result == 1
        captured = capsys.readouterr()
        assert "mismatch" in captured.out.lower()

    def test_mismatch_plugin_gemini(self, env, capsys):
        _make_gemini_json(env["gemini_json"], "0.5.0")
        result = spv.check_versions()
        assert result == 1

    def test_mismatch_plugin_readme(self, env, capsys):
        _make_readme(env["readme"], textwrap.dedent("""\
            | 版本 | 说明 |
            |------|------|
            | **v0.1.0 (当前)** | Old |
        """))
        result = spv.check_versions()
        assert result == 1

    def test_mismatch_plugin_init(self, env, capsys):
        _make_init_py(env["scripts_init"], "0.0.1")
        result = spv.check_versions()
        assert result == 1

    def test_expected_version_match(self, env, capsys):
        result = spv.check_versions(expected_version="1.0.0")
        assert result == 0

    def test_expected_version_mismatch(self, env, capsys):
        result = spv.check_versions(expected_version="9.9.9")
        assert result == 1
        captured = capsys.readouterr()
        assert "expected=9.9.9" in captured.out

    def test_without_gemini_file(self, env, monkeypatch, capsys):
        env["gemini_json"].unlink()
        monkeypatch.setattr(spv, "GEMINI_EXTENSION_PATH", env["root"] / "gone.json")
        result = spv.check_versions()
        assert result == 0

    def test_without_init_file(self, env, monkeypatch, capsys):
        env["scripts_init"].unlink()
        monkeypatch.setattr(spv, "SCRIPTS_INIT_PATH", env["root"] / "gone.py")
        result = spv.check_versions()
        assert result == 0


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------


class TestMain:
    def test_check_flag(self, env, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["prog", "--check"])
        result = spv.main()
        assert result == 0

    def test_check_with_expected_version_ok(self, env, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["prog", "--check", "--expected-version", "1.0.0"])
        result = spv.main()
        assert result == 0

    def test_sync_with_version(self, env, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["prog", "--version", "3.0.0", "--release-notes", "Big change"])
        result = spv.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "3.0.0" in captured.out

    def test_sync_no_change(self, env, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["prog", "--version", "1.0.0"])
        result = spv.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "No changes needed" in captured.out

    def test_invalid_version_format(self, env, monkeypatch):
        monkeypatch.setattr("sys.argv", ["prog", "--version", "bad"])
        with pytest.raises(SystemExit):
            spv.main()

    def test_invalid_expected_version_format(self, env, monkeypatch):
        monkeypatch.setattr("sys.argv", ["prog", "--check", "--expected-version", "nope"])
        with pytest.raises(SystemExit):
            spv.main()

    def test_expected_version_without_check(self, env, monkeypatch):
        monkeypatch.setattr("sys.argv", ["prog", "--expected-version", "1.0.0"])
        with pytest.raises(SystemExit):
            spv.main()

    def test_value_error_returns_1(self, env, monkeypatch, capsys):
        # Break the readme so sync_versions raises ValueError
        _make_readme(env["readme"], "No table at all\n")
        monkeypatch.setattr("sys.argv", ["prog", "--version", "2.0.0", "--release-notes", "X"])
        result = spv.main()
        assert result == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.out

    def test_default_no_args_runs_sync(self, env, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["prog"])
        result = spv.main()
        assert result == 0


# ---------------------------------------------------------------------------
# VERSION_PATTERN
# ---------------------------------------------------------------------------


class TestVersionPattern:
    @pytest.mark.parametrize("v", ["1.0.0", "0.0.1", "10.20.30"])
    def test_valid(self, v):
        assert spv.VERSION_PATTERN.fullmatch(v)

    @pytest.mark.parametrize("v", ["1.0", "v1.0.0", "1.0.0-beta", "abc", ""])
    def test_invalid(self, v):
        assert not spv.VERSION_PATTERN.fullmatch(v)


# ---------------------------------------------------------------------------
# _get_schema_versions (best-effort, never crashes)
# ---------------------------------------------------------------------------


class TestGetSchemaVersions:
    def test_returns_dict(self, env):
        # With monkeypatched ROOT pointing to tmp, files won't exist — should still return dict
        result = spv._get_schema_versions()
        assert isinstance(result, dict)
