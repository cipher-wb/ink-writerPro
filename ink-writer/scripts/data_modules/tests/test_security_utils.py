#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for security_utils.py — sanitization, atomic writes, git helpers."""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import security_utils


def _load_module():
    """Import security_utils."""
    return security_utils


@pytest.fixture
def mod():
    return _load_module()


# ===========================================================================
# sanitize_filename
# ===========================================================================

class TestSanitizeFilename:
    def test_path_traversal_unix(self, mod):
        assert mod.sanitize_filename("../../../etc/passwd") == "passwd"

    def test_path_traversal_windows(self, mod):
        # On Unix, os.path.basename doesn't split on backslash;
        # the function replaces \ with _ instead.
        result = mod.sanitize_filename("C:\\Windows\\System32")
        assert "Windows" not in result or "_" in result
        assert "/" not in result and "\\" not in result

    def test_complex_traversal(self, mod):
        assert mod.sanitize_filename("/tmp/../../../../../etc/hosts") == "hosts"

    def test_chinese_name(self, mod):
        assert mod.sanitize_filename("正常角色名") == "正常角色名"

    def test_special_chars_stripped(self, mod):
        result = mod.sanitize_filename("hello$world@name!")
        assert "$" not in result
        assert "@" not in result
        assert "!" not in result

    def test_max_length(self, mod):
        long_name = "a" * 200
        result = mod.sanitize_filename(long_name, max_length=50)
        assert len(result) <= 50

    def test_empty_input(self, mod):
        assert mod.sanitize_filename("") == "unnamed_entity"

    def test_only_special_chars(self, mod):
        assert mod.sanitize_filename("$$$!!!") == "unnamed_entity"

    def test_consecutive_underscores(self, mod):
        result = mod.sanitize_filename("a///b///c")
        assert "__" not in result

    def test_leading_trailing_underscores(self, mod):
        result = mod.sanitize_filename("_test_")
        assert not result.startswith("_")
        assert not result.endswith("_")

    def test_mixed_slashes(self, mod):
        result = mod.sanitize_filename("path/to\\file.txt")
        assert "/" not in result
        assert "\\" not in result


# ===========================================================================
# sanitize_commit_message
# ===========================================================================

class TestSanitizeCommitMessage:
    def test_newline_removed(self, mod):
        result = mod.sanitize_commit_message("line1\nline2\rline3")
        assert "\n" not in result
        assert "\r" not in result

    def test_git_flag_removed(self, mod):
        result = mod.sanitize_commit_message("Test --author='Attacker'")
        assert "--author" not in result

    def test_amend_flag(self, mod):
        result = mod.sanitize_commit_message("--amend Chapter 1")
        assert result == "Chapter 1"

    def test_quotes_removed(self, mod):
        result = mod.sanitize_commit_message("Test'message\"here")
        assert "'" not in result
        assert '"' not in result

    def test_leading_dash_stripped(self, mod):
        result = mod.sanitize_commit_message("-m Test")
        assert result.startswith("m")

    def test_max_length(self, mod):
        long_msg = "a" * 300
        result = mod.sanitize_commit_message(long_msg, max_length=100)
        assert len(result) <= 100

    def test_empty_after_sanitize(self, mod):
        result = mod.sanitize_commit_message("--amend --force")
        assert result == "Untitled commit"

    def test_consecutive_spaces(self, mod):
        result = mod.sanitize_commit_message("hello   world")
        assert "  " not in result


# ===========================================================================
# validate_integer_input
# ===========================================================================

class TestValidateIntegerInput:
    def test_valid_int(self, mod):
        assert mod.validate_integer_input("123", "chapter") == 123

    def test_negative_int(self, mod):
        assert mod.validate_integer_input("-5", "offset") == -5

    def test_zero(self, mod):
        assert mod.validate_integer_input("0", "count") == 0

    def test_invalid_string(self, mod):
        with pytest.raises(ValueError):
            mod.validate_integer_input("abc", "chapter")

    def test_float_string(self, mod):
        with pytest.raises(ValueError):
            mod.validate_integer_input("3.14", "level")

    def test_empty_string(self, mod):
        with pytest.raises(ValueError):
            mod.validate_integer_input("", "field")


# ===========================================================================
# create_secure_directory / create_secure_file
# ===========================================================================

class TestSecureFileOps:
    def test_create_secure_directory(self, mod, tmp_path):
        target = tmp_path / "secure_dir"
        result = mod.create_secure_directory(str(target))
        assert target.exists()
        assert target.is_dir()
        assert isinstance(result, Path)
        if os.name != "nt":
            mode = oct(target.stat().st_mode & 0o777)
            assert mode == "0o700"

    def test_create_secure_directory_idempotent(self, mod, tmp_path):
        target = tmp_path / "secure_dir"
        mod.create_secure_directory(str(target))
        mod.create_secure_directory(str(target))
        assert target.exists()

    def test_create_secure_file(self, mod, tmp_path):
        target = tmp_path / "secret.txt"
        mod.create_secure_file(str(target), "sensitive data")
        assert target.read_text(encoding="utf-8") == "sensitive data"
        if os.name != "nt":
            mode = oct(target.stat().st_mode & 0o777)
            assert mode == "0o600"


