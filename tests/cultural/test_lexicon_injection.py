"""Tests for cultural lexicon loading, sampling, and context injection."""

from __future__ import annotations

import json
import pathlib
from textwrap import dedent

import pytest

from ink_writer.cultural_lexicon.config import (
    DEFAULT_MIN_TERMS,
    SUPPORTED_GENRES,
    CulturalLexiconConfig,
    InjectInto,
    load_config,
)
from ink_writer.cultural_lexicon.context_injection import (
    CulturalLexiconSection,
    build_cultural_lexicon_section,
)
from ink_writer.cultural_lexicon.loader import (
    DEFAULT_DATA_DIR,
    LexiconEntry,
    load_lexicon,
    sample_lexicon,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    id_: str = "T001",
    term: str = "测试词",
    type_: str = "idiom",
    category: str = "general",
    usage_example: str = "示例句子",
    context_hint: str = "用于测试",
) -> LexiconEntry:
    return LexiconEntry(
        id=id_, term=term, type=type_,
        category=category, usage_example=usage_example,
        context_hint=context_hint,
    )


def _make_lexicon_file(
    tmp_path: pathlib.Path,
    genre: str,
    count: int = 10,
    categories: list[str] | None = None,
) -> pathlib.Path:
    """Create a minimal lexicon JSON for testing."""
    cats = categories or ["cat_a", "cat_b"]
    entries = []
    for i in range(count):
        entries.append({
            "id": f"T{i:03d}",
            "term": f"词汇{i}",
            "type": "idiom" if i % 2 == 0 else "slang",
            "category": cats[i % len(cats)],
            "usage_example": f"这是词汇{i}的用法示例",
            "context_hint": f"场景{i}",
        })
    data = {
        "genre": genre,
        "version": "1.0.0",
        "description": f"{genre}测试语料库",
        "total_count": count,
        "entries": entries,
    }
    path = tmp_path / f"{genre}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestConfig:
    def test_default_config(self):
        cfg = CulturalLexiconConfig()
        assert cfg.enabled is True
        assert cfg.inject_into.context is True
        assert cfg.inject_into.writer is True
        assert cfg.inject_count == 20
        assert cfg.seed_offset == 42
        assert cfg.min_terms_per_chapter == DEFAULT_MIN_TERMS

    def test_load_missing_file_returns_defaults(self, tmp_path: pathlib.Path):
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.enabled is True

    def test_load_config_from_yaml(self, tmp_path: pathlib.Path):
        yaml_content = dedent("""\
            enabled: true
            inject_into:
              context: true
              writer: false
            min_terms_per_chapter:
              xianxia: 8
              scifi: 6
            inject_count: 15
            seed_offset: 99
        """)
        cfg_path = tmp_path / "cultural-lexicon.yaml"
        cfg_path.write_text(yaml_content, encoding="utf-8")
        cfg = load_config(cfg_path)
        assert cfg.enabled is True
        assert cfg.inject_into.context is True
        assert cfg.inject_into.writer is False
        assert cfg.min_terms_per_chapter["xianxia"] == 8
        assert cfg.min_terms_per_chapter["scifi"] == 6
        assert cfg.min_terms_per_chapter["urban"] == 3  # default preserved
        assert cfg.inject_count == 15
        assert cfg.seed_offset == 99

    def test_load_config_invalid_yaml(self, tmp_path: pathlib.Path):
        cfg_path = tmp_path / "bad.yaml"
        cfg_path.write_text("null", encoding="utf-8")
        cfg = load_config(cfg_path)
        assert cfg.enabled is True

    def test_load_config_empty_inject_into(self, tmp_path: pathlib.Path):
        cfg_path = tmp_path / "partial.yaml"
        cfg_path.write_text("enabled: false\ninject_into: 42\n", encoding="utf-8")
        cfg = load_config(cfg_path)
        assert cfg.enabled is False
        assert cfg.inject_into.context is True  # default

    def test_supported_genres_complete(self):
        assert len(SUPPORTED_GENRES) >= 6
        for g in ["xianxia", "xuanhuan", "urban", "scifi", "lishi", "youxi"]:
            assert g in SUPPORTED_GENRES

    def test_real_config_loads(self):
        """Real config/cultural-lexicon.yaml should be parseable."""
        from ink_writer.cultural_lexicon.config import DEFAULT_CONFIG_PATH
        if DEFAULT_CONFIG_PATH.exists():
            cfg = load_config()
            assert cfg.enabled in (True, False)


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------

