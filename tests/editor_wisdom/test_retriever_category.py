"""Tests for category-filtered retrieval correctness and score ordering."""

from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np
import pytest
from sentence_transformers import SentenceTransformer

from ink_writer.editor_wisdom.retriever import Retriever, Rule

MODEL_NAME = "BAAI/bge-small-zh-v1.5"

CATEGORIES = [
    "opening", "hook", "character", "pacing", "taboo",
    "dialogue", "conflict", "worldbuild", "emotion", "foreshadow",
]

RULES_PER_CAT = 3


def _build_rules() -> list[dict]:
    rules = []
    idx = 0
    for cat in CATEGORIES:
        for j in range(RULES_PER_CAT):
            idx += 1
            rules.append({
                "id": f"EW-{idx:04d}",
                "category": cat,
                "rule": f"{cat} rule {j}: 关于{cat}的写作技巧第{j}条",
                "why": f"因为{cat}很重要 — 条目{j}",
                "severity": ["hard", "soft", "info"][j % 3],
                "applies_to": ["all_chapters"],
                "source_files": [f"src_{cat}_{j}.md"],
            })
    return rules


@pytest.fixture(scope="module")
def index_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("cat_index")
    rules = _build_rules()

    model = SentenceTransformer(MODEL_NAME)
    texts = [f"{r['rule']} {r['why']}" for r in rules]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    embeddings = np.array(embeddings, dtype=np.float32)

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    faiss.write_index(index, str(d / "rules.faiss"))

    (d / "metadata.json").write_text(
        json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return d


@pytest.fixture(scope="module")
def retriever(index_dir: Path) -> Retriever:
    return Retriever(index_dir)


def test_category_filter_returns_only_target(retriever: Retriever) -> None:
    results = retriever.retrieve(query="opening tips", category="taboo", k=3)
    assert len(results) == 3
    assert all(r.category == "taboo" for r in results)


def test_category_filter_scores_descending(retriever: Retriever) -> None:
    results = retriever.retrieve(query="opening tips", category="taboo", k=3)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_category_filter_all_have_scores(retriever: Retriever) -> None:
    results = retriever.retrieve(query="写作", category="opening", k=3)
    for r in results:
        assert isinstance(r.score, float)
        assert r.score != 0.0


def test_unfiltered_also_has_scores(retriever: Retriever) -> None:
    results = retriever.retrieve(query="写作技巧", k=5)
    for r in results:
        assert isinstance(r.score, float)


def test_category_k_exceeds_available(retriever: Retriever) -> None:
    results = retriever.retrieve(query="写作", category="opening", k=100)
    assert len(results) == RULES_PER_CAT
    assert all(r.category == "opening" for r in results)


def test_nonexistent_category_returns_empty(retriever: Retriever) -> None:
    results = retriever.retrieve(query="anything", category="does_not_exist", k=3)
    assert results == []
