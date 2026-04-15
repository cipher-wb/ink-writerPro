"""Tests for scripts/editor-wisdom/01_scan.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "editor-wisdom"))

from importlib import import_module

scan_mod = import_module("01_scan")
scan = scan_mod.scan


def _make_source(tmp_path: Path) -> Path:
    """Build a minimal source tree mimicking 星河编辑 layout."""
    src = tmp_path / "source"
    xhs = src / "编辑星河"
    douyin = src / "编辑星河_抖音"
    xhs.mkdir(parents=True)
    douyin.mkdir(parents=True)

    (xhs / "001_test.md").write_text("# 标题一\n正文内容", encoding="utf-8")
    (xhs / "002_test.md").write_text("# 标题二\nmore content", encoding="utf-8")
    (douyin / "100_test.md").write_text("# 抖音标题\n抖音内容", encoding="utf-8")
    return src


def test_scan_basic(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    out = tmp_path / "output"

    stats = scan(src, out)

    assert stats["indexed"] == 3
    assert stats["skipped"] == 0

    raw = json.loads((out / "raw_index.json").read_text(encoding="utf-8"))
    assert len(raw) == 3

    platforms = {e["platform"] for e in raw}
    assert platforms == {"xhs", "douyin"}

    for entry in raw:
        assert "path" in entry
        assert "filename" in entry
        assert "title" in entry
        assert "platform" in entry
        assert "word_count" in entry
        assert "file_hash" in entry
        assert entry["word_count"] > 0


def test_scan_skipped_log_exists(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    out = tmp_path / "output"
    scan(src, out)
    assert (out / "skipped.log").exists()


def test_scan_count_integrity(tmp_path: Path) -> None:
    """indexed + skipped == total .md files in source."""
    src = _make_source(tmp_path)
    out = tmp_path / "output"
    stats = scan(src, out)

    total_md = len(list(src.rglob("*.md")))
    assert stats["indexed"] + stats["skipped"] == total_md


def test_scan_title_extraction(tmp_path: Path) -> None:
    src = tmp_path / "source" / "编辑星河"
    src.mkdir(parents=True)
    (src / "t.md").write_text("# My Title\nbody", encoding="utf-8")

    out = tmp_path / "output"
    scan(src.parent, out)
    raw = json.loads((out / "raw_index.json").read_text(encoding="utf-8"))
    assert raw[0]["title"] == "My Title"


def test_scan_empty_source(tmp_path: Path) -> None:
    src = tmp_path / "source"
    src.mkdir()
    out = tmp_path / "output"
    stats = scan(src, out)
    assert stats["indexed"] == 0
    assert stats["skipped"] == 0
