"""US-LR-011 Tests for vector index build + retrieval (genre semantic search).

bge-small-zh-v1.5 模型加载 ~30s — 用 module-scoped fixture 共享 index_dir 与构建产物。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_30_CASES = FIXTURES_DIR / "sample_30_cases"


@pytest.fixture(scope="module")
def vector_index_dir(tmp_path_factory) -> Path:
    """Build vector index from sample_30_cases once for the whole module."""
    from ink_writer.live_review._vector_index import build_index

    out_dir = tmp_path_factory.mktemp("vector_index_30")
    build_index(SAMPLE_30_CASES, out_dir)
    return out_dir


def test_build_index_creates_faiss_and_meta(vector_index_dir: Path) -> None:
    assert (vector_index_dir / "index.faiss").exists(), "index.faiss should be built"
    meta_path = vector_index_dir / "meta.jsonl"
    assert meta_path.exists(), "meta.jsonl should be built"
    lines = meta_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 30, f"expected 30 meta lines, got {len(lines)}"
    record = json.loads(lines[0])
    for field in ("case_id", "title_guess", "genre_guess", "overall_comment", "embedding_text"):
        assert field in record, f"meta record missing field {field}"


def test_build_and_retrieve(vector_index_dir: Path) -> None:
    """Query '都市重生律师' should hit cases tagged 都市/重生 in top-3."""
    from ink_writer.live_review._vector_index import load_index, search

    index_data = load_index(vector_index_dir)
    results = search(index_data, "都市重生律师文案", top_k=3)
    assert len(results) == 3
    case_ids = [r["case_id"] for r in results]
    # 0001-0004 are 都市,重生 cases — at least one should be in top 3
    overlap = set(case_ids) & {f"CASE-LR-2026-{i:04d}" for i in (1, 2, 3, 4, 8)}
    assert len(overlap) >= 1, f"expected at least one 都市/重生 hit in top-3, got {case_ids}"


def test_cosine_sim_monotonic(vector_index_dir: Path) -> None:
    """search results must be sorted by cosine_sim descending."""
    from ink_writer.live_review._vector_index import load_index, search

    index_data = load_index(vector_index_dir)
    results = search(index_data, "玄幻无敌流爽文", top_k=5)
    sims = [r["cosine_sim"] for r in results]
    assert sims == sorted(sims, reverse=True), f"cosine_sim not monotonically descending: {sims}"


def test_retrieve_similar_cases_uses_default_index_dir(
    monkeypatch, vector_index_dir: Path
) -> None:
    """genre_retrieval.retrieve_similar_cases reads from configured index_dir."""
    from ink_writer.live_review import genre_retrieval

    cases = genre_retrieval.retrieve_similar_cases(
        "都市重生", top_k=3, index_dir=vector_index_dir
    )
    assert len(cases) == 3
    for c in cases:
        for field in ("case_id", "title_guess", "verdict", "cosine_sim"):
            assert field in c, f"missing field {field} in retrieved case"
        assert c["case_id"].startswith("CASE-LR-2026-")


def test_retrieve_similar_cases_raises_on_missing_index(tmp_path: Path) -> None:
    from ink_writer.live_review import genre_retrieval

    nonexistent = tmp_path / "no_index_here"
    with pytest.raises(FileNotFoundError, match="build_vector_index"):
        genre_retrieval.retrieve_similar_cases("query", top_k=3, index_dir=nonexistent)
