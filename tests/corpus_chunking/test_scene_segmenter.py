from __future__ import annotations

import json
from unittest.mock import MagicMock

from scripts.corpus_chunking.scene_segmenter import (
    SegmenterConfig,
    segment_chapter,
)


def _mock_anthropic_response(payload: dict) -> MagicMock:
    """Mimic anthropic client response shape."""
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(payload, ensure_ascii=False))]
    return msg


def test_segment_chapter_happy_path() -> None:
    client = MagicMock()
    client.messages.create.return_value = _mock_anthropic_response({
        "chunks": [
            {"scene_type": "opening", "char_range": [0, 400], "text": "克莱恩盯着镜子。" * 25},
            {"scene_type": "combat", "char_range": [400, 800], "text": "战斗开始。" * 40},
        ]
    })
    cfg = SegmenterConfig(
        model="claude-haiku-4-5", min_chunk_chars=200, max_chunk_chars=800, max_retries=3,
    )
    chunks = segment_chapter(
        client=client,
        cfg=cfg,
        book="诡秘之主",
        chapter="ch003",
        text="x" * 800,
    )
    assert len(chunks) == 2
    assert chunks[0].chunk_id == "CHUNK-诡秘之主-ch003-§1"
    assert chunks[0].source_book == "诡秘之主"
    assert chunks[0].source_chapter == "ch003"
    assert chunks[0].char_range == (0, 400)
    assert chunks[1].chunk_id == "CHUNK-诡秘之主-ch003-§2"


def test_segment_retries_on_invalid_json() -> None:
    client = MagicMock()
    bad = MagicMock()
    bad.content = [MagicMock(text="not json")]
    good = _mock_anthropic_response({
        "chunks": [{"scene_type": "opening", "char_range": [0, 300], "text": "abc"}]
    })
    client.messages.create.side_effect = [bad, bad, good]
    cfg = SegmenterConfig(model="m", min_chunk_chars=200, max_chunk_chars=800, max_retries=3)
    chunks = segment_chapter(client=client, cfg=cfg, book="b", chapter="c", text="x" * 300)
    assert len(chunks) == 1


def test_segment_returns_empty_after_max_retries() -> None:
    client = MagicMock()
    bad = MagicMock()
    bad.content = [MagicMock(text="garbage")]
    client.messages.create.side_effect = [bad, bad, bad]
    cfg = SegmenterConfig(model="m", min_chunk_chars=200, max_chunk_chars=800, max_retries=3)
    chunks = segment_chapter(client=client, cfg=cfg, book="b", chapter="c", text="x" * 500)
    assert chunks == []


def test_segment_rechunks_oversize_output() -> None:
    """LLM returns a 1200-char chunk; segmenter splits it on sentence boundary."""
    client = MagicMock()
    big_text = "句子。" * 400  # 1200 chars
    client.messages.create.return_value = _mock_anthropic_response({
        "chunks": [{"scene_type": "opening", "char_range": [0, 1200], "text": big_text}]
    })
    cfg = SegmenterConfig(model="m", min_chunk_chars=200, max_chunk_chars=800, max_retries=3)
    chunks = segment_chapter(client=client, cfg=cfg, book="b", chapter="c", text=big_text)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c.text) <= 800
