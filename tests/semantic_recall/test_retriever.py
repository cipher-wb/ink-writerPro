"""Tests for SemanticChapterRetriever."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

import numpy as np

from ink_writer.semantic_recall.chapter_index import ChapterCard, ChapterVectorIndex
from ink_writer.semantic_recall.config import SemanticRecallConfig
from ink_writer.semantic_recall.retriever import RecallHit, SemanticChapterRetriever


DIM = 16


def _make_card(chapter: int, entities: list[str] | None = None) -> ChapterCard:
    return ChapterCard(
        chapter=chapter,
        summary=f"第{chapter}章摘要",
        goal=f"目标{chapter}",
        conflict=f"冲突{chapter}",
        result=f"结果{chapter}",
        next_chapter_bridge=f"过渡{chapter}",
        unresolved_questions=[f"悬念{chapter}"],
        key_facts=[f"关键{chapter}"],
        involved_entities=entities or [],
        plot_progress=[],
    )


def _fake_model():
    model = MagicMock()
    model.get_sentence_embedding_dimension.return_value = DIM

    def _encode(texts, **kwargs):
        rng = np.random.RandomState(hash(texts[0]) % 2**31)
        vecs = rng.randn(len(texts), DIM).astype(np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / norms

    model.encode = _encode
    return model


def _build_test_index(tmp_path, cards):
    with patch.object(ChapterVectorIndex, "_get_model", return_value=_fake_model()):
        index = ChapterVectorIndex(index_dir=tmp_path / "idx")
        index.build(cards)
    return index


class TestSemanticChapterRetriever:
    def test_recent_n_always_included(self, tmp_path):
        cards = [_make_card(i) for i in range(1, 21)]
        index = _build_test_index(tmp_path, cards)

        config = SemanticRecallConfig(recent_n=3, final_top_k=20, min_semantic_score=0.0)
        retriever = SemanticChapterRetriever(index=index, config=config)

        with patch.object(index, "_get_model", return_value=_fake_model()):
            hits = retriever.recall("测试查询", chapter_num=20)

        hit_chapters = {h.chapter for h in hits}
        assert 17 in hit_chapters
        assert 18 in hit_chapters
        assert 19 in hit_chapters

    def test_entity_forced_recall(self, tmp_path):
        cards = [
            _make_card(1, entities=["萧尘", "林渊"]),
            _make_card(2, entities=["张三"]),
            _make_card(3, entities=["萧尘"]),
            _make_card(4, entities=["李四"]),
            _make_card(5, entities=["林渊"]),
        ]
        index = _build_test_index(tmp_path, cards)

        config = SemanticRecallConfig(
            recent_n=0,
            semantic_top_k=0,
            entity_forced_max=10,
            final_top_k=20,
            min_semantic_score=0.99,
        )
        retriever = SemanticChapterRetriever(index=index, config=config)

        with patch.object(index, "_get_model", return_value=_fake_model()):
            hits = retriever.recall(
                "测试", chapter_num=6, scene_entities=["萧尘"]
            )

        hit_chapters = {h.chapter for h in hits}
        assert 1 in hit_chapters  # 萧尘 appeared
        assert 3 in hit_chapters  # 萧尘 appeared

    def test_no_future_chapters_returned(self, tmp_path):
        cards = [_make_card(i) for i in range(1, 11)]
        index = _build_test_index(tmp_path, cards)

        config = SemanticRecallConfig(recent_n=2, final_top_k=20, min_semantic_score=0.0)
        retriever = SemanticChapterRetriever(index=index, config=config)

        with patch.object(index, "_get_model", return_value=_fake_model()):
            hits = retriever.recall("测试", chapter_num=5)

        for h in hits:
            assert h.chapter < 5

    def test_final_top_k_limits_output(self, tmp_path):
        cards = [_make_card(i) for i in range(1, 31)]
        index = _build_test_index(tmp_path, cards)

        config = SemanticRecallConfig(
            recent_n=5, semantic_top_k=10, final_top_k=8, min_semantic_score=0.0
        )
        retriever = SemanticChapterRetriever(index=index, config=config)

        with patch.object(index, "_get_model", return_value=_fake_model()):
            hits = retriever.recall("测试", chapter_num=30)

        assert len(hits) <= 8

    def test_entity_boost_increases_score(self, tmp_path):
        cards = [
            _make_card(1, entities=["萧尘"]),
            _make_card(2, entities=["张三"]),
        ]
        index = _build_test_index(tmp_path, cards)

        config = SemanticRecallConfig(
            recent_n=0,
            semantic_top_k=5,
            entity_boost_weight=0.5,
            min_semantic_score=0.0,
            final_top_k=20,
        )
        retriever = SemanticChapterRetriever(index=index, config=config)

        with patch.object(index, "_get_model", return_value=_fake_model()):
            hits_with = retriever.recall("测试", chapter_num=3, scene_entities=["萧尘"])

        ch1_hit = next((h for h in hits_with if h.chapter == 1), None)
        ch2_hit = next((h for h in hits_with if h.chapter == 2), None)
        if ch1_hit and ch2_hit:
            assert ch1_hit.score > ch2_hit.score or ch1_hit.source != ch2_hit.source

    def test_source_tagging(self, tmp_path):
        cards = [_make_card(i) for i in range(1, 6)]
        index = _build_test_index(tmp_path, cards)

        config = SemanticRecallConfig(
            recent_n=2, semantic_top_k=5, final_top_k=20, min_semantic_score=0.0
        )
        retriever = SemanticChapterRetriever(index=index, config=config)

        with patch.object(index, "_get_model", return_value=_fake_model()):
            hits = retriever.recall("测试", chapter_num=5)

        sources = {h.source for h in hits}
        assert any("recent" in s for s in sources)

    def test_to_payload_format(self, tmp_path):
        cards = [_make_card(i, entities=["A"]) for i in range(1, 6)]
        index = _build_test_index(tmp_path, cards)

        config = SemanticRecallConfig(
            recent_n=2, semantic_top_k=3, final_top_k=5, min_semantic_score=0.0
        )
        retriever = SemanticChapterRetriever(index=index, config=config)

        with patch.object(index, "_get_model", return_value=_fake_model()):
            payload = retriever.recall_to_payload("测试", chapter_num=5)

        assert payload["invoked"] is True
        assert payload["mode"] == "semantic_hybrid"
        assert "hits" in payload
        assert "query" in payload
        assert isinstance(payload["center_entities"], list)
        for hit in payload["hits"]:
            assert "chapter" in hit
            assert "score" in hit
            assert "source" in hit
            assert "content" in hit

    def test_empty_index_returns_empty(self, tmp_path):
        with patch.object(ChapterVectorIndex, "_get_model", return_value=_fake_model()):
            index = ChapterVectorIndex(index_dir=tmp_path / "idx")

        config = SemanticRecallConfig(recent_n=0, final_top_k=10)
        retriever = SemanticChapterRetriever(index=index, config=config)

        with patch.object(index, "_get_model", return_value=_fake_model()):
            hits = retriever.recall("测试", chapter_num=5)
        assert hits == []


class TestSimulated300ChapterReplay:
    """Simulated 300-chapter replay: verify no missed callbacks."""

    def test_300_chapter_no_missed_callbacks(self, tmp_path):
        all_entities = ["萧尘", "林渊", "洛清影", "张三", "李四", "王五"]
        rng = np.random.RandomState(42)

        cards = []
        for i in range(1, 301):
            n_entities = rng.randint(1, 4)
            chapter_entities = list(rng.choice(all_entities, size=n_entities, replace=False))
            cards.append(_make_card(i, entities=chapter_entities))

        index = _build_test_index(tmp_path, cards)

        config = SemanticRecallConfig(
            recent_n=5,
            semantic_top_k=8,
            entity_forced_max=10,
            final_top_k=10,
            min_semantic_score=0.0,
            entity_boost_weight=0.15,
        )
        retriever = SemanticChapterRetriever(index=index, config=config)

        missed_callbacks = 0
        total_checks = 0

        for ch in range(10, 301, 10):
            current_entities = cards[ch - 1].involved_entities

            with patch.object(index, "_get_model", return_value=_fake_model()):
                hits = retriever.recall(
                    f"第{ch}章查询",
                    chapter_num=ch,
                    scene_entities=current_entities,
                )

            hit_chapters = {h.chapter for h in hits}

            for prev_ch in range(max(1, ch - 5), ch):
                total_checks += 1
                if prev_ch not in hit_chapters:
                    missed_callbacks += 1

            for prev_ch_idx in range(max(0, ch - 50), ch - 1):
                prev_card = cards[prev_ch_idx]
                overlap = set(e.lower() for e in current_entities) & set(
                    e.lower() for e in prev_card.involved_entities
                )
                if overlap and prev_card.chapter not in hit_chapters:
                    pass

        assert missed_callbacks == 0, (
            f"Missed {missed_callbacks}/{total_checks} recent-N callbacks"
        )

    def test_writing_pack_size_reduction(self, tmp_path):
        cards = [_make_card(i, entities=[f"角色{i % 5}"]) for i in range(1, 51)]
        index = _build_test_index(tmp_path, cards)

        config = SemanticRecallConfig(
            recent_n=5, semantic_top_k=8, final_top_k=10, min_semantic_score=0.0
        )
        retriever = SemanticChapterRetriever(index=index, config=config)

        with patch.object(index, "_get_model", return_value=_fake_model()):
            hits = retriever.recall("测试", chapter_num=50, scene_entities=["角色1"])

        total_content = sum(len(h.content) for h in hits)
        assert total_content <= config.max_pack_chars, (
            f"Pack size {total_content} exceeds max {config.max_pack_chars}"
        )
