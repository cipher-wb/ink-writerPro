"""Scene-level emotion curve detection using keyword-based valence/arousal mapping."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

EMOTION_VALENCE_AROUSAL: dict[str, tuple[float, float]] = {
    "紧张": (-0.3, 0.8),
    "热血": (0.4, 0.9),
    "悲伤": (-0.7, 0.3),
    "轻松": (0.6, 0.2),
    "震惊": (-0.1, 0.9),
    "愤怒": (-0.6, 0.8),
    "温馨": (0.7, 0.2),
}

EMOTION_KEYWORDS: dict[str, list[str]] = {
    "紧张": ["紧张", "心跳", "冷汗", "屏息", "颤抖", "危险", "死"],
    "热血": ["热血", "燃烧", "冲", "战", "豪气", "壮志", "怒吼"],
    "悲伤": ["泪", "哭", "痛", "失去", "离别", "死去", "悲", "心碎"],
    "轻松": ["笑", "乐", "有趣", "好玩", "轻松", "惬意", "舒适"],
    "震惊": ["震惊", "不可能", "怎么可能", "瞳孔", "难以置信", "目瞪口呆"],
    "愤怒": ["愤怒", "怒", "恨", "该死", "混蛋", "可恶", "杀了"],
    "温馨": ["温暖", "温柔", "关心", "照顾", "微笑", "安慰", "陪伴"],
}


@dataclass
class SceneEmotion:
    scene_index: int
    start_char: int
    end_char: int
    valence: float
    arousal: float
    dominant_emotion: str
    keyword_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class EmotionCurve:
    chapter: int
    scenes: list[SceneEmotion]
    valence_variance: float
    arousal_variance: float
    flat_segments: list[int]
    overall_valence_range: float
    overall_arousal_range: float


def split_scenes(text: str, min_scene_chars: int = 200) -> list[tuple[int, int]]:
    """Split chapter text into scene boundaries by paragraph breaks or scene markers."""
    separators = re.compile(r"\n{2,}|(?:^|\n)\s*[＊\*]{3,}\s*(?:\n|$)|(?:^|\n)\s*---+\s*(?:\n|$)")
    if not text.strip():
        return []

    parts: list[tuple[int, int]] = []
    prev = 0
    for m in separators.finditer(text):
        if m.start() > prev:
            parts.append((prev, m.start()))
        prev = m.end()
    if prev < len(text):
        parts.append((prev, len(text)))

    merged: list[tuple[int, int]] = []
    for start, end in parts:
        if merged and (end - merged[-1][0]) < min_scene_chars * 2 and (end - start) < min_scene_chars:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))

    if not merged:
        merged.append((0, len(text)))

    return merged


def _compute_scene_emotion(text_segment: str) -> tuple[float, float, str, dict[str, int]]:
    """Compute valence/arousal for a text segment via keyword frequency weighting."""
    counts: dict[str, int] = {}
    for emotion, keywords in EMOTION_KEYWORDS.items():
        total = 0
        for kw in keywords:
            total += len(re.findall(re.escape(kw), text_segment))
        if total > 0:
            counts[emotion] = total

    if not counts:
        return 0.0, 0.3, "中性", counts

    total_hits = sum(counts.values())
    weighted_valence = 0.0
    weighted_arousal = 0.0

    for emotion, count in counts.items():
        v, a = EMOTION_VALENCE_AROUSAL[emotion]
        weight = count / total_hits
        weighted_valence += v * weight
        weighted_arousal += a * weight

    dominant = max(counts, key=counts.get)
    return weighted_valence, weighted_arousal, dominant, counts


def detect_emotion_curve(text: str, chapter: int, min_scene_chars: int = 200) -> EmotionCurve:
    """Detect per-scene emotion curve for a chapter."""
    boundaries = split_scenes(text, min_scene_chars)

    scenes: list[SceneEmotion] = []
    for i, (start, end) in enumerate(boundaries):
        segment = text[start:end]
        valence, arousal, dominant, counts = _compute_scene_emotion(segment)
        scenes.append(SceneEmotion(
            scene_index=i,
            start_char=start,
            end_char=end,
            valence=valence,
            arousal=arousal,
            dominant_emotion=dominant,
            keyword_counts=counts,
        ))

    valences = [s.valence for s in scenes]
    arousals = [s.arousal for s in scenes]

    valence_var = _variance(valences)
    arousal_var = _variance(arousals)

    flat_segments = _find_flat_segments(scenes)

    v_range = (max(valences) - min(valences)) if valences else 0.0
    a_range = (max(arousals) - min(arousals)) if arousals else 0.0

    return EmotionCurve(
        chapter=chapter,
        scenes=scenes,
        valence_variance=valence_var,
        arousal_variance=arousal_var,
        flat_segments=flat_segments,
        overall_valence_range=v_range,
        overall_arousal_range=a_range,
    )


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def _find_flat_segments(scenes: list[SceneEmotion], delta_threshold: float = 0.05) -> list[int]:
    """Find scene indices where consecutive scenes have nearly identical emotion."""
    flat: list[int] = []
    for i in range(1, len(scenes)):
        v_delta = abs(scenes[i].valence - scenes[i - 1].valence)
        a_delta = abs(scenes[i].arousal - scenes[i - 1].arousal)
        if v_delta < delta_threshold and a_delta < delta_threshold:
            if i - 1 not in flat:
                flat.append(i - 1)
            flat.append(i)
    return flat


def cosine_similarity(curve_a: list[float], curve_b: list[float]) -> float:
    """Compute cosine similarity between two curves (same-length lists)."""
    if len(curve_a) != len(curve_b) or not curve_a:
        return 0.0
    dot = sum(a * b for a, b in zip(curve_a, curve_b))
    norm_a = math.sqrt(sum(a * a for a in curve_a))
    norm_b = math.sqrt(sum(b * b for b in curve_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def interpolate_curve(values: list[float], target_len: int) -> list[float]:
    """Linearly interpolate a curve to target_len points for comparison."""
    if not values:
        return [0.0] * target_len
    if len(values) == 1:
        return [values[0]] * target_len
    if len(values) == target_len:
        return list(values)

    result: list[float] = []
    for i in range(target_len):
        pos = i * (len(values) - 1) / (target_len - 1)
        lo = int(pos)
        hi = min(lo + 1, len(values) - 1)
        frac = pos - lo
        result.append(values[lo] * (1 - frac) + values[hi] * frac)
    return result


def compute_corpus_similarity(
    chapter_curve: EmotionCurve,
    reference_curves: list[list[float]],
    target_len: int = 10,
) -> float:
    """Compute max cosine similarity of chapter's valence curve vs reference curves."""
    if not reference_curves or not chapter_curve.scenes:
        return 0.0

    chapter_valences = [s.valence for s in chapter_curve.scenes]
    chapter_interp = interpolate_curve(chapter_valences, target_len)

    max_sim = 0.0
    for ref in reference_curves:
        ref_interp = interpolate_curve(ref, target_len)
        sim = cosine_similarity(chapter_interp, ref_interp)
        if sim > max_sim:
            max_sim = sim
    return max_sim


def curve_to_jsonl_records(curve: EmotionCurve) -> list[dict]:
    """Convert an EmotionCurve to JSONL-ready dicts for data/emotion_curves.jsonl."""
    records = []
    for scene in curve.scenes:
        records.append({
            "chapter": curve.chapter,
            "scene": scene.scene_index,
            "start_char": scene.start_char,
            "end_char": scene.end_char,
            "valence": round(scene.valence, 4),
            "arousal": round(scene.arousal, 4),
            "dominant_emotion": scene.dominant_emotion,
        })
    return records
