"""Unit tests for ``scripts.corpus_chunking.cli`` (M2 US-005).

Two AC-mandated tests:

1. ``test_ingest_dry_run_does_not_call_qdrant`` — Mock the anthropic client
   so ``segment_chapter`` returns no chunks, then verify that
   ``_build_qdrant_client`` / ``_build_embedding_client`` are *never* called
   under ``--dry-run``.

2. ``test_ingest_resume_skips_indexed_chapters`` — Drive the
   ``_already_indexed`` helper directly (PRD-permitted shortcut).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from scripts.corpus_chunking import cli as cli_mod

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_CONFIG = _REPO_ROOT / "config" / "corpus_chunking.yaml"


def _make_fake_anthropic_empty_segments() -> MagicMock:
    """Return a MagicMock that mimics ``anthropic.Anthropic`` returning empty chunks."""
    client = MagicMock()
    resp = MagicMock()
    resp.content = [MagicMock(text='{"chunks": []}')]
    client.messages.create.return_value = resp
    return client


def test_ingest_dry_run_does_not_call_qdrant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Create a minimal corpus dir with one book + one chapter.
    corpus_dir = tmp_path / "corpus"
    book_dir = corpus_dir / "sample_book"
    (book_dir / "chapters").mkdir(parents=True)
    (book_dir / "chapters" / "ch001.txt").write_text(
        "克莱恩盯着镜子。" * 40, encoding="utf-8"
    )
    (book_dir / "manifest.json").write_text(
        json.dumps({"genre": "玄幻"}, ensure_ascii=False), encoding="utf-8"
    )

    fake_anthropic = _make_fake_anthropic_empty_segments()
    build_qdrant = MagicMock(side_effect=AssertionError("qdrant must not be built"))
    build_embed = MagicMock(side_effect=AssertionError("embedder must not be built"))

    monkeypatch.setattr(cli_mod, "_build_anthropic_client", lambda: fake_anthropic)
    monkeypatch.setattr(cli_mod, "_build_qdrant_client", build_qdrant)
    monkeypatch.setattr(cli_mod, "_build_embedding_client", build_embed)
    # Redirect default DATA_DIR to tmp so we don't write into repo data/.
    monkeypatch.setattr(cli_mod, "DEFAULT_DATA_DIR", tmp_path / "data")

    rc = cli_mod.main(
        [
            "--config",
            str(_REAL_CONFIG),
            "ingest",
            "--dry-run",
            "--dir",
            str(corpus_dir),
        ]
    )

    assert rc == 0
    assert build_qdrant.call_count == 0
    assert build_embed.call_count == 0
    # The segmenter was invoked (proves dry-run still drives the LLM half).
    assert fake_anthropic.messages.create.called


def test_ingest_resume_skips_indexed_chapters(tmp_path: Path) -> None:
    raw_path = tmp_path / "chunks_raw.jsonl"
    raw_path.write_text(
        json.dumps(
            {
                "chunk_id": "CHUNK-诡秘之主-ch001-§1",
                "source_book": "诡秘之主",
                "source_chapter": "ch001",
                "char_range": [0, 100],
                "text": "...",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    # Exact match → already indexed.
    assert cli_mod._already_indexed("诡秘之主", "ch001", raw_path) is True
    # Different chapter → not indexed yet.
    assert cli_mod._already_indexed("诡秘之主", "ch002", raw_path) is False
    # Different book (same chapter id) → not indexed yet.
    assert cli_mod._already_indexed("另一本书", "ch001", raw_path) is False
    # Missing raw_path → not indexed.
    assert cli_mod._already_indexed("any", "any", tmp_path / "nope.jsonl") is False
