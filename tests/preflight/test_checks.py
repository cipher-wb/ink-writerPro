"""Unit tests for the six independent preflight check functions (US-014)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from ink_writer.preflight.checks import (
    CheckResult,
    check_case_library_loadable,
    check_editor_wisdom_index_loadable,
    check_embedding_api_reachable,
    check_qdrant_connection,
    check_reference_corpus_readable,
    check_rerank_api_reachable,
)


def _make_txt(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------- reference_corpus_readable ----------

def test_reference_corpus_pass(tmp_path: Path) -> None:
    root = tmp_path / "reference_corpus"
    for i in range(5):
        _make_txt(root / "book" / "chapters" / f"ch{i:03d}.txt")
    result = check_reference_corpus_readable(root, min_files=3)
    assert isinstance(result, CheckResult)
    assert result.passed is True
    assert "5 files readable" in result.detail


def test_reference_corpus_fail_when_below_min(tmp_path: Path) -> None:
    root = tmp_path / "reference_corpus"
    for i in range(2):
        _make_txt(root / "book" / "chapters" / f"ch{i:03d}.txt")
    result = check_reference_corpus_readable(root, min_files=10)
    assert result.passed is False
    assert "2 files readable" in result.detail
    assert "10 minimum" in result.detail


def test_reference_corpus_fail_when_broken_symlink(tmp_path: Path) -> None:
    root = tmp_path / "reference_corpus"
    chapters = root / "book" / "chapters"
    chapters.mkdir(parents=True)
    # One broken symlink is enough to trip the check regardless of readable count.
    broken = chapters / "ch001.txt"
    broken.symlink_to(tmp_path / "nonexistent.txt")  # c5-ok: intentional dangling symlink is the SUT fixture
    result = check_reference_corpus_readable(root, min_files=1)
    assert result.passed is False
    assert "broken symlink" in result.detail


# ---------- case_library_loadable ----------

def test_case_library_loadable_pass(tmp_path: Path) -> None:
    library_root = tmp_path / "case_library"
    (library_root / "cases").mkdir(parents=True)
    (library_root / "cases" / "CASE-2026-0001.yaml").write_text(
        "case_id: CASE-2026-0001\n", encoding="utf-8"
    )
    result = check_case_library_loadable(library_root)
    assert result.passed is True
    assert "1 cases on disk" in result.detail


def test_case_library_loadable_fail_when_missing(tmp_path: Path) -> None:
    library_root = tmp_path / "case_library"
    # Note: cases/ subdirectory not created.
    result = check_case_library_loadable(library_root)
    assert result.passed is False
    assert "missing" in result.detail


# ---------- editor_wisdom_index_loadable ----------

def test_editor_wisdom_index_loadable_pass(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(
        json.dumps([{"id": "EW-0001"}, {"id": "EW-0002"}]), encoding="utf-8"
    )
    result = check_editor_wisdom_index_loadable(rules_path)
    assert result.passed is True
    assert "2 rules indexed" in result.detail


def test_editor_wisdom_index_loadable_fail_when_missing(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.json"
    # File not created.
    result = check_editor_wisdom_index_loadable(rules_path)
    assert result.passed is False
    assert "not found" in result.detail


# ---------- qdrant_connection ----------

def test_qdrant_connection_pass_with_in_memory_client(in_memory_client) -> None:
    result = check_qdrant_connection(client=in_memory_client)
    assert result.passed is True
    assert "reachable" in result.detail


# ---------- embedding / rerank api keys ----------

def test_embedding_api_reachable_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMBED_API_KEY", raising=False)
    result = check_embedding_api_reachable()
    assert result.passed is False
    assert result.detail == "EMBED_API_KEY not set"


def test_rerank_api_reachable_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RERANK_API_KEY", raising=False)
    result = check_rerank_api_reachable()
    assert result.passed is False
    assert result.detail == "RERANK_API_KEY not set"
