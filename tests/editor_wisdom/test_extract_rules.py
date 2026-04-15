"""Tests for scripts/editor-wisdom/05_extract_rules.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "editor-wisdom"))

from importlib import import_module

extract_mod = import_module("05_extract_rules")
extract_rules = extract_mod.extract_rules
CATEGORIES = extract_mod.CATEGORIES
SEVERITY_VALUES = extract_mod.SEVERITY_VALUES

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "editor-rules.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _make_classified(data_dir: Path, source_dir: Path, entries: list[dict]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        p = Path(entry["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(entry.get("_body", "# Title\n" + "写作建议内容" * 50), encoding="utf-8")

    classified = [{k: v for k, v in e.items() if k != "_body"} for e in entries]
    (data_dir / "classified.json").write_text(json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8")


def _entry(tmp_path: Path, name: str, file_hash: str, categories: list[str] | None = None) -> dict:
    return {
        "path": str(tmp_path / "src" / name),
        "filename": name,
        "title": name.replace(".md", ""),
        "platform": "xhs",
        "word_count": 500,
        "file_hash": file_hash,
        "categories": categories or ["opening"],
        "summary": "测试摘要",
        "_body": "# Title\n" + "开篇第一句话必须抓住读者注意力" * 30,
    }


def _mock_response(rules: list[dict]) -> MagicMock:
    mock_content = MagicMock()
    mock_content.text = json.dumps(rules, ensure_ascii=False)
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    return mock_response


SAMPLE_RULES = [
    {
        "rule": "开篇第一段必须在50字内建立核心冲突",
        "why": "读者在前3秒决定是否继续阅读",
        "severity": "hard",
        "applies_to": ["golden_three", "opening_only"],
    },
    {
        "rule": "避免以天气描写或闹钟响铃开头",
        "why": "这是最常见的新手开头，编辑会直接跳过",
        "severity": "hard",
        "applies_to": ["golden_three"],
    },
]


@patch("anthropic.Anthropic")
def test_basic_extraction(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _mock_response(SAMPLE_RULES)

    data_dir = tmp_path / "data"
    entries = [_entry(tmp_path, "test.md", "hash_a")]
    _make_classified(data_dir, tmp_path / "src", entries)

    stats = extract_rules(data_dir)

    assert stats["total"] >= 1
    assert stats["api_calls"] == 1

    rules = json.loads((data_dir / "rules.json").read_text(encoding="utf-8"))
    assert len(rules) >= 1
    assert all(r["category"] in CATEGORIES for r in rules)


@patch("anthropic.Anthropic")
def test_schema_validation(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _mock_response(SAMPLE_RULES)

    data_dir = tmp_path / "data"
    entries = [_entry(tmp_path, "test.md", "hash_b")]
    _make_classified(data_dir, tmp_path / "src", entries)

    extract_rules(data_dir)

    rules = json.loads((data_dir / "rules.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=rules, schema=SCHEMA)


@patch("anthropic.Anthropic")
def test_cache_skips_unchanged(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _mock_response(SAMPLE_RULES)

    data_dir = tmp_path / "data"
    entries = [_entry(tmp_path, "test.md", "hash_c")]
    _make_classified(data_dir, tmp_path / "src", entries)

    extract_rules(data_dir)
    assert mock_client.messages.create.call_count == 1

    extract_rules(data_dir)
    assert mock_client.messages.create.call_count == 1


@patch("anthropic.Anthropic")
def test_rule_id_format(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _mock_response(SAMPLE_RULES)

    data_dir = tmp_path / "data"
    entries = [_entry(tmp_path, "test.md", "hash_d")]
    _make_classified(data_dir, tmp_path / "src", entries)

    extract_rules(data_dir)

    rules = json.loads((data_dir / "rules.json").read_text(encoding="utf-8"))
    for rule in rules:
        assert rule["id"].startswith("EW-")
        assert len(rule["id"]) == 7


@patch("anthropic.Anthropic")
def test_rule_length_limit(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    long_rules = [
        {"rule": "x" * 121, "why": "too long", "severity": "hard", "applies_to": ["all"]},
        {"rule": "短规则有效", "why": "ok", "severity": "soft", "applies_to": ["all"]},
    ]
    mock_client.messages.create.return_value = _mock_response(long_rules)

    data_dir = tmp_path / "data"
    entries = [_entry(tmp_path, "test.md", "hash_e")]
    _make_classified(data_dir, tmp_path / "src", entries)

    extract_rules(data_dir)

    rules = json.loads((data_dir / "rules.json").read_text(encoding="utf-8"))
    assert all(len(r["rule"]) <= 120 for r in rules)


@patch("anthropic.Anthropic")
def test_invalid_severity_defaults_to_info(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    bad_rules = [
        {"rule": "测试规则", "why": "原因", "severity": "invalid", "applies_to": ["all"]},
    ]
    mock_client.messages.create.return_value = _mock_response(bad_rules)

    data_dir = tmp_path / "data"
    entries = [_entry(tmp_path, "test.md", "hash_f")]
    _make_classified(data_dir, tmp_path / "src", entries)

    extract_rules(data_dir)

    rules = json.loads((data_dir / "rules.json").read_text(encoding="utf-8"))
    assert all(r["severity"] in SEVERITY_VALUES for r in rules)


@patch("anthropic.Anthropic")
def test_empty_input(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    data_dir = tmp_path / "data"
    _make_classified(data_dir, tmp_path / "src", [])

    stats = extract_rules(data_dir)
    assert stats["total"] == 0
    assert stats["api_calls"] == 0


@patch("anthropic.Anthropic")
def test_deduplication(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    same_rule = [{"rule": "重复规则", "why": "原因", "severity": "hard", "applies_to": ["all"]}]
    mock_client.messages.create.return_value = _mock_response(same_rule)

    data_dir = tmp_path / "data"
    entries = [
        _entry(tmp_path, "a.md", "h1", ["opening"]),
        _entry(tmp_path, "b.md", "h2", ["opening"]),
    ]
    _make_classified(data_dir, tmp_path / "src", entries)

    extract_rules(data_dir)

    rules = json.loads((data_dir / "rules.json").read_text(encoding="utf-8"))
    rule_texts = [r["rule"] for r in rules]
    assert rule_texts.count("重复规则") == 1
    dup_rule = next(r for r in rules if r["rule"] == "重复规则")
    assert len(dup_rule["source_files"]) == 2


@patch("anthropic.Anthropic")
def test_multiple_categories_uses_primary(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    rules_resp = [{"rule": "多分类规则", "why": "原因", "severity": "soft", "applies_to": ["all"]}]
    mock_client.messages.create.return_value = _mock_response(rules_resp)

    data_dir = tmp_path / "data"
    entries = [_entry(tmp_path, "multi.md", "h_multi", ["opening", "hook"])]
    _make_classified(data_dir, tmp_path / "src", entries)

    extract_rules(data_dir)

    rules = json.loads((data_dir / "rules.json").read_text(encoding="utf-8"))
    matched = [r for r in rules if r["rule"] == "多分类规则"]
    assert len(matched) == 1
    assert matched[0]["category"] == "opening"


@patch("anthropic.Anthropic")
def test_source_files_populated(mock_anthropic_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _mock_response(SAMPLE_RULES)

    data_dir = tmp_path / "data"
    entries = [_entry(tmp_path, "source_test.md", "hash_src")]
    _make_classified(data_dir, tmp_path / "src", entries)

    extract_rules(data_dir)

    rules = json.loads((data_dir / "rules.json").read_text(encoding="utf-8"))
    for rule in rules:
        assert len(rule["source_files"]) >= 1
        assert "source_test.md" in rule["source_files"]