class TestLoader:
    def test_load_valid_lexicon(self, tmp_path: pathlib.Path):
        _make_lexicon_file(tmp_path, "xianxia", count=15)
        entries = load_lexicon("xianxia", data_dir=tmp_path)
        assert len(entries) == 15
        assert all(isinstance(e, LexiconEntry) for e in entries)

    def test_load_missing_genre(self, tmp_path: pathlib.Path):
        entries = load_lexicon("nonexistent", data_dir=tmp_path)
        assert entries == []

    def test_load_invalid_json(self, tmp_path: pathlib.Path):
        (tmp_path / "bad.json").write_text("not json", encoding="utf-8")
        entries = load_lexicon("bad", data_dir=tmp_path)
        assert entries == []

    def test_load_non_dict_json(self, tmp_path: pathlib.Path):
        (tmp_path / "arr.json").write_text("[1,2,3]", encoding="utf-8")
        entries = load_lexicon("arr", data_dir=tmp_path)
        assert entries == []

    def test_entry_fields(self, tmp_path: pathlib.Path):
        _make_lexicon_file(tmp_path, "urban", count=1)
        entries = load_lexicon("urban", data_dir=tmp_path)
        e = entries[0]
        assert e.id == "T000"
        assert e.term == "词汇0"
        assert e.type == "idiom"
        assert e.category == "cat_a"
        assert "用法示例" in e.usage_example
        assert "场景" in e.context_hint

    def test_entry_is_frozen(self, tmp_path: pathlib.Path):
        _make_lexicon_file(tmp_path, "test", count=1)
        entries = load_lexicon("test", data_dir=tmp_path)
        with pytest.raises(AttributeError):
            entries[0].term = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Sampling tests
# ---------------------------------------------------------------------------

class TestSampling:
    @pytest.fixture()
    def entries(self) -> list[LexiconEntry]:
        return [
            _make_entry(f"E{i:03d}", f"词{i}", category=f"cat_{i % 3}")
            for i in range(30)
        ]

    def test_sample_count(self, entries: list[LexiconEntry]):
        result = sample_lexicon(entries, 10)
        assert len(result) == 10

    def test_sample_exceeding_pool(self, entries: list[LexiconEntry]):
        result = sample_lexicon(entries, 100)
        assert len(result) == 30

    def test_sample_empty(self):
        assert sample_lexicon([], 5) == []

    def test_sample_zero_count(self, entries: list[LexiconEntry]):
        assert sample_lexicon(entries, 0) == []

    def test_deterministic_by_chapter(self, entries: list[LexiconEntry]):
        a = sample_lexicon(entries, 5, chapter_no=1)
        b = sample_lexicon(entries, 5, chapter_no=1)
        assert a == b

    def test_different_chapters_different_selection(self, entries: list[LexiconEntry]):
        a = sample_lexicon(entries, 10, chapter_no=1)
        b = sample_lexicon(entries, 10, chapter_no=2)
        assert a != b

    def test_category_diversity(self, entries: list[LexiconEntry]):
        result = sample_lexicon(
            entries, 10,
            categories=["cat_0", "cat_1", "cat_2"],
        )
        cats = {e.category for e in result}
        assert len(cats) >= 2

    def test_category_filter(self, entries: list[LexiconEntry]):
        result = sample_lexicon(entries, 5, categories=["cat_0"])
        assert all(e.category == "cat_0" for e in result)


# ---------------------------------------------------------------------------
# Context injection tests
# ---------------------------------------------------------------------------

