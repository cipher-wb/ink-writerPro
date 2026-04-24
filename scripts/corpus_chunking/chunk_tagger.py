"""chunk_tagger: LLM 给 RawChunk 打 6 标签 + 4 维 quality_breakdown → TaggedChunk.

genre 不让 LLM 判（防跨书漂移），从 caller 传入（manifest.json 继承）。
4 维加权由 tagger 内部完成（不依赖 LLM 自己加权），权重从 cfg.quality_weights 读取。
LLM 失败重试 max_retries 次后仍失败 → 返回 scene_type=tagging_failed + quality_score=0
的 TaggedChunk（不丢数据，schema 仍合法，caller 可决定是否上索引）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.corpus_chunking.models import (
    QualityBreakdown,
    RawChunk,
    SourceType,
    TaggedChunk,
)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "chunk_tagger.txt"

_DEFAULT_WEIGHTS: dict[str, float] = {
    "tension": 0.3,
    "originality": 0.3,
    "language_density": 0.2,
    "readability": 0.2,
}


@dataclass
class TaggerConfig:
    model: str
    batch_size: int = 5
    quality_weights: dict[str, float] = field(
        default_factory=lambda: dict(_DEFAULT_WEIGHTS)
    )
    max_retries: int = 3

    def weights_tuple(self) -> tuple[float, float, float, float]:
        w = self.quality_weights
        return (
            float(w.get("tension", _DEFAULT_WEIGHTS["tension"])),
            float(w.get("originality", _DEFAULT_WEIGHTS["originality"])),
            float(w.get("language_density", _DEFAULT_WEIGHTS["language_density"])),
            float(w.get("readability", _DEFAULT_WEIGHTS["readability"])),
        )


def _load_prompt(chunk_text: str) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{chunk_text}", chunk_text)


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


def _failure_tagged_chunk(
    chunk: RawChunk,
    genre: list[str],
    source_type: SourceType,
    ingested_at: str,
    weights: tuple[float, float, float, float],
) -> TaggedChunk:
    return TaggedChunk(
        raw=chunk,
        scene_type="tagging_failed",
        genre=list(genre),
        tension_level=0.0,
        character_count=0,
        dialogue_ratio=0.0,
        hook_type="unknown",
        borrowable_aspects=["tagging_failed"],
        quality_breakdown=QualityBreakdown(0.0, 0.0, 0.0, 0.0),
        source_type=source_type,
        ingested_at=ingested_at,
        quality_weights=weights,
    )


def tag_chunk(
    *,
    client: Any,
    cfg: TaggerConfig,
    chunk: RawChunk,
    genre: list[str],
    ingested_at: str,
    source_type: SourceType,
) -> TaggedChunk:
    """LLM 给单个 RawChunk 打标签；失败返回 tagging_failed TaggedChunk。"""
    prompt = _load_prompt(chunk.text)
    weights = cfg.weights_tuple()
    payload: dict[str, Any] | None = None
    for _ in range(max(1, cfg.max_retries)):
        try:
            resp = client.messages.create(
                model=cfg.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = resp.content[0].text
            parsed = _parse_json(raw_text)
            if parsed and "quality_breakdown" in parsed:
                payload = parsed
                break
        except Exception:  # noqa: BLE001 — broad retry on any SDK/transport error
            payload = None

    if payload is None:
        return _failure_tagged_chunk(chunk, genre, source_type, ingested_at, weights)

    try:
        qb = payload["quality_breakdown"]
        breakdown = QualityBreakdown(
            tension=float(qb["tension"]),
            originality=float(qb["originality"]),
            language_density=float(qb["language_density"]),
            readability=float(qb["readability"]),
        )
        return TaggedChunk(
            raw=chunk,
            scene_type=str(payload.get("scene_type", "unknown")),
            genre=list(genre),  # caller-supplied; LLM 的 genre 一律忽略
            tension_level=float(payload.get("tension_level", 0.0)),
            character_count=int(payload.get("character_count", 0)),
            dialogue_ratio=float(payload.get("dialogue_ratio", 0.0)),
            hook_type=str(payload.get("hook_type", "unknown")),
            borrowable_aspects=[str(x) for x in payload.get("borrowable_aspects", [])],
            quality_breakdown=breakdown,
            source_type=source_type,
            ingested_at=ingested_at,
            quality_weights=weights,
        )
    except (KeyError, TypeError, ValueError):
        return _failure_tagged_chunk(chunk, genre, source_type, ingested_at, weights)
