"""Tests for dashboard/path_guard.py — safe_resolve path traversal guard."""

import sys

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import HTTPException

from path_guard import safe_resolve

# US-004: Windows 未启用开发者模式时 os.symlink 会抛 OSError；跳过 symlink
# 相关测试避免 false negative。Mac/Linux 照常执行。
try:
    from runtime_compat import _has_symlink_privilege  # type: ignore
    _SYMLINK_ALLOWED = _has_symlink_privilege()
except Exception:  # pragma: no cover
    _SYMLINK_ALLOWED = sys.platform != "win32"

_symlink_required = pytest.mark.skipif(
    not _SYMLINK_ALLOWED,
    reason="symlink requires admin or Developer Mode on Windows",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_403(exc_info):
    """Assert that the captured HTTPException has status_code 403."""
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 1. Normal paths within project root
# ---------------------------------------------------------------------------

class TestNormalPaths:
    def test_simple_file(self, tmp_path):
        result = safe_resolve(tmp_path, "chapter01.txt")
        assert result == (tmp_path / "chapter01.txt").resolve()

    def test_subdirectory_file(self, tmp_path):
        result = safe_resolve(tmp_path, "src/main.py")
        assert result == (tmp_path / "src" / "main.py").resolve()

    def test_returned_path_is_absolute(self, tmp_path):
        result = safe_resolve(tmp_path, "foo/bar.txt")
        assert result.is_absolute()

    def test_returned_path_starts_with_root(self, tmp_path):
        result = safe_resolve(tmp_path, "data/file.json")
        assert str(result).startswith(str(tmp_path.resolve()))


# ---------------------------------------------------------------------------
# 2. Path traversal with ../
# ---------------------------------------------------------------------------

class TestSingleDotDotTraversal:
    def test_dot_dot_escapes_root(self, tmp_path):
        with pytest.raises(HTTPException) as exc_info:
            safe_resolve(tmp_path, "../escape.txt")
        _assert_403(exc_info)

    def test_dot_dot_at_start(self, tmp_path):
        with pytest.raises(HTTPException) as exc_info:
            safe_resolve(tmp_path, "../")
        _assert_403(exc_info)


# ---------------------------------------------------------------------------
# 3. Path traversal with ../../etc/passwd
# ---------------------------------------------------------------------------

class TestDeepTraversal:
    def test_etc_passwd(self, tmp_path):
        with pytest.raises(HTTPException) as exc_info:
            safe_resolve(tmp_path, "../../etc/passwd")
        _assert_403(exc_info)

    def test_many_levels_up(self, tmp_path):
        with pytest.raises(HTTPException) as exc_info:
            safe_resolve(tmp_path, "../../../../../../../../etc/shadow")
        _assert_403(exc_info)

    def test_dot_dot_hidden_in_middle(self, tmp_path):
        with pytest.raises(HTTPException) as exc_info:
            safe_resolve(tmp_path, "subdir/../../outside.txt")
        _assert_403(exc_info)


# ---------------------------------------------------------------------------
# 4. Absolute paths outside root
# ---------------------------------------------------------------------------

class TestAbsolutePathsOutsideRoot:
    def test_absolute_path_outside(self, tmp_path):
        with pytest.raises(HTTPException) as exc_info:
            safe_resolve(tmp_path, "/etc/passwd")
        _assert_403(exc_info)

    def test_absolute_path_to_tmp(self, tmp_path):
        """An absolute path that does not fall under tmp_path should be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            safe_resolve(tmp_path, "/tmp/other_project/secret.txt")
        _assert_403(exc_info)


# ---------------------------------------------------------------------------
# 5. Paths with symlink potential
# ---------------------------------------------------------------------------

@_symlink_required
class TestSymlinks:
    def test_symlink_escaping_root(self, tmp_path):
        """A symlink inside tmp_path that points outside should be rejected."""
        outside_dir = tmp_path.parent / "outside_target"
        outside_dir.mkdir(exist_ok=True)
        secret = outside_dir / "secret.txt"
        secret.write_text("secret", encoding="utf-8")

        link = tmp_path / "evil_link"
        link.symlink_to(outside_dir)

        with pytest.raises(HTTPException) as exc_info:
            safe_resolve(tmp_path, "evil_link/secret.txt")
        _assert_403(exc_info)

    def test_symlink_within_root_is_ok(self, tmp_path):
        """A symlink pointing to a location still inside root should succeed."""
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        (real_dir / "file.txt").write_text("ok", encoding="utf-8")

        link = tmp_path / "link_to_real"
        link.symlink_to(real_dir)

        result = safe_resolve(tmp_path, "link_to_real/file.txt")
        assert result == (real_dir / "file.txt").resolve()


# ---------------------------------------------------------------------------
# 6. Empty string path
# ---------------------------------------------------------------------------

class TestEmptyPath:
    def test_empty_string_resolves_to_root(self, tmp_path):
        result = safe_resolve(tmp_path, "")
        assert result == tmp_path.resolve()


# ---------------------------------------------------------------------------
# 7. Deeply nested valid paths
# ---------------------------------------------------------------------------

class TestDeeplyNestedPaths:
    def test_deep_nesting(self, tmp_path):
        deep = "a/b/c/d/e/f/g/h/i/j/file.txt"
        result = safe_resolve(tmp_path, deep)
        assert result == (tmp_path / deep).resolve()

    def test_very_long_path(self, tmp_path):
        segments = "/".join(f"dir{i}" for i in range(50))
        path_str = f"{segments}/file.txt"
        result = safe_resolve(tmp_path, path_str)
        assert result == (tmp_path / path_str).resolve()


# ---------------------------------------------------------------------------
# 8. Paths with special characters
# ---------------------------------------------------------------------------

class TestSpecialCharacters:
    def test_spaces_in_path(self, tmp_path):
        result = safe_resolve(tmp_path, "my folder/my file.txt")
        assert result == (tmp_path / "my folder" / "my file.txt").resolve()

    def test_unicode_characters(self, tmp_path):
        result = safe_resolve(tmp_path, "章节/第一章.txt")
        assert result == (tmp_path / "章节" / "第一章.txt").resolve()

    def test_dots_in_filename(self, tmp_path):
        result = safe_resolve(tmp_path, "archive/backup.2024.01.tar.gz")
        expected = (tmp_path / "archive" / "backup.2024.01.tar.gz").resolve()
        assert result == expected

    def test_single_dot_current_dir(self, tmp_path):
        result = safe_resolve(tmp_path, "./subdir/file.txt")
        assert result == (tmp_path / "subdir" / "file.txt").resolve()

    def test_hash_in_name(self, tmp_path):
        result = safe_resolve(tmp_path, "notes/#draft.md")
        assert result == (tmp_path / "notes" / "#draft.md").resolve()
