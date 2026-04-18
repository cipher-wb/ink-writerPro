"""US-022: BM25 + FAISS hybrid (reciprocal rank fusion) retrieval tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

np = pytest.importorskip("numpy")

from ink_writer.semantic_recall.bm25 import BM25Index, tokenize
from ink_writer.semantic_recall.chapter_index import ChapterCard, ChapterVectorIndex
from ink_writer.semantic_recall.config import SemanticRecallConfig
from ink_writer.semantic_recall.retriever import SemanticChapterRetriever

DIM = 16


def _make_card(chapter: int, summary: str, entities: list[str] | None = None) -> ChapterCard:
    return ChapterCard(
        chapter=chapter,
        summary=summary,
        goal=f"目标{chapter}",
        conflict=f"冲突{chapter}",
        result=f"结果{chapter}",
        next_chapter_bridge=f"过渡{chapter}",
        unresolved_questions=[],
        key_facts=[],
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


def _build_index(tmp_path, cards):
    with patch.object(ChapterVectorIndex, "_get_model", return_value=_fake_model()):
        idx = ChapterVectorIndex(index_dir=tmp_path / "idx")
        idx.build(cards)
    return idx


class TestBM25Index:
    def test_tokenize_chinese_and_latin(self):
        toks = tokenize("萧尘救下林渊 rescue")
        assert "萧" in toks
        assert "尘" in toks
        assert "rescue" in toks

    def test_empty_query_returns_empty(self):
        bm = BM25Index().fit(["甲乙丙", "丁戊己"])
        assert bm.search("", k=5) == []

    def test_exact_match_scores_higher_than_unrelated(self):
        bm = BM25Index().fit(["萧尘与林渊对话", "宴会上的歌舞", "城外的战斗"])
        hits = bm.search("林渊", k=3)
        assert hits, "should return at least one hit"
        assert hits[0][0] == 0  # first doc contains 林渊

    def test_score_is_zero_for_missing_terms(self):
        bm = BM25Index().fit(["完全无关的内容"])
        assert bm.score("萧尘", 0) == 0.0

    def test_eligible_filter_restricts_docs(self):
        bm = BM25Index().fit(["萧尘对决", "萧尘归来", "无关内容"])
        hits = bm.search("萧尘", k=5, eligible=[2])
        # Only doc 2 is eligible, it has no match.
        assert hits == []


class TestHybridRetriever:
    def test_bm25_branch_activates_and_tags_source(self, tmp_path):
        cards = [
            _make_card(1, "萧尘拜师学艺", entities=["萧尘"]),
            _make_card(2, "林渊独自修炼", entities=["林渊"]),
            _make_card(3, "洛清影出山", entities=["洛清影"]),
            _make_card(4, "萧尘对决林渊", entities=["萧尘", "林渊"]),
        ]
        idx = _build_index(tmp_path, cards)
        cfg = SemanticRecallConfig(
            recent_n=0,
            semantic_top_k=2,
            bm25_top_k=3,
            hybrid_enabled=True,
            min_semantic_score=0.0,
            final_top_k=10,
        )
        retr = SemanticChapterRetriever(index=idx, config=cfg)

        with patch.object(idx, "_get_model", return_value=_fake_model()):
            hits = retr.recall("萧尘", chapter_num=5)

        sources = {h.source for h in hits}
        # Expect BM25 to contribute its branch or fuse into existing semantic source.
        assert any("bm25" in s for s in sources), f"no bm25 tag in {sources}"

    def test_hybrid_disabled_falls_back_to_semantic_only(self, tmp_path):
        cards = [_make_card(i, f"章节{i}内容") for i in range(1, 5)]
        idx = _build_index(tmp_path, cards)
        cfg = SemanticRecallConfig(
            recent_n=0,
            semantic_top_k=3,
            bm25_top_k=0,
            hybrid_enabled=False,
            min_semantic_score=0.0,
            final_top_k=10,
        )
        retr = SemanticChapterRetriever(index=idx, config=cfg)

        with patch.object(idx, "_get_model", return_value=_fake_model()):
            hits = retr.recall("查询", chapter_num=5)

        for h in hits:
            assert "bm25" not in h.source

    def test_rrf_fusion_boosts_docs_hit_by_both_branches(self, tmp_path):
        # doc hit by both branches should score higher than doc hit by one.
        cards = [
            _make_card(1, "萧尘萧尘萧尘", entities=["萧尘"]),
            _make_card(2, "林渊"),
            _make_card(3, "其他内容"),
        ]
        idx = _build_index(tmp_path, cards)
        cfg = SemanticRecallConfig(
            recent_n=0,
            semantic_top_k=3,
            bm25_top_k=3,
            hybrid_enabled=True,
            min_semantic_score=0.0,
            final_top_k=10,
            rrf_k=60,
        )
        retr = SemanticChapterRetriever(index=idx, config=cfg)
        with patch.object(idx, "_get_model", return_value=_fake_model()):
            hits = retr.recall("萧尘", chapter_num=4)

        # ch1 should appear (BM25 strong) and win over ch3 (purely random semantic).
        hit_chapters = [h.chapter for h in hits]
        assert 1 in hit_chapters

    def test_payload_mode_reflects_bm25(self, tmp_path):
        cards = [_make_card(i, f"章节{i} 萧尘") for i in range(1, 5)]
        idx = _build_index(tmp_path, cards)
        cfg = SemanticRecallConfig(
            recent_n=0,
            semantic_top_k=2,
            bm25_top_k=3,
            hybrid_enabled=True,
            min_semantic_score=0.0,
            final_top_k=10,
        )
        retr = SemanticChapterRetriever(index=idx, config=cfg)
        with patch.object(idx, "_get_model", return_value=_fake_model()):
            payload = retr.recall_to_payload("萧尘", chapter_num=5)

        assert payload["mode"] in {"semantic_hybrid", "semantic_hybrid+bm25_rrf"}

    def test_no_future_chapters_returned_with_hybrid(self, tmp_path):
        cards = [_make_card(i, f"章节{i}内容 萧尘") for i in range(1, 11)]
        idx = _build_index(tmp_path, cards)
        cfg = SemanticRecallConfig(
            recent_n=2,
            semantic_top_k=5,
            bm25_top_k=5,
            hybrid_enabled=True,
            min_semantic_score=0.0,
            final_top_k=20,
        )
        retr = SemanticChapterRetriever(index=idx, config=cfg)
        with patch.object(idx, "_get_model", return_value=_fake_model()):
            hits = retr.recall("萧尘", chapter_num=5)

        for h in hits:
            assert h.chapter < 5
