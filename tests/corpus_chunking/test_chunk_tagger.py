from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from scripts.corpus_chunking.chunk_tagger import TaggerConfig, tag_chunk
from scripts.corpus_chunking.models import RawChunk, SourceType


def _cfg(**overrides: object) -> TaggerConfig:
    base: dict[str, object] = {
        "model": "claude-haiku-4-5-20251001",
        "batch_size": 5,
        "quality_weights": {
            "tension": 0.3,
            "originality": 0.3,
            "language_density": 0.2,
            "readability": 0.2,
        },
        "max_retries": 3,
    }
    base.update(overrides)
    return TaggerConfig(**base)  # type: ignore[arg-type]


def _raw() -> RawChunk:
    return RawChunk(
        chunk_id="CHUNK-x-ch1-§1",
        source_book="x",
        source_chapter="ch1",
        char_range=(0, 80),
        text="克莱恩走进屋子。" * 10,
    )


def _mock_client(json_text: str) -> MagicMock:
    client = MagicMock()
    resp = MagicMock()
    resp.content = [MagicMock(text=json_text)]
    client.messages.create.return_value = resp
    return client


def test_tag_chunk_happy() -> None:
    payload = {
        "scene_type": "opening",
        "tension_level": 0.5,
        "character_count": 1,
        "dialogue_ratio": 0.0,
        "hook_type": "introduction",
        "borrowable_aspects": ["sensory_grounding"],
        "quality_breakdown": {
            "tension": 0.9,
            "originality": 0.8,
            "language_density": 0.7,
            "readability": 0.9,
        },
    }
    client = _mock_client(json.dumps(payload))
    tagged = tag_chunk(
        client=client,
        cfg=_cfg(),
        chunk=_raw(),
        genre=["异世大陆"],
        ingested_at="2026-04-25",
        source_type=SourceType.BUILTIN,
    )
    assert tagged.scene_type == "opening"
    assert tagged.genre == ["异世大陆"]
    assert tagged.character_count == 1
    assert tagged.borrowable_aspects == ["sensory_grounding"]
    assert tagged.quality_score == pytest.approx(
        0.9 * 0.3 + 0.8 * 0.3 + 0.7 * 0.2 + 0.9 * 0.2
    )


def test_tag_chunk_failure_returns_zero_quality() -> None:
    client = _mock_client("not a json at all")
    tagged = tag_chunk(
        client=client,
        cfg=_cfg(max_retries=2),
        chunk=_raw(),
        genre=["异世大陆"],
        ingested_at="2026-04-25",
        source_type=SourceType.BUILTIN,
    )
    assert tagged.scene_type == "tagging_failed"
    assert tagged.quality_score == 0.0
    assert tagged.borrowable_aspects == ["tagging_failed"]
    assert tagged.genre == ["异世大陆"]
    assert client.messages.create.call_count == 2


def test_tag_chunk_uses_passed_genre_not_llm() -> None:
    payload = {
        "scene_type": "opening",
        "tension_level": 0.5,
        "character_count": 1,
        "dialogue_ratio": 0.0,
        "hook_type": "introduction",
        "borrowable_aspects": ["x"],
        "genre": ["LLM-guessed-genre"],
        "quality_breakdown": {
            "tension": 0.5,
            "originality": 0.5,
            "language_density": 0.5,
            "readability": 0.5,
        },
    }
    client = _mock_client(json.dumps(payload))
    tagged = tag_chunk(
        client=client,
        cfg=_cfg(),
        chunk=_raw(),
        genre=["都市"],
        ingested_at="2026-04-25",
        source_type=SourceType.USER,
    )
    assert tagged.genre == ["都市"]
    assert tagged.source_type == SourceType.USER
