"""Tests for scripts/editor-wisdom/03_classify.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "editor-wisdom"))

from importlib import import_module

classify_mod = import_module("03_classify")
classify = classify_mod.classify
CATEGORIES = classify_mod.CATEGORIES


def _make_clean_index(data_dir: Path, source_dir: Path, entries: list[dict]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        p = Path(entry["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(entry.get("_body", "# Title\n" + "x" * 200), encoding="utf-8")

    clean = [{k: v for k, v in e.items() if k != "_body"} for e in entries]
    (data_dir / "clean_index.json").write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")


def _entry(tmp_path: Path, name: str, file_hash: str, body: str | None = None) -> dict:
    return {
        "path": str(tmp_path / "src" / name),
        "filename": name,
        "title": name.replace(".md", ""),
        "platform": "xhs",
        "word_count": 200,
        "file_hash": file_hash,
        "_body": body if body else "# Title\n" + "这是一篇关于开篇技巧的文章" * 20,
    }


def _mock_anthropic_response(categories: list[str], summary: str) -> MagicMock:
    mock_content = MagicMock()
    mock_content.text = json.dumps({"categories": categories, "summary": summary})
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    return mock_response


@patch("anthropic.Anthropic")
def test_classify_basic(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _mock_anthropic_response(
        ["opening", "hook"], "开篇要抓人"
    )

    data_dir = tmp_path / "data"
    entries = [_entry(tmp_path, "test.md", "hash_a")]
    _make_clean_index(data_dir, tmp_path / "src", entries)

    stats = classify(data_dir)

    assert stats["total"] == 1
    assert stats["api_calls"] == 1

    result = json.loads((data_dir / "classified.json").read_text(encoding="utf-8"))
    assert len(result) == 1
    assert result[0]["categories"] == ["opening", "hook"]
    assert result[0]["summary"] == "开篇要抓人"


@patch("anthropic.Anthropic")
def test_cache_skips_unchanged(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _mock_anthropic_response(
        ["pacing"], "节奏控制"
    )

    data_dir = tmp_path / "data"
    entries = [_entry(tmp_path, "test.md", "hash_b")]
    _make_clean_index(data_dir, tmp_path / "src", entries)

    classify(data_dir)
    assert mock_client.messages.create.call_count == 1

    classify(data_dir)
    assert mock_client.messages.create.call_count == 1


@patch("anthropic.Anthropic")
def test_invalid_category_falls_back_to_misc(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _mock_anthropic_response(
        ["nonexistent_category"], "some summary"
    )

    data_dir = tmp_path / "data"
    entries = [_entry(tmp_path, "test.md", "hash_c")]
    _make_clean_index(data_dir, tmp_path / "src", entries)

    classify(data_dir)
    result = json.loads((data_dir / "classified.json").read_text(encoding="utf-8"))
    assert result[0]["categories"] == ["misc"]


@patch("anthropic.Anthropic")
def test_output_files_exist(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _mock_anthropic_response(
        ["character"], "角色塑造"
    )

    data_dir = tmp_path / "data"
    entries = [_entry(tmp_path, "test.md", "hash_d")]
    _make_clean_index(data_dir, tmp_path / "src", entries)

    classify(data_dir)

    assert (data_dir / "classified.json").exists()
    assert (data_dir / "classify_report.md").exists()
    assert (data_dir / "classify_cache.json").exists()


@patch("anthropic.Anthropic")
def test_classified_schema(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _mock_anthropic_response(
        ["taboo", "genre"], "避免常见雷区"
    )

    data_dir = tmp_path / "data"
    entries = [_entry(tmp_path, "test.md", "hash_e")]
    _make_clean_index(data_dir, tmp_path / "src", entries)

    classify(data_dir)

    result = json.loads((data_dir / "classified.json").read_text(encoding="utf-8"))
    for entry in result:
        assert "categories" in entry
        assert "summary" in entry
        assert isinstance(entry["categories"], list)
        assert all(c in CATEGORIES for c in entry["categories"])
        assert "path" in entry
        assert "filename" in entry
        assert "file_hash" in entry


@patch("anthropic.Anthropic")
def test_report_has_distribution(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _mock_anthropic_response(
        ["opening"], "开篇技巧"
    )

    data_dir = tmp_path / "data"
    entries = [
        _entry(tmp_path, "a.md", "hash_f"),
        _entry(tmp_path, "b.md", "hash_g"),
    ]
    _make_clean_index(data_dir, tmp_path / "src", entries)

    classify(data_dir)

    report = (data_dir / "classify_report.md").read_text(encoding="utf-8")
    assert "Category Distribution" in report
    assert "opening" in report
    assert "Random Samples" in report
    assert "Total files: 2" in report


@patch("anthropic.Anthropic")
def test_empty_input(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    data_dir = tmp_path / "data"
    _make_clean_index(data_dir, tmp_path / "src", [])

    stats = classify(data_dir)
    assert stats["total"] == 0
    assert stats["api_calls"] == 0

    result = json.loads((data_dir / "classified.json").read_text(encoding="utf-8"))
    assert len(result) == 0


@patch("anthropic.Anthropic")
def test_multiple_files_mixed_categories(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    responses = [
        _mock_anthropic_response(["opening", "hook"], "开篇钩子"),
        _mock_anthropic_response(["character"], "角色设计"),
        _mock_anthropic_response(["ops"], "运营技巧"),
    ]
    mock_client.messages.create.side_effect = responses

    data_dir = tmp_path / "data"
    entries = [
        _entry(tmp_path, "a.md", "h1"),
        _entry(tmp_path, "b.md", "h2"),
        _entry(tmp_path, "c.md", "h3"),
    ]
    _make_clean_index(data_dir, tmp_path / "src", entries)

    stats = classify(data_dir)
    assert stats["total"] == 3
    assert stats["api_calls"] == 3

    result = json.loads((data_dir / "classified.json").read_text(encoding="utf-8"))
    all_cats = set()
    for entry in result:
        all_cats.update(entry["categories"])
    assert "opening" in all_cats
    assert "character" in all_cats
    assert "ops" in all_cats
