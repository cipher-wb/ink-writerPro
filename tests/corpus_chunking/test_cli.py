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


def test_rebuild_without_yes_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_mod, "DEFAULT_DATA_DIR", tmp_path / "data")
    # Guard: _build_qdrant_client must NOT be invoked when --yes is absent.
    monkeypatch.setattr(
        cli_mod,
        "_build_qdrant_client",
        MagicMock(side_effect=AssertionError("qdrant must not be built without --yes")),
    )
    rc = cli_mod.main(["--config", str(_REAL_CONFIG), "rebuild"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "--yes" in err


def test_rebuild_with_yes_clears_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # Pre-populate the 5 jsonl files so we can verify they're deleted.
    expected_files = (
        "chunks_raw.jsonl",
        "chunks_tagged.jsonl",
        "metadata.jsonl",
        "failures.jsonl",
        "unindexed.jsonl",
    )
    for fname in expected_files:
        (data_dir / fname).write_text("{}\n", encoding="utf-8")

    qdrant_mock = MagicMock()
    ingest_mock = MagicMock(return_value=0)

    monkeypatch.setattr(cli_mod, "DEFAULT_DATA_DIR", data_dir)
    monkeypatch.setattr(cli_mod, "_build_qdrant_client", lambda: qdrant_mock)
    monkeypatch.setattr(cli_mod, "_cmd_ingest", ingest_mock)

    rc = cli_mod.main(["--config", str(_REAL_CONFIG), "rebuild", "--yes"])

    assert rc == 0
    qdrant_mock.delete_collection.assert_called_once_with(collection_name="corpus_chunks")
    # ensure_collection(qd, CORPUS_CHUNKS_SPEC) must have run against the mock.
    assert qdrant_mock.collection_exists.called
    # Re-ingest was triggered exactly once.
    assert ingest_mock.call_count == 1
    # All 5 jsonl files removed.
    for fname in expected_files:
        assert not (data_dir / fname).exists(), f"{fname} should have been deleted"


def test_watch_detects_new_file_and_triggers_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Polling watcher fires ``_ingest_single_file`` on new / changed files.

    Uses ``--iterations 2 --interval 0`` + ``time.sleep`` stubbed out so the
    test runs synchronously. Two chapter files staged before the call → we
    expect ``_ingest_single_file`` called once per file (2 total).
    """
    watch_dir = tmp_path / "corpus"
    chapters = watch_dir / "sample_book" / "chapters"
    chapters.mkdir(parents=True)
    (chapters / "ch001.txt").write_text("hello", encoding="utf-8")
    (chapters / "ch002.txt").write_text("world", encoding="utf-8")

    ingest_calls: list[Path] = []

    def _fake_ingest(file_path: Path, _cfg: dict[str, object]) -> None:
        ingest_calls.append(file_path)

    monkeypatch.setattr(cli_mod, "_ingest_single_file", _fake_ingest)
    # Avoid real sleeping regardless of --interval.
    monkeypatch.setattr(cli_mod.time, "sleep", lambda _s: None)

    rc = cli_mod.main(
        [
            "--config",
            str(_REAL_CONFIG),
            "watch",
            "--dir",
            str(watch_dir),
            "--interval",
            "0",
            "--iterations",
            "2",
        ]
    )

    assert rc == 0
    # Both files processed once (mtime cache suppresses 2nd loop iteration).
    assert len(ingest_calls) == 2
    assert {p.name for p in ingest_calls} == {"ch001.txt", "ch002.txt"}


def test_rebuild_with_yes_and_book_filters_jsonl_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # chunks_raw.jsonl: 2 books × 2 rows — keep only non-target book rows.
    raw_path = data_dir / "chunks_raw.jsonl"
    raw_path.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {"chunk_id": "c1", "source_book": "诡秘之主", "source_chapter": "ch001"},
                {"chunk_id": "c2", "source_book": "诡秘之主", "source_chapter": "ch002"},
                {"chunk_id": "c3", "source_book": "另一本书", "source_chapter": "ch001"},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    # failures.jsonl must be left untouched (per AC: only 3 jsonl are filtered).
    failures_path = data_dir / "failures.jsonl"
    failures_path.write_text("{\"book\": \"诡秘之主\"}\n", encoding="utf-8")

    qdrant_mock = MagicMock(
        side_effect=AssertionError("per-book rebuild must not touch collection")
    )
    ingest_mock = MagicMock(return_value=0)

    monkeypatch.setattr(cli_mod, "DEFAULT_DATA_DIR", data_dir)
    monkeypatch.setattr(cli_mod, "_build_qdrant_client", qdrant_mock)
    monkeypatch.setattr(cli_mod, "_cmd_ingest", ingest_mock)

    rc = cli_mod.main(
        ["--config", str(_REAL_CONFIG), "rebuild", "--yes", "--book", "诡秘之主"]
    )

    assert rc == 0
    # Only non-target book rows remain.
    remaining = [
        json.loads(line)
        for line in raw_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(remaining) == 1
    assert remaining[0]["source_book"] == "另一本书"
    # failures.jsonl was not touched.
    assert failures_path.read_text(encoding="utf-8") == '{"book": "诡秘之主"}\n'
    # No Qdrant client was built (side_effect would have fired).
    assert qdrant_mock.call_count == 0
    # Per-book re-ingest still runs.
    assert ingest_mock.call_count == 1
