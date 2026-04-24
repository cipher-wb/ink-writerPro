"""scene_segmenter: LLM 切场景边界 → RawChunk 列表。

输入一章正文 → 调 Haiku 输出 JSON {chunks: [{scene_type, char_range, text}, ...]}
→ 解析 + 后处理（rechunk oversize）→ 返回 RawChunk 列表。

失败处理：JSON 解析失败重试 max_retries 次；仍失败返回空列表（caller 决定写 failures.jsonl）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.corpus_chunking.models import RawChunk

_PROMPT_PATH = Path(__file__).parent / "prompts" / "scene_segmenter.txt"


@dataclass
class SegmenterConfig:
    model: str
    min_chunk_chars: int
    max_chunk_chars: int
    max_retries: int


def _load_prompt(book: str, chapter: str, text: str) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{book}", book)
        .replace("{chapter}", chapter)
        .replace("{chapter_text}", text)
    )


def _parse_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
        return None


def _rechunk_oversize(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(cursor + max_chars, len(text))
        slice_text = text[cursor:end]
        last_period = max(
            slice_text.rfind("。"),
            slice_text.rfind("！"),
            slice_text.rfind("？"),
        )
        if last_period > 100 and cursor + last_period + 1 < len(text):
            cut = cursor + last_period + 1
        else:
            cut = end
        parts.append(text[cursor:cut])
        cursor = cut
    return parts


def segment_chapter(
    *,
    client: Any,
    cfg: SegmenterConfig,
    book: str,
    chapter: str,
    text: str,
) -> list[RawChunk]:
    """Returns RawChunk list. Empty list iff all retries failed (caller logs)."""
    prompt = _load_prompt(book, chapter, text)
    payload: dict[str, Any] | None = None
    for _ in range(cfg.max_retries):
        try:
            resp = client.messages.create(
                model=cfg.model,
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text
            payload = _parse_json(raw)
            if payload and "chunks" in payload:
                break
            payload = None
        except Exception:  # noqa: BLE001 — broad retry on any SDK/transport error
            payload = None
    if not payload or "chunks" not in payload:
        return []

    chunks: list[RawChunk] = []
    seq = 0
    for ch in payload["chunks"]:
        text_part = ch.get("text", "")
        cr = ch.get("char_range") or [0, len(text_part)]
        cr_start = int(cr[0])
        cr_end_orig = int(cr[1]) if len(cr) >= 2 else cr_start + len(text_part)
        rechunked = _rechunk_oversize(text_part, cfg.max_chunk_chars)
        if len(rechunked) <= 1:
            seq += 1
            chunks.append(
                RawChunk(
                    chunk_id=f"CHUNK-{book}-{chapter}-§{seq}",
                    source_book=book,
                    source_chapter=chapter,
                    char_range=(cr_start, cr_end_orig),
                    text=text_part,
                )
            )
        else:
            sub_start = cr_start
            for sub in rechunked:
                seq += 1
                sub_end = sub_start + len(sub)
                chunks.append(
                    RawChunk(
                        chunk_id=f"CHUNK-{book}-{chapter}-§{seq}",
                        source_book=book,
                        source_chapter=chapter,
                        char_range=(sub_start, sub_end),
                        text=sub,
                    )
                )
                sub_start = sub_end
    return chunks