class TestContextInjection:
    @pytest.fixture()
    def lexicon(self) -> list[LexiconEntry]:
        return [
            _make_entry(f"L{i:03d}", f"文化词{i}", category=f"c_{i % 4}")
            for i in range(50)
        ]

    def test_build_section_default(self, lexicon: list[LexiconEntry]):
        section = build_cultural_lexicon_section(
            "xianxia", chapter_no=1, lexicon=lexicon,
        )
        assert not section.empty
        assert section.genre == "xianxia"
        assert section.min_terms == 5
        assert len(section.entries) == 20  # default inject_count

    def test_build_section_disabled(self, lexicon: list[LexiconEntry]):
        cfg = CulturalLexiconConfig(enabled=False)
        section = build_cultural_lexicon_section(
            "xianxia", config=cfg, lexicon=lexicon,
        )
        assert section.empty

    def test_build_section_context_disabled(self, lexicon: list[LexiconEntry]):
        cfg = CulturalLexiconConfig(
            inject_into=InjectInto(context=False),
        )
        section = build_cultural_lexicon_section(
            "xianxia", config=cfg, lexicon=lexicon,
        )
        assert section.empty

    def test_build_section_empty_lexicon(self):
        section = build_cultural_lexicon_section(
            "xianxia", lexicon=[],
        )
        assert section.empty

    def test_build_section_unknown_genre_min_terms(self, lexicon: list[LexiconEntry]):
        section = build_cultural_lexicon_section(
            "unknown_genre", lexicon=lexicon,
        )
        assert section.min_terms == 3  # fallback default

    def test_to_markdown_format(self, lexicon: list[LexiconEntry]):
        section = build_cultural_lexicon_section(
            "xianxia", chapter_no=5, lexicon=lexicon,
        )
        md = section.to_markdown()
        assert "### 13. 文化语料库" in md
        assert "xianxia" in md
        assert "硬约束" in md
        assert "≥5" in md

    def test_to_markdown_empty(self):
        section = CulturalLexiconSection()
        assert section.to_markdown() == ""

    def test_markdown_groups_by_category(self, lexicon: list[LexiconEntry]):
        section = build_cultural_lexicon_section(
            "urban", chapter_no=1, lexicon=lexicon,
        )
        md = section.to_markdown()
        assert "**[c_" in md  # category headers

    def test_custom_inject_count(self, lexicon: list[LexiconEntry]):
        cfg = CulturalLexiconConfig(inject_count=5)
        section = build_cultural_lexicon_section(
            "xianxia", config=cfg, lexicon=lexicon,
        )
        assert len(section.entries) == 5

    def test_categories_passed_through(self, lexicon: list[LexiconEntry]):
        section = build_cultural_lexicon_section(
            "xianxia", chapter_no=1,
            lexicon=lexicon, categories=["c_0"],
        )
        assert all(e.category == "c_0" for e in section.entries)


# ---------------------------------------------------------------------------
# Live data tests (skip if data dir missing)
# ---------------------------------------------------------------------------

_LIVE_DIR = DEFAULT_DATA_DIR


@pytest.mark.skipif(
    not _LIVE_DIR.exists(),
    reason="Live cultural lexicon data not available",
)
class TestLiveData:
    @pytest.mark.parametrize("genre", sorted(SUPPORTED_GENRES))
    def test_genre_file_exists(self, genre: str):
        path = _LIVE_DIR / f"{genre}.json"
        assert path.exists(), f"Missing {path}"

    @pytest.mark.parametrize("genre", sorted(SUPPORTED_GENRES))
    def test_genre_has_minimum_entries(self, genre: str):
        entries = load_lexicon(genre)
        assert len(entries) >= 300, f"{genre}: only {len(entries)} entries, need ≥300"

    @pytest.mark.parametrize("genre", sorted(SUPPORTED_GENRES))
    def test_no_duplicate_ids(self, genre: str):
        entries = load_lexicon(genre)
        ids = [e.id for e in entries]
        assert len(ids) == len(set(ids)), f"{genre}: duplicate IDs found"

    @pytest.mark.parametrize("genre", sorted(SUPPORTED_GENRES))
    def test_no_empty_terms(self, genre: str):
        entries = load_lexicon(genre)
        for e in entries:
            assert e.term.strip(), f"{genre}/{e.id}: empty term"
            assert e.usage_example.strip(), f"{genre}/{e.id}: empty usage_example"

    @pytest.mark.parametrize("genre", sorted(SUPPORTED_GENRES))
    def test_valid_types(self, genre: str):
        valid = {"idiom", "slang", "dialect", "era_word", "jargon"}
        entries = load_lexicon(genre)
        for e in entries:
            assert e.type in valid, f"{genre}/{e.id}: invalid type '{e.type}'"

    @pytest.mark.parametrize("genre", sorted(SUPPORTED_GENRES))
    def test_build_section_from_live_data(self, genre: str):
        section = build_cultural_lexicon_section(genre, chapter_no=1)
        assert not section.empty
        md = section.to_markdown()
        assert len(md) > 100

    def test_different_chapters_different_words(self):
        s1 = build_cultural_lexicon_section("xianxia", chapter_no=1)
        s2 = build_cultural_lexicon_section("xianxia", chapter_no=50)
        terms1 = {e.term for e in s1.entries}
        terms2 = {e.term for e in s2.entries}
        assert terms1 != terms2
