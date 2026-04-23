"""Tests for :mod:`scripts.maintenance.fix_reference_corpus_symlinks` (US-001).

Covers the three file-state outcomes: broken symlink → hard copy, real file →
skipped, source missing → recorded in ``missing_paths`` without aborting.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.maintenance.fix_reference_corpus_symlinks import (
    FixReport,
    fix_reference_corpus_symlinks,
)


def _make_corpus_source(corpus_root: Path, book: str, chapter: str, body: str) -> Path:
    chapter_dir = corpus_root / book / "chapters"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    source = chapter_dir / chapter
    source.write_text(body, encoding="utf-8")
    return source


def _make_broken_symlink(
    reference_root: Path, book: str, chapter: str, dangling_target: Path
) -> Path:
    chapter_dir = reference_root / book / "chapters"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    link = chapter_dir / chapter
    # dangling_target doesn't need to exist — that's the whole point of the fix.
    link.symlink_to(dangling_target)
    return link


def test_fix_replaces_broken_symlinks_with_hard_copies(tmp_path: Path) -> None:
    reference_root = tmp_path / "reference_corpus"
    corpus_root = tmp_path / "corpus"

    body = "第一章\n克莱恩睁开了眼睛。"
    _make_corpus_source(corpus_root, "诡秘之主", "ch001.txt", body)
    link = _make_broken_symlink(
        reference_root,
        "诡秘之主",
        "ch001.txt",
        dangling_target=Path("/nonexistent/ink/诡秘之主/chapters/ch001.txt"),
    )
    assert link.is_symlink() and not link.exists()

    report = fix_reference_corpus_symlinks(reference_root, corpus_root)

    assert isinstance(report, FixReport)
    assert report.fixed == 1
    assert report.skipped == 0
    assert report.missing_source == 0
    assert report.missing_paths == []
    # Link is gone — a real file sits in its place with the expected bytes.
    assert not link.is_symlink()
    assert link.is_file()
    assert link.read_text(encoding="utf-8") == body


def test_fix_skips_already_real_files(tmp_path: Path) -> None:
    reference_root = tmp_path / "reference_corpus"
    corpus_root = tmp_path / "corpus"

    chapter_dir = reference_root / "诡秘之主" / "chapters"
    chapter_dir.mkdir(parents=True)
    real_file = chapter_dir / "ch001.txt"
    real_file.write_text("已经是真实文件", encoding="utf-8")
    # corpus_root is empty — prove the script doesn't need a source for real files.

    report = fix_reference_corpus_symlinks(reference_root, corpus_root)

    assert report.fixed == 0
    assert report.skipped == 1
    assert report.missing_source == 0
    # File content untouched.
    assert real_file.read_text(encoding="utf-8") == "已经是真实文件"


def test_fix_records_missing_source(tmp_path: Path) -> None:
    reference_root = tmp_path / "reference_corpus"
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()

    link = _make_broken_symlink(
        reference_root,
        "诡秘之主",
        "ch999.txt",
        dangling_target=Path("/nonexistent/ink/诡秘之主/chapters/ch999.txt"),
    )

    report = fix_reference_corpus_symlinks(reference_root, corpus_root)

    assert report.fixed == 0
    assert report.skipped == 0
    assert report.missing_source == 1
    assert str(link) in report.missing_paths
    # Broken link still there — we didn't silently delete it.
    assert link.is_symlink()
    assert not link.exists()


def test_fix_is_idempotent_on_second_run(tmp_path: Path) -> None:
    reference_root = tmp_path / "reference_corpus"
    corpus_root = tmp_path / "corpus"

    body = "body"
    _make_corpus_source(corpus_root, "bookA", "ch001.txt", body)
    _make_broken_symlink(
        reference_root,
        "bookA",
        "ch001.txt",
        dangling_target=Path("/nonexistent/bookA/chapters/ch001.txt"),
    )

    first = fix_reference_corpus_symlinks(reference_root, corpus_root)
    second = fix_reference_corpus_symlinks(reference_root, corpus_root)

    assert first.fixed == 1
    assert second.fixed == 0
    assert second.skipped == 1


def test_fix_returns_empty_report_when_reference_root_absent(tmp_path: Path) -> None:
    report = fix_reference_corpus_symlinks(
        tmp_path / "does-not-exist", tmp_path / "corpus"
    )
    assert report.fixed == 0
    assert report.skipped == 0
    assert report.missing_source == 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
