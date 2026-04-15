"""Tests for Style RAG polish integration module."""

from __future__ import annotations

import pytest

from ink_writer.style_rag.polish_integration import (
    DEFAULT_TOP_K,
    MIN_QUALITY,
    PolishStylePack,
    StyleReference,
    _extract_paragraph_text,
    build_polish_style_pack,
)
from ink_writer.style_rag.retriever import StyleFragment


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_fragment(
    fid: str = "frag001",
    book_title: str = "测试之书",
    scene_type: str = "战斗",
    emotion: str = "紧张",
    content: str = "剑光如虹，划破长空。少年握紧手中长剑，真气在体内翻涌。",
    quality_score: float = 0.85,
    avg_sentence_length: float = 25.0,
    dialogue_ratio: float = 0.15,
    **kwargs,
) -> StyleFragment:
    defaults = dict(
        id=fid,
        book_title=book_title,
        book_genre="玄幻",
        chapter_num=1,
        scene_index=0,
        scene_type=scene_type,
        emotion=emotion,
        content=content,
        word_count=len(content),
        avg_sentence_length=avg_sentence_length,
        short_sentence_ratio=0.1,
        long_sentence_ratio=0.2,
        dialogue_ratio=dialogue_ratio,
        exclamation_density=2.0,
        ellipsis_density=1.0,
        question_density=0.5,
        quality_score=quality_score,
        score=0.92,
    )
    defaults.update(kwargs)
    return StyleFragment(**defaults)


class FakeRetriever:
    """Mock retriever that returns configurable fragments."""

    def __init__(self, fragments: list[StyleFragment] | None = None):
        self._fragments = fragments or [_make_fragment()]
        self.calls: list[dict] = []

    def retrieve(
        self,
        query: str,
        k: int = 5,
        scene_type: str | None = None,
        emotion: str | None = None,
        genre: str | None = None,
        min_quality: float = 0.0,
    ) -> list[StyleFragment]:
        self.calls.append(dict(
            query=query, k=k, scene_type=scene_type,
            emotion=emotion, genre=genre, min_quality=min_quality,
        ))
        return self._fragments[:k]


class FailingRetriever:
    """Retriever that always raises."""

    def retrieve(self, **kwargs) -> list[StyleFragment]:
        raise RuntimeError("index corrupted")


SAMPLE_CHAPTER = (
    "少年站在山巅，望着远方的云海。风从谷底升起，带着泥土和青草的气息。\n\n"
    "「你真的要走？」身后传来一个清冷的声音。\n\n"
    "他没有回头。手中的剑微微颤动，仿佛感受到了主人的犹豫。"
    "但下一刻，他已经纵身跃下悬崖，衣袍在风中猎猎作响。\n\n"
    "山下的村庄炊烟袅袅，一切如常。没有人知道，一场改变整个大陆格局的旅程，"
    "就此拉开了序幕。老村长坐在门前的石墩上，手中的烟袋明灭不定。\n\n"
    "「又一个不安分的孩子。」他叹了口气，浑浊的目光望向远方。"
)

SAMPLE_FIX_PRIORITIES = [
    {"location": "第2段", "type": "句长平坦区", "fix": "插入碎句打破均匀节奏"},
    {"location": "第3-4段", "type": "对话同质", "fix": "差异化角色对话长度和风格"},
    {"location": "第4段", "type": "段落过于工整", "fix": "拆分长段为碎片段"},
]


# ---------------------------------------------------------------------------
# _extract_paragraph_text
# ---------------------------------------------------------------------------

