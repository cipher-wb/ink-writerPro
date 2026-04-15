"""Tests for scripts/editor-wisdom/02_clean.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "editor-wisdom"))

from importlib import import_module

clean_mod = import_module("02_clean")
clean = clean_mod.clean


def _make_raw_index(data_dir: Path, source_dir: Path, entries: list[dict]) -> None:
    """Build raw_index.json and corresponding source files."""
    data_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        p = Path(entry["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(entry.get("_body", "# Title\n" + "x" * 100), encoding="utf-8")

    raw = [{k: v for k, v in e.items() if k != "_body"} for e in entries]
    (data_dir / "raw_index.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")


def _entry(tmp_path: Path, name: str, body: str | None = None) -> dict:
    path = str(tmp_path / "src" / name)
    return {
        "path": path,
        "filename": name,
        "title": name.replace(".md", ""),
        "platform": "xhs",
        "word_count": len(body) if body else 100,
        "file_hash": f"hash_{name}",
        "_body": body if body else "# Title\n" + "x" * 100,
    }


def test_basic_clean(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    entries = [
        _entry(tmp_path, "good_file.md"),
        _entry(tmp_path, "another_good.md", "# Title\n" + "y" * 200),
    ]
    _make_raw_index(data_dir, tmp_path / "src", entries)

    stats = clean(data_dir)
    assert stats["kept"] == 2
    assert stats["dropped_short"] == 0
    assert stats["dropped_noise"] == 0


def test_drop_short_content(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    entries = [
        _entry(tmp_path, "short.md", "tiny"),
        _entry(tmp_path, "good.md"),
    ]
    _make_raw_index(data_dir, tmp_path / "src", entries)

    stats = clean(data_dir)
    assert stats["kept"] == 1
    assert stats["dropped_short"] == 1


def test_drop_noise_keywords(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    entries = [
        _entry(tmp_path, "001_手机号登录.md"),
        _entry(tmp_path, "002_验证码输入.md"),
        _entry(tmp_path, "003_登录页面.md"),
        _entry(tmp_path, "good.md"),
    ]
    _make_raw_index(data_dir, tmp_path / "src", entries)

    stats = clean(data_dir)
    assert stats["kept"] == 1
    assert stats["dropped_noise"] == 3


def test_drop_near_duplicates(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    body = "# 标题\n" + "这是一段很长的重复内容用来测试去重功能" * 20
    entries = [
        _entry(tmp_path, "original.md", body),
        _entry(tmp_path, "duplicate.md", body),
    ]
    _make_raw_index(data_dir, tmp_path / "src", entries)

    stats = clean(data_dir)
    assert stats["kept"] == 1
    assert stats["dropped_dup"] == 1


def test_outputs_exist(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    entries = [_entry(tmp_path, "file.md")]
    _make_raw_index(data_dir, tmp_path / "src", entries)

    clean(data_dir)

    assert (data_dir / "clean_index.json").exists()
    assert (data_dir / "cleanup_report.md").exists()


def test_cleanup_report_content(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    entries = [
        _entry(tmp_path, "short.md", "tiny"),
        _entry(tmp_path, "手机号登录.md"),
        _entry(tmp_path, "good.md"),
    ]
    _make_raw_index(data_dir, tmp_path / "src", entries)

    clean(data_dir)

    report = (data_dir / "cleanup_report.md").read_text(encoding="utf-8")
    assert "Total input: 3" in report
    assert "Kept: 1" in report


def test_clean_index_schema(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    entries = [_entry(tmp_path, "good.md")]
    _make_raw_index(data_dir, tmp_path / "src", entries)

    clean(data_dir)

    result = json.loads((data_dir / "clean_index.json").read_text(encoding="utf-8"))
    assert len(result) == 1
    assert "_body" not in result[0]
    for key in ("path", "filename", "title", "platform", "word_count", "file_hash"):
        assert key in result[0]


def test_empty_input(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _make_raw_index(data_dir, tmp_path / "src", [])

    stats = clean(data_dir)
    assert stats["kept"] == 0


def test_different_content_not_deduped(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    entries = [
        _entry(tmp_path, "a.md", "# A\n" + "完全不同的第一篇内容" * 20),
        _entry(tmp_path, "b.md", "# B\n" + "另外一个完全独立的文章" * 20),
    ]
    _make_raw_index(data_dir, tmp_path / "src", entries)

    stats = clean(data_dir)
    assert stats["kept"] == 2
    assert stats["dropped_dup"] == 0
