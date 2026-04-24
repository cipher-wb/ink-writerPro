"""M2 end-to-end integration (US-012).

Five scenarios covering spec §6.2 acceptance:

1. ``test_rules_conversion_creates_402_cases_with_severity_split`` — real v23
   ``data/editor-wisdom/rules.json`` (skipped if missing) goes through
   ``convert_rules_to_cases`` end-to-end; verifies created=402 +
   by_severity={hard:236, soft:147, info:19}.
2. ``test_active_pending_counts_after_conversion`` — same real rules.json,
   verifies active=236 (hard→P1 active) + pending=166 (soft+info).
3. ``test_approve_batch_yaml_changes_status`` — ingest 5 pending cases,
   write a batch YAML with mixed approve/reject/defer actions, assert each
   case status transitioned correctly.
4. ``test_corpus_ingest_resume_skips_indexed_chapters`` — directly exercises
   ``_already_indexed`` helper (PRD-permitted shortcut for resume logic).
5. ``test_chunking_pipeline_e2e_with_one_chapter_mocked`` — in-memory Qdrant
   (8-dim test collection), mocked anthropic + embedder, one chapter →
   segment → tag → index → points_count == 1.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from ink_writer.case_library.ingest import ingest_case
from ink_writer.case_library.rules_to_cases import convert_rules_to_cases
from ink_writer.case_library.store import CaseStore

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_RULES_PATH = _REPO_ROOT / "data" / "editor-wisdom" / "rules.json"


# ---------------------------------------------------------------------------
# 1) rules.json → 402 cases split by severity
# ---------------------------------------------------------------------------


def test_rules_conversion_creates_402_cases_with_severity_split(
    tmp_path: Path,
) -> None:
    if not _REAL_RULES_PATH.exists():
        pytest.skip(f"real rules.json missing: {_REAL_RULES_PATH}")

    library_root = tmp_path / "lib"
    report = convert_rules_to_cases(
        rules_path=_REAL_RULES_PATH,
        library_root=library_root,
        dry_run=False,
    )

    assert report.failed == 0, report.failures[:5]
    assert report.created == 402, report
    assert report.by_severity == {"hard": 236, "soft": 147, "info": 19}, (
        report.by_severity
    )


# ---------------------------------------------------------------------------
# 2) active / pending counts after the conversion
# ---------------------------------------------------------------------------


def test_active_pending_counts_after_conversion(tmp_path: Path) -> None:
    if not _REAL_RULES_PATH.exists():
        pytest.skip(f"real rules.json missing: {_REAL_RULES_PATH}")

    library_root = tmp_path / "lib"
    convert_rules_to_cases(
        rules_path=_REAL_RULES_PATH,
        library_root=library_root,
        dry_run=False,
    )

    store = CaseStore(library_root)
    by_status: dict[str, int] = {}
    for case in store.iter_cases():
        by_status[case.status.value] = by_status.get(case.status.value, 0) + 1

    # hard → active P1 = 236; soft (147) + info (19) = 166 pending.
    assert by_status.get("active") == 236, by_status
    assert by_status.get("pending") == 166, by_status


# ---------------------------------------------------------------------------
# 3) approve --batch transitions 5 cases with mixed actions
# ---------------------------------------------------------------------------


def _make_pending(store: CaseStore, *, n: int, title_prefix: str) -> list[str]:
    ids: list[str] = []
    for i in range(n):
        result = ingest_case(
            store,
            title=f"{title_prefix}-{i}",
            raw_text=f"raw-{title_prefix}-{i} | why-{i}",
            domain="writing_quality",
            layer=["downstream"],
            severity="P2",
            tags=["from_editor_wisdom", "opening"],
            source_type="editor_review",
            ingested_at="2026-04-24",
            failure_description=f"desc {title_prefix}-{i}",
            observable=[f"placeholder {title_prefix}-{i}"],
            initial_status="pending",
        )
        assert result.created, f"expected fresh create for {title_prefix}-{i}"
        ids.append(result.case_id)
    return ids


def test_approve_batch_yaml_changes_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from ink_writer.case_library.cli import main as case_cli_main

    library_root = tmp_path / "lib"
    store = CaseStore(library_root)
    ids = _make_pending(store, n=5, title_prefix="e2e")

    # 5 cases, each action covered: approve / reject / defer / approve / reject.
    approvals = [
        {"case_id": ids[0], "action": "approve"},
        {"case_id": ids[1], "action": "reject", "note": "unclear"},
        {"case_id": ids[2], "action": "defer", "note": "revisit in M3"},
        {"case_id": ids[3], "action": "approve", "note": "hard rule"},
        {"case_id": ids[4], "action": "reject"},
    ]
    batch_path = tmp_path / "batch.yaml"
    batch_path.write_text(
        yaml.safe_dump({"approvals": approvals}, allow_unicode=True),
        encoding="utf-8",
    )

    rc = case_cli_main(
        [
            "--library-root",
            str(library_root),
            "approve",
            "--batch",
            str(batch_path),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "applied=5" in out
    assert "failed=0" in out

    expected = {
        ids[0]: "active",
        ids[1]: "retired",
        ids[2]: "pending",
        ids[3]: "active",
        ids[4]: "retired",
    }
    for case_id, want in expected.items():
        assert store.load(case_id).status.value == want, (
            f"{case_id} expected {want}, got {store.load(case_id).status.value}"
        )


# ---------------------------------------------------------------------------
# 4) corpus ingest resume helper
# ---------------------------------------------------------------------------


def test_corpus_ingest_resume_skips_indexed_chapters(tmp_path: Path) -> None:
    from scripts.corpus_chunking import cli as cli_mod

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
    assert cli_mod._already_indexed("x", "y", tmp_path / "nope.jsonl") is False


# ---------------------------------------------------------------------------
# 5) chunking pipeline end-to-end with mocked anthropic + embedder
# ---------------------------------------------------------------------------


def _build_segmenter_response_text() -> str:
    """Return a JSON payload mimicking what Haiku produces for 1 chunk."""
    return json.dumps(
        {
            "chunks": [
                {
                    "scene_type": "opening",
                    "char_range": [0, 60],
                    "text": "克莱恩在旧货市场翻找着那本魔药配方手册。" * 3,
                }
            ]
        },
        ensure_ascii=False,
    )


def _build_tagger_response_text() -> str:
    """Return a JSON payload mimicking what Haiku produces for 1 tagged chunk."""
    return json.dumps(
        {
            "scene_type": "opening",
            "tension_level": 0.6,
            "character_count": 1,
            "dialogue_ratio": 0.0,
            "hook_type": "setting_intro",
            "borrowable_aspects": ["atmosphere"],
            "quality_breakdown": {
                "tension": 0.7,
                "originality": 0.8,
                "language_density": 0.75,
                "readability": 0.8,
            },
        },
        ensure_ascii=False,
    )


def _make_anthropic_mock() -> MagicMock:
    """One MagicMock routes both segmenter + tagger calls by alternating responses."""
    client = MagicMock()
    seg = MagicMock()
    seg.content = [MagicMock(text=_build_segmenter_response_text())]
    tag = MagicMock()
    tag.content = [MagicMock(text=_build_tagger_response_text())]
    # First call = segmenter, second call = tagger.
    client.messages.create.side_effect = [seg, tag]
    return client


def test_chunking_pipeline_e2e_with_one_chapter_mocked(tmp_path: Path) -> None:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Distance, VectorParams
    from scripts.corpus_chunking.chunk_indexer import IndexerConfig, index_chunks
    from scripts.corpus_chunking.chunk_tagger import TaggerConfig, tag_chunk
    from scripts.corpus_chunking.models import SourceType
    from scripts.corpus_chunking.scene_segmenter import (
        SegmenterConfig,
        segment_chapter,
    )

    # In-memory Qdrant with a tiny 8-dim test collection.
    qd = QdrantClient(":memory:")
    collection_name = "corpus_chunks_test"
    qd.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=8, distance=Distance.COSINE),
    )

    anthropic_client = _make_anthropic_mock()
    embedder = MagicMock()
    embedder.embed_batch = MagicMock(return_value=[[0.1] * 8])

    # Stage 1: segment.
    seg_cfg = SegmenterConfig(
        model="claude-haiku-4-5-20251001",
        min_chunk_chars=20,
        max_chunk_chars=800,
        max_retries=3,
    )
    chapter_text = "克莱恩在旧货市场翻找着那本魔药配方手册。" * 3
    raw_chunks = segment_chapter(
        client=anthropic_client,
        cfg=seg_cfg,
        book="诡秘之主",
        chapter="ch001",
        text=chapter_text,
    )
    assert len(raw_chunks) == 1
    assert raw_chunks[0].source_book == "诡秘之主"

    # Stage 2: tag.
    tag_cfg = TaggerConfig(
        model="claude-haiku-4-5-20251001",
        batch_size=5,
        quality_weights={
            "tension": 0.3,
            "originality": 0.3,
            "language_density": 0.2,
            "readability": 0.2,
        },
        max_retries=3,
    )
    tagged = tag_chunk(
        client=anthropic_client,
        cfg=tag_cfg,
        chunk=raw_chunks[0],
        genre=["异世大陆"],
        ingested_at="2026-04-24",
        source_type=SourceType.BUILTIN,
    )
    assert tagged.scene_type == "opening"
    assert tagged.genre == ["异世大陆"]  # from caller, not LLM.
    assert tagged.quality_score == pytest.approx(
        0.7 * 0.3 + 0.8 * 0.3 + 0.75 * 0.2 + 0.8 * 0.2, rel=1e-9
    )

    # Stage 3: index.
    idx_cfg = IndexerConfig(
        qdrant_collection=collection_name,
        upsert_batch_size=256,
    )
    indexed = index_chunks(
        chunks=[tagged],
        qdrant_client=qd,
        embedder=embedder,
        cfg=idx_cfg,
        metadata_path=tmp_path / "metadata.jsonl",
        unindexed_path=tmp_path / "unindexed.jsonl",
    )
    assert indexed == 1
    assert embedder.embed_batch.call_count == 1
    # The collection now has exactly one point.
    info = qd.get_collection(collection_name)
    assert info.points_count == 1
    # metadata.jsonl backup exists and has one line.
    meta_lines = (
        (tmp_path / "metadata.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(meta_lines) == 1
    row = json.loads(meta_lines[0])
    assert row["source_book"] == "诡秘之主"
    assert row["scene_type"] == "opening"