class TestExtractParagraphText:
    def test_single_paragraph_by_number(self):
        text = _extract_paragraph_text(SAMPLE_CHAPTER, "第2段")
        assert "你真的要走" in text

    def test_paragraph_range(self):
        text = _extract_paragraph_text(SAMPLE_CHAPTER, "第1-2段")
        assert "少年站在山巅" in text
        assert "你真的要走" in text

    def test_paragraph_format_段N(self):
        text = _extract_paragraph_text(SAMPLE_CHAPTER, "段3-5")
        assert len(text) > 0

    def test_line_range(self):
        text = _extract_paragraph_text(SAMPLE_CHAPTER, "第1-3行")
        assert len(text) > 0

    def test_fallback_returns_first_paragraph(self):
        text = _extract_paragraph_text(SAMPLE_CHAPTER, "unknown location")
        assert "少年站在山巅" in text

    def test_empty_chapter(self):
        text = _extract_paragraph_text("", "第1段")
        assert text == ""

    def test_out_of_range_paragraph(self):
        text = _extract_paragraph_text(SAMPLE_CHAPTER, "第99段")
        assert text == ""


# ---------------------------------------------------------------------------
# StyleReference
# ---------------------------------------------------------------------------

class TestStyleReference:
    def test_format_prompt_block_with_fragments(self):
        ref = StyleReference(
            fix_location="第2段",
            fix_type="句长平坦区",
            fragments=[_make_fragment()],
        )
        block = ref.format_prompt_block()
        assert "人写参考" in block
        assert "句长平坦区" in block
        assert "第2段" in block
        assert "测试之书" in block
        assert "剑光如虹" in block

    def test_format_prompt_block_empty(self):
        ref = StyleReference(
            fix_location="第2段",
            fix_type="句长平坦区",
            fragments=[],
        )
        assert ref.format_prompt_block() == ""

    def test_multiple_fragments(self):
        frags = [
            _make_fragment(fid="f1", content="第一段参考内容，风很大。"),
            _make_fragment(fid="f2", content="第二段参考内容，雨很急。"),
        ]
        ref = StyleReference(fix_location="第3段", fix_type="信息密度", fragments=frags)
        block = ref.format_prompt_block()
        assert "参考1" in block
        assert "参考2" in block

    def test_stats_in_prompt(self):
        frag = _make_fragment(avg_sentence_length=30.0, dialogue_ratio=0.25, quality_score=0.90)
        ref = StyleReference(fix_location="第1段", fix_type="test", fragments=[frag])
        block = ref.format_prompt_block()
        assert "句长均值30字" in block
        assert "对话占比25%" in block
        assert "质量0.90" in block


# ---------------------------------------------------------------------------
# PolishStylePack
# ---------------------------------------------------------------------------

class TestPolishStylePack:
    def test_has_references_true(self):
        pack = PolishStylePack(
            chapter=1,
            references=[StyleReference("loc", "type", [_make_fragment()])],
        )
        assert pack.has_references is True

    def test_has_references_false_empty_fragments(self):
        pack = PolishStylePack(
            chapter=1,
            references=[StyleReference("loc", "type", [])],
        )
        assert pack.has_references is False

    def test_has_references_false_no_refs(self):
        pack = PolishStylePack(chapter=1, references=[])
        assert pack.has_references is False

    def test_format_full_prompt_header(self):
        pack = PolishStylePack(
            chapter=5,
            references=[StyleReference("第2段", "句长平坦区", [_make_fragment()])],
        )
        prompt = pack.format_full_prompt()
        assert "人写标杆片段" in prompt
        assert "不可照搬内容或剧情" in prompt

    def test_format_full_prompt_empty(self):
        pack = PolishStylePack(chapter=1, references=[])
        assert pack.format_full_prompt() == ""

    def test_format_full_prompt_skips_empty_refs(self):
        pack = PolishStylePack(
            chapter=1,
            references=[
                StyleReference("第1段", "type_a", [_make_fragment()]),
                StyleReference("第2段", "type_b", []),
            ],
        )
        prompt = pack.format_full_prompt()
        assert "type_a" in prompt
        assert "type_b" not in prompt


# ---------------------------------------------------------------------------
# build_polish_style_pack
# ---------------------------------------------------------------------------

