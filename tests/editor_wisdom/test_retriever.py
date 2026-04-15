"""Tests for ink_writer/editor_wisdom/retriever.py."""

from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np
import pytest
from ink_writer.editor_wisdom.retriever import Retriever, Rule
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-zh-v1.5"

SAMPLE_RULES = [
    {
        "id": "EW-0001",
        "category": "opening",
        "rule": "开篇第一段必须制造悬念或冲突",
        "why": "读者注意力在前3秒决定是否继续",
        "severity": "hard",
        "applies_to": ["golden_three", "opening"],
        "source_files": ["file1.md"],
    },
    {
        "id": "EW-0002",
        "category": "hook",
        "rule": "每章结尾留下未解悬念",
        "why": "驱动读者翻页",
        "severity": "hard",
        "applies_to": ["all_chapters"],
        "source_files": ["file2.md"],
    },
    {
        "id": "EW-0003",
        "category": "character",
        "rule": "主角在前三章必须展示核心性格特质",
        "why": "帮助读者建立情感连接",
        "severity": "soft",
        "applies_to": ["golden_three", "character"],
        "source_files": ["file3.md"],
    },
    {
        "id": "EW-0004",
        "category": "pacing",
        "rule": "高潮场景后安排短暂喘息",
        "why": "节奏张弛有度避免疲劳",
        "severity": "soft",
        "applies_to": ["all_chapters"],
        "source_files": ["file4.md"],
    },
    {
        "id": "EW-0005",
        "category": "opening",
        "rule": "避免以大段世界观设定开头",
        "why": "信息灌输会劝退读者",
        "severity": "hard",
        "applies_to": ["golden_three", "opening"],
        "source_files": ["file5.md"],
    },
    {
        "id": "EW-0006",
        "category": "taboo",
        "rule": "不要在对话中使用过多语气词",
        "why": "语气词过多显得不专业",
        "severity": "info",
        "applies_to": ["all_chapters"],
        "source_files": ["file6.md"],
    },
]


@pytest.fixture(scope="module")
def index_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a real FAISS index from sample rules."""
    d = tmp_path_factory.mktemp("vector_index")

    model = SentenceTransformer(MODEL_NAME)
    texts = [f"{r['rule']} {r['why']}" for r in SAMPLE_RULES]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    embeddings = np.array(embeddings, dtype=np.float32)

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    faiss.write_index(index, str(d / "rules.faiss"))

    (d / "metadata.json").write_text(
        json.dumps(SAMPLE_RULES, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return d


@pytest.fixture(scope="module")
def retriever(index_dir: Path) -> Retriever:
    return Retriever(index_dir)


def test_retrieve_returns_rules(retriever: Retriever) -> None:
    results = retriever.retrieve("开篇悬念", k=3)
    assert len(results) <= 3
    assert all(isinstance(r, Rule) for r in results)


def test_retrieve_k_limit(retriever: Retriever) -> None:
    results = retriever.retrieve("写作", k=2)
    assert len(results) <= 2


def test_retrieve_category_filter(retriever: Retriever) -> None:
    results = retriever.retrieve("开头", k=10, category="opening")
    assert len(results) > 0
    assert all(r.category == "opening" for r in results)


def test_retrieve_category_filter_no_match(retriever: Retriever) -> None:
    results = retriever.retrieve("开头", k=5, category="nonexistent_category")
    assert results == []


def test_retrieve_returns_all_fields(retriever: Retriever) -> None:
    results = retriever.retrieve("悬念", k=1)
    assert len(results) == 1
    r = results[0]
    assert r.id.startswith("EW-")
    assert r.category in ["opening", "hook", "character", "pacing", "taboo"]
    assert len(r.rule) > 0
    assert len(r.why) > 0
    assert r.severity in ["hard", "soft", "info"]
    assert isinstance(r.applies_to, list)
    assert isinstance(r.source_files, list)


def test_retrieve_relevance(retriever: Retriever) -> None:
    """Top result for opening-related query should be an opening rule."""
    results = retriever.retrieve("第一段要制造冲突和悬念", k=1)
    assert len(results) == 1
    assert results[0].category == "opening"


def test_retrieve_full_k(retriever: Retriever) -> None:
    results = retriever.retrieve("写作技巧", k=6)
    assert len(results) == 6
    ids = [r.id for r in results]
    assert len(set(ids)) == 6
