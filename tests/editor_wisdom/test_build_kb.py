"""Tests for scripts/editor-wisdom/04_build_kb.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "editor-wisdom"))

from importlib import import_module

kb_mod = import_module("04_build_kb")
build_kb = kb_mod.build_kb
CATEGORIES = kb_mod.CATEGORIES
CATEGORY_NAMES = kb_mod.CATEGORY_NAMES


def _make_classified(data_dir: Path, source_dir: Path, entries: list[dict]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        p = Path(entry["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        body = entry.get("_body", f"# {entry['title']}\n\n这是一段详细的写作建议内容，需要超过二十个字才能被提取为引用。")
        p.write_text(body, encoding="utf-8")

    classified = [{k: v for k, v in e.items() if k != "_body"} for e in entries]
    (data_dir / "classified.json").write_text(
        json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _entry(
    tmp_path: Path,
    name: str,
    categories: list[str],
    summary: str,
    platform: str = "xhs",
    body: str | None = None,
) -> dict:
    return {
        "path": str(tmp_path / "src" / name),
        "filename": name,
        "title": name.replace(".md", ""),
        "platform": platform,
        "word_count": 200,
        "file_hash": f"hash_{name}",
        "categories": categories,
        "summary": summary,
        "_body": body if body else f"# {name.replace('.md', '')}\n\n这是一段关于写作技巧的详细建议，内容足够长可以被提取为引用文本。",
    }


def test_builds_all_category_files(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    entries = [
        _entry(tmp_path, "a.md", ["opening", "hook"], "开篇要有冲击力"),
        _entry(tmp_path, "b.md", ["character"], "角色要立体"),
    ]
    _make_classified(data_dir, tmp_path / "src", entries)

    build_kb(data_dir, docs_dir)

    for cat in CATEGORIES:
        assert (docs_dir / f"{cat}.md").exists(), f"{cat}.md missing"
    assert (docs_dir / "README.md").exists()


def test_category_file_structure(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    entries = [
        _entry(tmp_path, "a.md", ["opening"], "开篇三秒抓人"),
        _entry(tmp_path, "b.md", ["opening"], "第一句话决定生死"),
    ]
    _make_classified(data_dir, tmp_path / "src", entries)

    build_kb(data_dir, docs_dir)

    content = (docs_dir / "opening.md").read_text(encoding="utf-8")
    assert f"# {CATEGORY_NAMES['opening']}" in content
    assert "## 核心原则" in content
    assert "## 详细建议" in content
    assert "开篇三秒抓人" in content
    assert "第一句话决定生死" in content


def test_principles_limited_to_10(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    entries = [
        _entry(tmp_path, f"f{i}.md", ["opening"], f"原则{i}")
        for i in range(15)
    ]
    _make_classified(data_dir, tmp_path / "src", entries)

    build_kb(data_dir, docs_dir)

    content = (docs_dir / "opening.md").read_text(encoding="utf-8")
    principles_section = content.split("## 核心原则")[1].split("## 详细建议")[0]
    bullet_count = principles_section.count("\n- ")
    assert bullet_count <= 10


def test_readme_links_all_categories(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    entries = [_entry(tmp_path, "a.md", ["misc"], "综合建议")]
    _make_classified(data_dir, tmp_path / "src", entries)

    build_kb(data_dir, docs_dir)

    readme = (docs_dir / "README.md").read_text(encoding="utf-8")
    for cat in CATEGORIES:
        assert f"{cat}.md" in readme
        assert CATEGORY_NAMES[cat] in readme


def test_empty_category_has_placeholder(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    entries = [_entry(tmp_path, "a.md", ["opening"], "开篇技巧")]
    _make_classified(data_dir, tmp_path / "src", entries)

    build_kb(data_dir, docs_dir)

    content = (docs_dir / "character.md").read_text(encoding="utf-8")
    assert "暂无条目" in content


def test_multi_category_entry_appears_in_each(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    entries = [
        _entry(tmp_path, "multi.md", ["opening", "hook", "pacing"], "跨分类建议"),
    ]
    _make_classified(data_dir, tmp_path / "src", entries)

    build_kb(data_dir, docs_dir)

    for cat in ["opening", "hook", "pacing"]:
        content = (docs_dir / f"{cat}.md").read_text(encoding="utf-8")
        assert "multi" in content


def test_returns_counts(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    entries = [
        _entry(tmp_path, "a.md", ["opening", "hook"], "建议A"),
        _entry(tmp_path, "b.md", ["opening"], "建议B"),
        _entry(tmp_path, "c.md", ["character"], "建议C"),
    ]
    _make_classified(data_dir, tmp_path / "src", entries)

    counts = build_kb(data_dir, docs_dir)

    assert counts["opening"] == 2
    assert counts["hook"] == 1
    assert counts["character"] == 1
    assert counts["pacing"] == 0


def test_empty_classified(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    _make_classified(data_dir, tmp_path / "src", [])

    counts = build_kb(data_dir, docs_dir)

    assert all(v == 0 for v in counts.values())
    assert (docs_dir / "README.md").exists()
    for cat in CATEGORIES:
        assert (docs_dir / f"{cat}.md").exists()


def test_platform_label_display(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    entries = [
        _entry(tmp_path, "xhs.md", ["misc"], "小红书建议", platform="xhs"),
        _entry(tmp_path, "dy.md", ["misc"], "抖音建议", platform="douyin"),
    ]
    _make_classified(data_dir, tmp_path / "src", entries)

    build_kb(data_dir, docs_dir)

    content = (docs_dir / "misc.md").read_text(encoding="utf-8")
    assert "小红书" in content
    assert "抖音" in content


def test_quote_extraction(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    body = "# 标题\n\n这是第一段正文内容，写得比较长，可以被用作引用文本。\n\n## 小标题\n\n其他内容"
    entries = [
        _entry(tmp_path, "q.md", ["opening"], "引用测试", body=body),
    ]
    _make_classified(data_dir, tmp_path / "src", entries)

    build_kb(data_dir, docs_dir)

    content = (docs_dir / "opening.md").read_text(encoding="utf-8")
    assert ">" in content
    assert "这是第一段正文内容" in content