class TestBuildPolishStylePack:
    def test_basic_build(self):
        retriever = FakeRetriever()
        pack = build_polish_style_pack(
            fix_priorities=SAMPLE_FIX_PRIORITIES,
            chapter_text=SAMPLE_CHAPTER,
            chapter_no=42,
            retriever=retriever,
        )
        assert pack.chapter == 42
        assert len(pack.references) == 3
        assert pack.has_references is True
        assert len(retriever.calls) == 3

    def test_genre_filter_passed(self):
        retriever = FakeRetriever()
        build_polish_style_pack(
            fix_priorities=[SAMPLE_FIX_PRIORITIES[0]],
            chapter_text=SAMPLE_CHAPTER,
            chapter_no=1,
            retriever=retriever,
            genre="仙侠",
        )
        assert retriever.calls[0]["genre"] == "仙侠"

    def test_top_k_passed(self):
        retriever = FakeRetriever()
        build_polish_style_pack(
            fix_priorities=[SAMPLE_FIX_PRIORITIES[0]],
            chapter_text=SAMPLE_CHAPTER,
            chapter_no=1,
            retriever=retriever,
            top_k=5,
        )
        assert retriever.calls[0]["k"] == 5

    def test_min_quality_passed(self):
        retriever = FakeRetriever()
        build_polish_style_pack(
            fix_priorities=[SAMPLE_FIX_PRIORITIES[0]],
            chapter_text=SAMPLE_CHAPTER,
            chapter_no=1,
            retriever=retriever,
            min_quality=0.7,
        )
        assert retriever.calls[0]["min_quality"] == 0.7

    def test_dialogue_type_gets_scene_hint(self):
        retriever = FakeRetriever()
        fix = [{"location": "第1段", "type": "对话同质", "fix": "差异化"}]
        build_polish_style_pack(
            fix_priorities=fix,
            chapter_text=SAMPLE_CHAPTER,
            chapter_no=1,
            retriever=retriever,
        )
        assert retriever.calls[0]["scene_type"] == "对话"

    def test_non_dialogue_type_no_scene_hint(self):
        retriever = FakeRetriever()
        fix = [{"location": "第1段", "type": "句长平坦区", "fix": "修复"}]
        build_polish_style_pack(
            fix_priorities=fix,
            chapter_text=SAMPLE_CHAPTER,
            chapter_no=1,
            retriever=retriever,
        )
        assert retriever.calls[0]["scene_type"] is None

    def test_empty_fix_priorities(self):
        retriever = FakeRetriever()
        pack = build_polish_style_pack(
            fix_priorities=[],
            chapter_text=SAMPLE_CHAPTER,
            chapter_no=1,
            retriever=retriever,
        )
        assert pack.has_references is False
        assert len(retriever.calls) == 0

    def test_retriever_failure_graceful(self):
        retriever = FailingRetriever()
        pack = build_polish_style_pack(
            fix_priorities=SAMPLE_FIX_PRIORITIES,
            chapter_text=SAMPLE_CHAPTER,
            chapter_no=1,
            retriever=retriever,
        )
        assert len(pack.references) == 3
        assert pack.has_references is False

    def test_default_top_k_and_quality(self):
        retriever = FakeRetriever()
        build_polish_style_pack(
            fix_priorities=[SAMPLE_FIX_PRIORITIES[0]],
            chapter_text=SAMPLE_CHAPTER,
            chapter_no=1,
            retriever=retriever,
        )
        assert retriever.calls[0]["k"] == DEFAULT_TOP_K
        assert retriever.calls[0]["min_quality"] == MIN_QUALITY

    def test_full_prompt_integration(self):
        frags = [
            _make_fragment(fid="f1", content="人写参考片段一"),
            _make_fragment(fid="f2", content="人写参考片段二"),
        ]
        retriever = FakeRetriever(fragments=frags)
        pack = build_polish_style_pack(
            fix_priorities=SAMPLE_FIX_PRIORITIES[:1],
            chapter_text=SAMPLE_CHAPTER,
            chapter_no=10,
            retriever=retriever,
        )
        prompt = pack.format_full_prompt()
        assert "人写标杆片段" in prompt
        assert "人写参考片段一" in prompt
        assert "人写参考片段二" in prompt