# ===========================================================================
# Git helpers
# ===========================================================================

class TestGitHelpers:
    def test_is_git_available_cached(self, mod):
        # Reset cache
        mod._git_available = None
        result = mod.is_git_available()
        assert isinstance(result, bool)
        # Second call uses cache
        cached = mod.is_git_available()
        assert cached == result

    def test_is_git_available_when_missing(self, mod):
        mod._git_available = None
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = mod.is_git_available()
            assert result is False
        mod._git_available = None  # Reset

    def test_is_git_repo_true(self, mod, tmp_path):
        mod._git_available = True
        (tmp_path / ".git").mkdir()
        assert mod.is_git_repo(tmp_path) is True
        mod._git_available = None

    def test_is_git_repo_false(self, mod, tmp_path):
        mod._git_available = True
        assert mod.is_git_repo(tmp_path) is False
        mod._git_available = None

    def test_is_git_repo_git_unavailable(self, mod, tmp_path):
        mod._git_available = False
        assert mod.is_git_repo(tmp_path) is False
        mod._git_available = None

    def test_git_graceful_when_unavailable(self, mod, tmp_path):
        mod._git_available = False
        success, output, skipped = mod.git_graceful_operation(
            ["status"], cwd=tmp_path
        )
        assert success is False
        assert skipped is True
        mod._git_available = None

    def test_git_graceful_timeout(self, mod, tmp_path):
        import subprocess
        mod._git_available = True
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=60)):
            success, output, skipped = mod.git_graceful_operation(
                ["status"], cwd=tmp_path
            )
            assert success is False
            assert skipped is False
        mod._git_available = None

    def test_git_graceful_os_error(self, mod, tmp_path):
        mod._git_available = True
        with patch("subprocess.run", side_effect=OSError("broken")):
            success, output, skipped = mod.git_graceful_operation(
                ["status"], cwd=tmp_path
            )
            assert success is False
            assert skipped is False
        mod._git_available = None


# ===========================================================================
# atomic_write_json / read_json_safe / restore_from_backup
# ===========================================================================

class TestAtomicWriteJson:
    def test_basic_write_and_read(self, mod, tmp_path):
        target = tmp_path / "test.json"
        data = {"key": "value", "中文": "支持"}
        mod.atomic_write_json(target, data, use_lock=False, backup=False)
        assert target.exists()
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_backup_created(self, mod, tmp_path):
        target = tmp_path / "test.json"
        mod.atomic_write_json(target, {"v": 1}, use_lock=False, backup=False)
        mod.atomic_write_json(target, {"v": 2}, use_lock=False, backup=True)
        backup = target.with_suffix(".json.bak")
        assert backup.exists()
        original = json.loads(backup.read_text(encoding="utf-8"))
        assert original == {"v": 1}

    def test_restore_from_backup(self, mod, tmp_path):
        target = tmp_path / "test.json"
        mod.atomic_write_json(target, {"original": True}, use_lock=False, backup=False)
        mod.atomic_write_json(target, {"updated": True}, use_lock=False, backup=True)
        assert mod.restore_from_backup(target) is True
        restored = json.loads(target.read_text(encoding="utf-8"))
        assert restored == {"original": True}

    def test_restore_no_backup(self, mod, tmp_path):
        target = tmp_path / "no_backup.json"
        assert mod.restore_from_backup(target) is False

    def test_invalid_json_data(self, mod, tmp_path):
        target = tmp_path / "bad.json"
        # Non-serializable type triggers AtomicWriteError
        with pytest.raises(mod.AtomicWriteError):
            mod.atomic_write_json(target, {"bad": object()}, use_lock=False)

    def test_with_filelock(self, mod, tmp_path):
        if not mod.HAS_FILELOCK:
            pytest.skip("filelock not installed")
        target = tmp_path / "locked.json"
        mod.atomic_write_json(target, {"locked": True}, use_lock=True, backup=False)
        assert json.loads(target.read_text(encoding="utf-8")) == {"locked": True}

    def test_creates_parent_dirs(self, mod, tmp_path):
        target = tmp_path / "sub" / "dir" / "test.json"
        mod.atomic_write_json(target, {"nested": True}, use_lock=False, backup=False)
        assert target.exists()


class TestReadJsonSafe:
    def test_read_existing(self, mod, tmp_path):
        target = tmp_path / "test.json"
        target.write_text('{"key": "value"}', encoding="utf-8")
        result = mod.read_json_safe(target)
        assert result == {"key": "value"}

    def test_read_missing(self, mod, tmp_path):
        result = mod.read_json_safe(tmp_path / "missing.json", {"default": True})
        assert result == {"default": True}

    def test_read_invalid_json(self, mod, tmp_path):
        target = tmp_path / "bad.json"
        target.write_text("not json", encoding="utf-8")
        result = mod.read_json_safe(target, {"fallback": True})
        assert result == {"fallback": True}

    def test_default_is_empty_dict(self, mod, tmp_path):
        result = mod.read_json_safe(tmp_path / "missing.json")
        assert result == {}
