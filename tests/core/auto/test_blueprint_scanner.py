# tests/core/auto/test_blueprint_scanner.py
from pathlib import Path
from ink_writer.core.auto.blueprint_scanner import find_blueprint, BLACKLIST


def test_returns_none_in_empty_dir(tmp_path: Path) -> None:
    assert find_blueprint(tmp_path) is None


def test_returns_none_when_only_blacklisted_md(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# readme", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# claude", encoding="utf-8")
    (tmp_path / "TODO.md").write_text("# todo", encoding="utf-8")
    assert find_blueprint(tmp_path) is None


def test_blacklist_is_case_insensitive(tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text("# readme", encoding="utf-8")
    (tmp_path / "Claude.MD").write_text("# claude", encoding="utf-8")
    assert find_blueprint(tmp_path) is None


def test_excludes_draft_md(tmp_path: Path) -> None:
    (tmp_path / "idea.draft.md").write_text("# draft", encoding="utf-8")
    assert find_blueprint(tmp_path) is None


def test_picks_largest_md_when_multiple_candidates(tmp_path: Path) -> None:
    small = tmp_path / "idea.md"
    big = tmp_path / "setup.md"
    small.write_text("x" * 500, encoding="utf-8")
    big.write_text("x" * 5000, encoding="utf-8")
    assert find_blueprint(tmp_path) == big


def test_does_not_recurse_into_subdirs(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "extra.md").write_text("x" * 9999, encoding="utf-8")
    top = tmp_path / "idea.md"
    top.write_text("x" * 100, encoding="utf-8")
    assert find_blueprint(tmp_path) == top


def test_blacklist_contents() -> None:
    expected = {"README.MD", "CLAUDE.MD", "TODO.MD", "CHANGELOG.MD", "LICENSE.MD", "CONTRIBUTING.MD", "AGENTS.MD", "GEMINI.MD"}
    assert expected.issubset({n.upper() for n in BLACKLIST})
