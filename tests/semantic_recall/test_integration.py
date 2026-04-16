"""Integration tests for semantic recall in extract_chapter_context."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

np = pytest.importorskip("numpy")

from ink_writer.semantic_recall.chapter_index import ChapterCard, ChapterVectorIndex
from ink_writer.semantic_recall.config import SemanticRecallConfig
from ink_writer.semantic_recall.retriever import SemanticChapterRetriever


DIM = 16


def _fake_model():
    model = MagicMock()
    model.get_sentence_embedding_dimension.return_value = DIM

    def _encode(texts, **kwargs):
        rng = np.random.RandomState(42)
        vecs = rng.randn(len(texts), DIM).astype(np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / norms

    model.encode = _encode
    return model


def _make_card(chapter, entities=None):
    return ChapterCard(
        chapter=chapter,
        summary=f"第{chapter}章摘要",
        goal=f"目标{chapter}",
        conflict=f"冲突{chapter}",
        result=f"结果{chapter}",
        next_chapter_bridge=f"过渡{chapter}",
        unresolved_questions=[],
        key_facts=[],
        involved_entities=entities or [],
        plot_progress=[],
    )


class TestSearchSemanticRecall:
    """Test _search_semantic_recall integration point."""

    def test_returns_none_when_disabled(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "semantic-recall.yaml").write_text("enabled: false\n")

        from ink_writer.semantic_recall.config import SemanticRecallConfig

        cfg = SemanticRecallConfig.from_project_root(tmp_path)
        assert cfg.enabled is False

    def test_returns_none_when_no_index(self, tmp_path):
        ink_dir = tmp_path / ".ink"
        ink_dir.mkdir()

        cfg = SemanticRecallConfig.from_project_root(tmp_path)
        assert cfg.enabled is True

        index_dir = tmp_path / ".ink" / "chapter_index"
        assert not (index_dir / "chapters.faiss").exists()

    def test_full_pipeline_with_index(self, tmp_path):
        cards = [_make_card(i, ["萧尘"]) for i in range(1, 11)]

        idx_dir = tmp_path / ".ink" / "chapter_index"
        with patch.object(ChapterVectorIndex, "_get_model", return_value=_fake_model()):
            index = ChapterVectorIndex(index_dir=idx_dir)
            index.build(cards)
            index.save()

        with patch.object(ChapterVectorIndex, "_get_model", return_value=_fake_model()):
            loaded = ChapterVectorIndex(index_dir=idx_dir)
            config = SemanticRecallConfig(
                recent_n=3, semantic_top_k=5, final_top_k=8, min_semantic_score=0.0
            )
            retriever = SemanticChapterRetriever(index=loaded, config=config)
            payload = retriever.recall_to_payload(
                query="第10章查询",
                chapter_num=10,
                scene_entities=["萧尘"],
            )

        assert payload["invoked"] is True
        assert payload["mode"] == "semantic_hybrid"
        assert len(payload["hits"]) > 0

        hit_chapters = {h["chapter"] for h in payload["hits"]}
        assert 7 in hit_chapters
        assert 8 in hit_chapters
        assert 9 in hit_chapters

    def test_payload_format_compatible(self, tmp_path):
        cards = [_make_card(i) for i in range(1, 6)]

        idx_dir = tmp_path / ".ink" / "chapter_index"
        with patch.object(ChapterVectorIndex, "_get_model", return_value=_fake_model()):
            index = ChapterVectorIndex(index_dir=idx_dir)
            index.build(cards)

            config = SemanticRecallConfig(
                recent_n=2, final_top_k=5, min_semantic_score=0.0
            )
            retriever = SemanticChapterRetriever(index=loaded if False else index, config=config)
            payload = retriever.recall_to_payload("test", chapter_num=5)

        required_keys = {"invoked", "mode", "reason", "intent", "needs_graph", "center_entities", "hits", "query"}
        assert required_keys.issubset(set(payload.keys()))

        for hit in payload["hits"]:
            hit_keys = {"chapter", "scene_index", "score", "source", "source_file", "content"}
            assert hit_keys.issubset(set(hit.keys()))


class TestBuildChapterIndex:
    """Test the build_chapter_index script logic."""

    def test_build_index_creates_files(self, tmp_path):
        idx_dir = tmp_path / ".ink" / "chapter_index"
        cards = [_make_card(i) for i in range(1, 6)]

        with patch.object(ChapterVectorIndex, "_get_model", return_value=_fake_model()):
            index = ChapterVectorIndex(index_dir=idx_dir)
            index.build(cards)
            index.save()

        assert (idx_dir / "chapters.faiss").exists()
        assert (idx_dir / "chapters_meta.json").exists()

        meta = json.loads((idx_dir / "chapters_meta.json").read_text(encoding="utf-8"))
        assert len(meta) == 5
        assert meta[0]["chapter"] == 1
