"""Tests for ChapterVectorIndex."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from ink_writer.semantic_recall.chapter_index import ChapterCard, ChapterVectorIndex


def _make_card(chapter: int, summary: str = "", entities: list[str] | None = None) -> ChapterCard:
    return ChapterCard(
        chapter=chapter,
        summary=summary or f"第{chapter}章摘要",
        goal=f"目标{chapter}",
        conflict=f"冲突{chapter}",
        result=f"结果{chapter}",
        next_chapter_bridge=f"过渡{chapter}",
        unresolved_questions=[f"悬念{chapter}"],
        key_facts=[f"关键{chapter}"],
        involved_entities=entities or [f"角色{chapter}"],
        plot_progress=[f"推进{chapter}"],
    )


class TestChapterCard:
    def test_to_embed_text(self):
        card = _make_card(1, "主角遭遇危机", ["萧尘", "林渊"])
        text = card.to_embed_text()
        assert "第1章" in text
        assert "主角遭遇危机" in text
        assert "目标1" in text

    def test_from_db_row(self):
        row = {
            "chapter": 5,
            "summary": "test",
            "goal": "g",
            "conflict": "c",
            "result": "r",
            "next_chapter_bridge": "b",
            "unresolved_questions": json.dumps(["q1"]),
            "key_facts": ["f1", "f2"],
            "involved_entities": json.dumps(["e1"]),
            "plot_progress": [],
        }
        card = ChapterCard.from_db_row(row)
        assert card.chapter == 5
        assert card.summary == "test"
        assert card.unresolved_questions == ["q1"]
        assert card.key_facts == ["f1", "f2"]
        assert card.involved_entities == ["e1"]

    def test_from_db_row_empty(self):
        card = ChapterCard.from_db_row({})
        assert card.chapter == 0
        assert card.summary == ""
        assert card.involved_entities == []


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


class TestChapterVectorIndexBuild:
    @patch("ink_writer.semantic_recall.chapter_index.ChapterVectorIndex._get_model")
    def test_build_and_search(self, mock_get_model, tmp_path):
        mock_get_model.return_value = _fake_model()
        index = ChapterVectorIndex(index_dir=tmp_path / "idx")
        cards = [_make_card(i) for i in range(1, 21)]
        index.build(cards)
        assert index.card_count == 20

        results = index.search("测试查询", k=5)
        assert len(results) <= 5
        assert all(isinstance(r[0], ChapterCard) for r in results)
        assert all(isinstance(r[1], float) for r in results)

    @patch("ink_writer.semantic_recall.chapter_index.ChapterVectorIndex._get_model")
    def test_search_before_chapter(self, mock_get_model, tmp_path):
        mock_get_model.return_value = _fake_model()
        index = ChapterVectorIndex(index_dir=tmp_path / "idx")
        cards = [_make_card(i) for i in range(1, 11)]
        index.build(cards)

        results = index.search("测试", k=5, before_chapter=5)
        chapters = [card.chapter for card, _ in results]
        assert all(ch < 5 for ch in chapters)

    @patch("ink_writer.semantic_recall.chapter_index.ChapterVectorIndex._get_model")
    def test_search_empty_index(self, mock_get_model, tmp_path):
        mock_get_model.return_value = _fake_model()
        index = ChapterVectorIndex(index_dir=tmp_path / "idx")
        results = index.search("test", k=5)
        assert results == []

    @patch("ink_writer.semantic_recall.chapter_index.ChapterVectorIndex._get_model")
    def test_save_and_load(self, mock_get_model, tmp_path):
        mock_get_model.return_value = _fake_model()
        idx_dir = tmp_path / "idx"
        index = ChapterVectorIndex(index_dir=idx_dir)
        cards = [_make_card(i) for i in range(1, 6)]
        index.build(cards)
        index.save()

        assert (idx_dir / "chapters.faiss").exists()
        assert (idx_dir / "chapters_meta.json").exists()

        loaded = ChapterVectorIndex(index_dir=idx_dir)
        loaded._model = _fake_model()
        assert loaded.card_count == 5
        assert loaded.get_card(3) is not None
        assert loaded.get_card(3).chapter == 3

    @patch("ink_writer.semantic_recall.chapter_index.ChapterVectorIndex._get_model")
    def test_add_chapter_incremental(self, mock_get_model, tmp_path):
        mock_get_model.return_value = _fake_model()
        index = ChapterVectorIndex(index_dir=tmp_path / "idx")
        cards = [_make_card(i) for i in range(1, 4)]
        index.build(cards)
        assert index.card_count == 3

        index.add_chapter(_make_card(4))
        assert index.card_count == 4
        assert index.get_card(4) is not None

    @patch("ink_writer.semantic_recall.chapter_index.ChapterVectorIndex._get_model")
    def test_get_cards_for_chapters(self, mock_get_model, tmp_path):
        mock_get_model.return_value = _fake_model()
        index = ChapterVectorIndex(index_dir=tmp_path / "idx")
        cards = [_make_card(i) for i in range(1, 11)]
        index.build(cards)

        result = index.get_cards_for_chapters([2, 5, 8])
        assert len(result) == 3
        assert [c.chapter for c in result] == [2, 5, 8]

    @patch("ink_writer.semantic_recall.chapter_index.ChapterVectorIndex._get_model")
    def test_get_cards_for_missing_chapters(self, mock_get_model, tmp_path):
        mock_get_model.return_value = _fake_model()
        index = ChapterVectorIndex(index_dir=tmp_path / "idx")
        cards = [_make_card(i) for i in range(1, 4)]
        index.build(cards)

        result = index.get_cards_for_chapters([1, 99])
        assert len(result) == 1
        assert result[0].chapter == 1
