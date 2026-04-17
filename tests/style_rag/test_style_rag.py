"""Tests for Style RAG index builder and retriever."""

from __future__ import annotations

import json
import pathlib
import sqlite3
from unittest.mock import patch

import pytest

faiss = pytest.importorskip("faiss")
np = pytest.importorskip("numpy")
SentenceTransformer = pytest.importorskip("sentence_transformers").SentenceTransformer

from ink_writer.style_rag.retriever import (
    MODEL_NAME,
    StyleFragment,
    StyleRAGRetriever,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_FRAGMENTS = [
    {
        "id": "frag001",
        "book_title": "测试之书",
        "book_genre": "玄幻",
        "chapter_num": 1,
        "scene_index": 0,
        "scene_type": "战斗",
        "emotion": "紧张",
        "content": "剑光如虹，划破长空。少年握紧手中长剑，真气在体内翻涌，他知道这一战避无可避。对面的黑衣人冷笑一声，手中黑刃闪过一道寒芒。两人同时动了，剑气纵横，地面被劈出一道道深深的裂痕。",
        "word_count": 300,
        "avg_sentence_length": 15.0,
        "short_sentence_ratio": 0.2,
        "long_sentence_ratio": 0.1,
        "dialogue_ratio": 0.0,
        "exclamation_density": 2.0,
        "ellipsis_density": 1.0,
        "question_density": 0.5,
        "quality_score": 0.85,
    },
    {
        "id": "frag002",
        "book_title": "测试之书",
        "book_genre": "玄幻",
        "chapter_num": 1,
        "scene_index": 1,
        "scene_type": "对话",
        "emotion": "轻松",
        "content": "\u201c你到底是谁？\u201d少年收剑而立，目光警惕地看着对面的女子。女子轻笑一声，\u201c问这么多做什么，我只是路过而已。\u201d她转身离去，衣裙飘飘如仙子下凡。少年怔了怔，随即摇了摇头。",
        "word_count": 250,
        "avg_sentence_length": 12.0,
        "short_sentence_ratio": 0.3,
        "long_sentence_ratio": 0.05,
        "dialogue_ratio": 0.45,
        "exclamation_density": 1.0,
        "ellipsis_density": 0.5,
        "question_density": 3.0,
        "quality_score": 0.78,
    },
    {
        "id": "frag003",
        "book_title": "都市之光",
        "book_genre": "都市",
        "chapter_num": 5,
        "scene_index": 0,
        "scene_type": "情感",
        "emotion": "悲伤",
        "content": "窗外的雨淅淅沥沥地下着，打在窗户上发出细密的声响。她坐在沙发上，手里捧着那张已经泛黄的照片，泪水无声地滑落。三年了，他离开已经三年了。可她依然记得那天清晨，他最后一次回头微笑的样子。",
        "word_count": 280,
        "avg_sentence_length": 18.0,
        "short_sentence_ratio": 0.15,
        "long_sentence_ratio": 0.2,
        "dialogue_ratio": 0.0,
        "exclamation_density": 0.5,
        "ellipsis_density": 2.0,
        "question_density": 0.0,
        "quality_score": 0.92,
    },
    {
        "id": "frag004",
        "book_title": "都市之光",
        "book_genre": "都市",
        "chapter_num": 5,
        "scene_index": 1,
        "scene_type": "日常",
        "emotion": "轻松",
        "content": "早餐店里人来人往，热气腾腾的豆浆和油条是这座城市清晨最温暖的味道。老板娘笑呵呵地招呼着每一位客人，手里的动作却一刻不停。张伟要了一碗豆腐脑，坐在角落里慢慢地吃着，享受这难得的安宁。",
        "word_count": 260,
        "avg_sentence_length": 20.0,
        "short_sentence_ratio": 0.1,
        "long_sentence_ratio": 0.15,
        "dialogue_ratio": 0.0,
        "exclamation_density": 0.0,
        "ellipsis_density": 0.0,
        "question_density": 0.0,
        "quality_score": 0.70,
    },
    {
        "id": "frag005",
        "book_title": "星际征途",
        "book_genre": "科幻",
        "chapter_num": 10,
        "scene_index": 0,
        "scene_type": "高潮",
        "emotion": "震惊",
        "content": "警报声响彻整艘战舰，红色的灯光不断闪烁。指挥官盯着全息投影，瞳孔骤缩——那不是陨石带，那是一整支虫族舰队！不可能，侦察兵明明汇报这片区域是安全的！他来不及多想，立刻下达了战斗命令。",
        "word_count": 270,
        "avg_sentence_length": 16.0,
        "short_sentence_ratio": 0.25,
        "long_sentence_ratio": 0.1,
        "dialogue_ratio": 0.0,
        "exclamation_density": 5.0,
        "ellipsis_density": 1.0,
        "question_density": 0.0,
        "quality_score": 0.88,
    },
]


def _build_style_rag_db(db_path: pathlib.Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS style_fragments (
            id TEXT PRIMARY KEY,
            book_title TEXT NOT NULL,
            book_genre TEXT NOT NULL,
            chapter_num INTEGER NOT NULL,
            scene_index INTEGER NOT NULL,
            scene_type TEXT NOT NULL,
            emotion TEXT NOT NULL,
            content TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            avg_sentence_length REAL,
            short_sentence_ratio REAL,
            long_sentence_ratio REAL,
            dialogue_ratio REAL,
            exclamation_density REAL,
            ellipsis_density REAL,
            question_density REAL,
            quality_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for f in SAMPLE_FRAGMENTS:
        conn.execute(
            """INSERT INTO style_fragments
               (id, book_title, book_genre, chapter_num, scene_index,
                scene_type, emotion, content, word_count,
                avg_sentence_length, short_sentence_ratio, long_sentence_ratio,
                dialogue_ratio, exclamation_density, ellipsis_density,
                question_density, quality_score)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f["id"], f["book_title"], f["book_genre"], f["chapter_num"],
                f["scene_index"], f["scene_type"], f["emotion"], f["content"],
                f["word_count"], f["avg_sentence_length"], f["short_sentence_ratio"],
                f["long_sentence_ratio"], f["dialogue_ratio"],
                f["exclamation_density"], f["ellipsis_density"],
                f["question_density"], f["quality_score"],
            ),
        )
    conn.commit()
    conn.close()


def _build_faiss_index(index_dir: pathlib.Path) -> None:
    """Build a small FAISS index from SAMPLE_FRAGMENTS for testing."""
    model = SentenceTransformer(MODEL_NAME)
    texts = [f["content"] for f in SAMPLE_FRAGMENTS]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    embeddings = np.array(embeddings, dtype=np.float32)

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    index_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_dir / "style_rag.faiss"))

    metadata = []
    for f in SAMPLE_FRAGMENTS:
        entry = {k: v for k, v in f.items() if k != "content"}
        entry["content_preview"] = f["content"][:200]
        metadata.append(entry)

    (index_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (index_dir / "contents.json").write_text(
        json.dumps(
            [{"id": f["id"], "content": f["content"]} for f in SAMPLE_FRAGMENTS],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@pytest.fixture(scope="module")
def index_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("style_rag_index")
    _build_faiss_index(d)
    return d


@pytest.fixture(scope="module")
def retriever(index_dir):
    return StyleRAGRetriever(index_dir=index_dir)


@pytest.fixture
def style_rag_db(tmp_path):
    db_path = tmp_path / "style_rag.db"
    _build_style_rag_db(db_path)
    return db_path


# ---------------------------------------------------------------------------
# StyleFragment dataclass tests
# ---------------------------------------------------------------------------


class TestStyleFragment:
    def test_fields(self):
        frag = StyleFragment(
            id="x", book_title="t", book_genre="g", chapter_num=1,
            scene_index=0, scene_type="战斗", emotion="紧张",
            content="text", word_count=100, score=0.9,
        )
        assert frag.id == "x"
        assert frag.score == 0.9
        assert frag.scene_type == "战斗"

    def test_defaults(self):
        frag = StyleFragment(
            id="y", book_title="", book_genre="", chapter_num=0,
            scene_index=0, scene_type="", emotion="", content="",
            word_count=0,
        )
        assert frag.score == 0.0
        assert frag.quality_score == 0.0
        assert frag.dialogue_ratio == 0.0


# ---------------------------------------------------------------------------
# Retriever init tests
# ---------------------------------------------------------------------------


class TestRetrieverInit:
    def test_missing_index_raises(self, tmp_path):
        # v13 US-008：索引缺失时默认走 SQLite fallback；要 raise 需同时禁 auto_build 且 db_path 不存在
        with pytest.raises(FileNotFoundError, match="auto-build failed and SQLite fallback"):
            StyleRAGRetriever(
                index_dir=tmp_path / "nonexistent",
                db_path=tmp_path / "nonexistent.db",
                auto_build=False,
            )

    def test_partial_missing_raises(self, tmp_path):
        (tmp_path / "style_rag.faiss").touch()
        with pytest.raises(FileNotFoundError):
            StyleRAGRetriever(
                index_dir=tmp_path,
                db_path=tmp_path / "nonexistent.db",
                auto_build=False,
            )

    def test_loads_successfully(self, retriever):
        assert retriever.fragment_count == len(SAMPLE_FRAGMENTS)


# ---------------------------------------------------------------------------
# Retrieval tests
# ---------------------------------------------------------------------------


class TestRetrieval:
    def test_returns_top_k(self, retriever):
        results = retriever.retrieve("剑光战斗", k=3)
        assert len(results) == 3

    def test_returns_all_when_k_exceeds(self, retriever):
        results = retriever.retrieve("test", k=100)
        assert len(results) == len(SAMPLE_FRAGMENTS)

    def test_returns_style_fragments(self, retriever):
        results = retriever.retrieve("战斗场景", k=1)
        assert isinstance(results[0], StyleFragment)
        assert results[0].id in {f["id"] for f in SAMPLE_FRAGMENTS}

    def test_scores_descending(self, retriever):
        results = retriever.retrieve("剑气纵横战斗", k=5)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True), \
            f"Scores not descending: {scores}"

    def test_content_populated(self, retriever):
        results = retriever.retrieve("战斗", k=1)
        assert len(results[0].content) > 50

    def test_metadata_populated(self, retriever):
        results = retriever.retrieve("战斗", k=1)
        r = results[0]
        assert r.book_title != ""
        assert r.book_genre != ""
        assert r.scene_type != ""
        assert r.emotion != ""
        assert r.word_count > 0

    def test_battle_query_ranks_battle_higher(self, retriever):
        results = retriever.retrieve("剑光如虹真气翻涌战斗", k=5)
        battle_frags = [r for r in results if r.scene_type == "战斗"]
        assert len(battle_frags) >= 1
        assert results[0].scene_type == "战斗"


# ---------------------------------------------------------------------------
# Filtered retrieval tests
# ---------------------------------------------------------------------------


class TestFilteredRetrieval:
    def test_filter_by_scene_type(self, retriever):
        results = retriever.retrieve("something", k=10, scene_type="战斗")
        assert all(r.scene_type == "战斗" for r in results)
        assert len(results) == 1

    def test_filter_by_emotion(self, retriever):
        results = retriever.retrieve("something", k=10, emotion="轻松")
        assert all(r.emotion == "轻松" for r in results)
        assert len(results) == 2

    def test_filter_by_genre(self, retriever):
        results = retriever.retrieve("something", k=10, genre="都市")
        assert all("都市" in r.book_genre for r in results)
        assert len(results) == 2

    def test_filter_by_min_quality(self, retriever):
        results = retriever.retrieve("something", k=10, min_quality=0.85)
        assert all(r.quality_score >= 0.85 for r in results)
        assert len(results) == 3  # frag001(0.85), frag003(0.92), frag005(0.88)

    def test_combined_filters(self, retriever):
        results = retriever.retrieve(
            "something", k=10, genre="玄幻", scene_type="战斗"
        )
        assert len(results) == 1
        assert results[0].id == "frag001"

    def test_no_match_returns_empty(self, retriever):
        results = retriever.retrieve(
            "something", k=10, scene_type="悬念", genre="科幻"
        )
        assert results == []

    def test_filtered_scores_descending(self, retriever):
        results = retriever.retrieve("test", k=10, emotion="轻松")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Build script tests
# ---------------------------------------------------------------------------


class TestBuildScript:
    def test_load_fragments(self, style_rag_db):
        sys_path_backup = __import__("sys").path[:]
        try:
            import importlib
            import sys
            scripts_dir = str(pathlib.Path(__file__).resolve().parent.parent.parent / "scripts")
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)

            from build_style_rag import load_fragments
            frags = load_fragments(style_rag_db)
            assert len(frags) == len(SAMPLE_FRAGMENTS)
            assert all("content" in f for f in frags)
            assert all("scene_type" in f for f in frags)
        finally:
            __import__("sys").path[:] = sys_path_backup

    def test_build_index_creates_files(self, style_rag_db, tmp_path):
        import sys
        scripts_dir = str(pathlib.Path(__file__).resolve().parent.parent.parent / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        from build_style_rag import build_index
        out_dir = tmp_path / "idx_out"
        stats = build_index(style_rag_db, out_dir)

        assert (out_dir / "style_rag.faiss").exists()
        assert (out_dir / "metadata.json").exists()
        assert (out_dir / "contents.json").exists()
        assert (out_dir / "build_stats.json").exists()
        assert stats["fragments_indexed"] == len(SAMPLE_FRAGMENTS)
        assert stats["embedding_dim"] > 0

    def test_built_index_is_queryable(self, style_rag_db, tmp_path):
        import sys
        scripts_dir = str(pathlib.Path(__file__).resolve().parent.parent.parent / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        from build_style_rag import build_index
        out_dir = tmp_path / "idx_query"
        build_index(style_rag_db, out_dir)

        ret = StyleRAGRetriever(index_dir=out_dir)
        results = ret.retrieve("战斗场景", k=2)
        assert len(results) == 2
        assert all(isinstance(r, StyleFragment) for r in results)

    def test_metadata_no_full_content(self, style_rag_db, tmp_path):
        import sys
        scripts_dir = str(pathlib.Path(__file__).resolve().parent.parent.parent / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        from build_style_rag import build_index
        out_dir = tmp_path / "idx_meta"
        build_index(style_rag_db, out_dir)

        meta = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
        for entry in meta:
            assert "content" not in entry
            assert "content_preview" in entry
            assert len(entry["content_preview"]) <= 200

    def test_contents_json_has_full_text(self, style_rag_db, tmp_path):
        import sys
        scripts_dir = str(pathlib.Path(__file__).resolve().parent.parent.parent / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        from build_style_rag import build_index
        out_dir = tmp_path / "idx_contents"
        build_index(style_rag_db, out_dir)

        contents = json.loads((out_dir / "contents.json").read_text(encoding="utf-8"))
        assert len(contents) == len(SAMPLE_FRAGMENTS)
        for c in contents:
            assert "id" in c
            assert "content" in c
            assert len(c["content"]) > 50


# ---------------------------------------------------------------------------
# Live corpus tests (only if real index exists)
# ---------------------------------------------------------------------------


LIVE_INDEX_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "style_rag"


@pytest.mark.skipif(
    not (LIVE_INDEX_DIR / "style_rag.faiss").exists(),
    reason="Live Style RAG index not built",
)
class TestLiveIndex:
    @pytest.fixture(scope="class")
    def live_retriever(self):
        return StyleRAGRetriever(index_dir=LIVE_INDEX_DIR)

    def test_fragment_count(self, live_retriever):
        assert live_retriever.fragment_count >= 100

    def test_battle_scene_retrieval(self, live_retriever):
        results = live_retriever.retrieve("剑光如虹激烈战斗", k=5, scene_type="战斗")
        assert len(results) <= 5
        assert all(r.scene_type == "战斗" for r in results)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_emotion_scene_retrieval(self, live_retriever):
        results = live_retriever.retrieve("悲伤离别泪水", k=5, emotion="悲伤")
        assert len(results) <= 5
        assert all(r.emotion == "悲伤" for r in results)
