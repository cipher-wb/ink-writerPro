"""US-008: polish-agent Simplification Pass helper.

A deterministic, rule-based 精简 pass that removes prose directness "噪音"
from a paragraph of text while preserving剧情 facts. Designed as a companion
to the LLM-driven simplification instructions documented in
``ink-writer/agents/polish-agent.md`` → ``## Simplification Pass``.

Activation单源: reuses :func:`ink_writer.prose.directness_checker.is_activated`
so writer / directness-checker / polish-agent share one source of truth for
"is this scene in Directness Mode".

Rules applied (PRD US-008 AC):

1. 黑名单命中词: :mod:`ink_writer.prose.blacklist_loader` 的 ``abstract_adjectives``
   条目 → 直接删除 (LLM prompt 会做更细的替换;这里只做硬删除确保 hit_count
   清零)。``empty_phrases`` / ``pretentious_metaphors`` 的处理交给 LLM prompt
   (replacement 字段是启发式建议而非可直接插入的字符串)。
2. 长句拆分: 单句 > ``max_sentence_len`` 字时按句中逗号/分号尝试拆为两句,拆
   后两段均 ≤ ``max_sentence_len``。
3. 连续 ≥2 个修辞格(比喻/拟人/排比标记词): 连续命中时保留第一处,删除后续。
4. 空描写段: 纯环境/无人称代词的段落 > 3 句 → 压缩到首尾 2 句。
5. 70% 字数下限保护: 若精简后字数 < ``min_retention_ratio`` × 原字数, 回滚
   到原文 (防过度删减损失剧情信息)。

The helper is **conservative by design**: it will only drop characters, never
add or rephrase. LLM-level rewrites (e.g. 形容词→动词+细节) remain the
polish-agent's job — this helper is the programmable deterministic floor.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from ink_writer.prose.blacklist_loader import Blacklist, load_blacklist
from ink_writer.prose.directness_checker import is_activated as _directness_is_activated

# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------


def should_activate_simplification(scene_mode: str | None, chapter_no: int = 0) -> bool:
    """Return ``True`` iff polish-agent should run the simplification pass.

    Delegates to :func:`ink_writer.prose.directness_checker.is_activated` so
    that writer-agent / directness-checker / polish-agent activation判定
    永远一致 (see Codebase Patterns "场景激活判定单源").
    """
    return _directness_is_activated(scene_mode, int(chapter_no or 0))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimplificationReport:
    """Result of :func:`simplify_text`; always frozen for safe caller storage."""

    simplified_text: str
    original_char_count: int
    simplified_char_count: int
    blacklist_hits_before: int
    blacklist_hits_after: int
    rolled_back: bool
    rules_fired: tuple[str, ...] = field(default_factory=tuple)

    @property
    def reduction_ratio(self) -> float:
        """Fraction of原文 **removed** (0.0 = 无变化; 0.2 = -20%)."""
        if self.original_char_count == 0:
            return 0.0
        return 1.0 - (self.simplified_char_count / self.original_char_count)


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

_SENTENCE_TERMINATORS = "。！？!?.…"
_RHETORIC_MARKERS: tuple[str, ...] = (
    "仿佛",
    "宛如",
    "犹如",
    "好似",
    "恍若",
    "仿若",
    "如同",
    "似乎",
)
_PRONOUN_MARKERS: tuple[str, ...] = (
    "他",
    "她",
    "我",
    "你",
    "咱",
    "它",
    "们",
)
_DIALOGUE_QUOTES: tuple[str, ...] = (
    "\u201c",  # "
    "\u201d",  # "
    "\u300c",  # 「
    "\u300d",  # 」
)


def simplify_text(
    text: str,
    *,
    blacklist: Blacklist | None = None,
    max_sentence_len: int = 35,
    split_target_len: int = 20,
    empty_paragraph_sentence_floor: int = 3,
    min_retention_ratio: float = 0.70,
) -> SimplificationReport:
    """Apply the deterministic Simplification Pass rules to ``text``.

    Parameters
    ----------
    text:
        Raw chapter paragraph(s). Preserves paragraph boundaries (``\n\n``).
    blacklist:
        Override for the shipped ``prose-blacklist.yaml``. Defaults to the
        cached result of :func:`load_blacklist` (ships with 107 entries).
    max_sentence_len:
        PRD US-008: 句长 > 35 字 → 拆为 ≤ 20 字短句候选。
    split_target_len:
        Target maximum length for split halves.
    empty_paragraph_sentence_floor:
        PRD US-008: 空描写段 > 3 句时压缩到 2 句。
    min_retention_ratio:
        70% 字数下限;低于则回滚 (过度精简保护)。

    Returns
    -------
    SimplificationReport
        Immutable record including character counts, blacklist hits before /
        after, rules fired, and the possibly-simplified text (or original if
        rollback triggered).
    """
    if not text:
        return SimplificationReport(
            simplified_text=text,
            original_char_count=0,
            simplified_char_count=0,
            blacklist_hits_before=0,
            blacklist_hits_after=0,
            rolled_back=False,
            rules_fired=(),
        )

    if blacklist is None:
        blacklist = load_blacklist()

    original = text
    original_len = len(original)
    hits_before = _count_total_hits(original, blacklist)

    rules_fired: list[str] = []
    current = original

    # Rule 1: drop abstract_adjective blacklist words verbatim (safe deletion).
    current_after_blacklist = _strip_abstract_adjectives(current, blacklist)
    if current_after_blacklist != current:
        rules_fired.append("blacklist_abstract_drop")
        current = current_after_blacklist

    # Rule 4: compress pure-environment paragraphs > 3 sentences to 2.
    current_after_empty = _compress_empty_paragraphs(current, empty_paragraph_sentence_floor)
    if current_after_empty != current:
        rules_fired.append("empty_paragraph_compress")
        current = current_after_empty

    # Rule 3: collapse consecutive rhetoric markers (keep first, drop rest).
    current_after_rhetoric = _collapse_consecutive_rhetoric(current)
    if current_after_rhetoric != current:
        rules_fired.append("rhetoric_collapse")
        current = current_after_rhetoric

    # Rule 2: split long sentences > max_sentence_len.
    current_after_split = _split_long_sentences(current, max_sentence_len, split_target_len)
    if current_after_split != current:
        rules_fired.append("long_sentence_split")
        current = current_after_split

    simplified_len = len(current)
    hits_after = _count_total_hits(current, blacklist)

    # 70% floor safety rollback.
    if original_len > 0 and simplified_len < original_len * min_retention_ratio:
        return SimplificationReport(
            simplified_text=original,
            original_char_count=original_len,
            simplified_char_count=original_len,
            blacklist_hits_before=hits_before,
            blacklist_hits_after=hits_before,
            rolled_back=True,
            rules_fired=tuple(rules_fired),
        )

    return SimplificationReport(
        simplified_text=current,
        original_char_count=original_len,
        simplified_char_count=simplified_len,
        blacklist_hits_before=hits_before,
        blacklist_hits_after=hits_after,
        rolled_back=False,
        rules_fired=tuple(rules_fired),
    )


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------


def _count_total_hits(text: str, blacklist: Blacklist) -> int:
    return sum(count for _, count in blacklist.match(text))


def _strip_abstract_adjectives(text: str, blacklist: Blacklist) -> str:
    """Remove abstract_adjectives literal substrings. Order: longest-first."""
    words = sorted(
        {entry.word for entry in blacklist.abstract_adjectives if "\u2026" not in entry.word},
        key=len,
        reverse=True,
    )
    out = text
    for word in words:
        if word and word in out:
            out = out.replace(word, "")
    return out


def _split_long_sentences(text: str, max_len: int, target_len: int) -> str:
    """Split sentences > ``max_len`` into two by the mid-nearest comma.

    Preserves paragraph structure. A "sentence" is anything between two
    terminators in ``_SENTENCE_TERMINATORS``. If no comma exists the sentence
    is left untouched (deterministic splitter — LLM handles hard cases).
    """
    if max_len <= 0:
        return text

    paragraphs = text.split("\n")
    out_paragraphs: list[str] = []
    for paragraph in paragraphs:
        sentences = _split_sentences_keep_terminators(paragraph)
        rebuilt: list[str] = []
        for chunk in sentences:
            body, terminator = _peel_terminator(chunk)
            if len(body) > max_len:
                split = _split_by_comma_near_midpoint(body, target_len)
                if split is not None:
                    left, right = split
                    rebuilt.append(left + "。")
                    rebuilt.append(right + terminator)
                    continue
            rebuilt.append(chunk)
        out_paragraphs.append("".join(rebuilt))
    return "\n".join(out_paragraphs)


def _split_sentences_keep_terminators(paragraph: str) -> list[str]:
    """Split ``paragraph`` on sentence terminators, keeping terminators attached."""
    if not paragraph:
        return [""]
    pattern = f"[^{re.escape(_SENTENCE_TERMINATORS)}]+[{re.escape(_SENTENCE_TERMINATORS)}]?"
    matches = re.findall(pattern, paragraph)
    return matches if matches else [paragraph]


def _peel_terminator(chunk: str) -> tuple[str, str]:
    if chunk and chunk[-1] in _SENTENCE_TERMINATORS:
        return chunk[:-1], chunk[-1]
    return chunk, ""


def _split_by_comma_near_midpoint(body: str, target_len: int) -> tuple[str, str] | None:
    """Find the comma closest to midpoint yielding two halves ≤ target_len where possible."""
    comma_indices = [i for i, ch in enumerate(body) if ch in "，,；;"]
    if not comma_indices:
        return None
    midpoint = len(body) // 2
    comma_indices.sort(key=lambda i: abs(i - midpoint))
    for idx in comma_indices:
        left = body[:idx].rstrip("，,；; ")
        right = body[idx + 1:].lstrip("，,；; ")
        if not left or not right:
            continue
        if len(left) <= target_len and len(right) <= target_len:
            return left, right
    # fallback: any valid comma split even if halves exceed target_len
    idx = comma_indices[0]
    left = body[:idx].rstrip("，,；; ")
    right = body[idx + 1:].lstrip("，,；; ")
    if left and right:
        return left, right
    return None


def _collapse_consecutive_rhetoric(text: str) -> str:
    """Within each sentence, keep the first rhetoric marker; drop later ones."""
    paragraphs = text.split("\n")
    out: list[str] = []
    for paragraph in paragraphs:
        sentences = _split_sentences_keep_terminators(paragraph)
        collapsed_sentences: list[str] = []
        for chunk in sentences:
            collapsed_sentences.append(_collapse_rhetoric_in_sentence(chunk))
        out.append("".join(collapsed_sentences))
    return "\n".join(out)


def _collapse_rhetoric_in_sentence(sentence: str) -> str:
    """Remove 2nd+ occurrences of any rhetoric marker in a single sentence."""
    seen: set[str] = set()
    result = sentence
    # Find markers in first-occurrence order
    ordered_marker_positions: list[tuple[int, str]] = []
    for marker in _RHETORIC_MARKERS:
        start = 0
        while True:
            idx = result.find(marker, start)
            if idx < 0:
                break
            ordered_marker_positions.append((idx, marker))
            start = idx + len(marker)
    ordered_marker_positions.sort()
    # Walk left-to-right; for each marker's 2nd+ appearance, delete a single
    # instance by locating via find-from-cursor.
    cursor = 0
    rebuilt_parts: list[str] = []
    removed_marker_instances: dict[str, int] = {}
    for idx, marker in ordered_marker_positions:
        if idx < cursor:
            continue  # already absorbed by prior removal
        rebuilt_parts.append(result[cursor:idx])
        if marker in seen:
            removed_marker_instances[marker] = removed_marker_instances.get(marker, 0) + 1
            cursor = idx + len(marker)  # skip the marker
        else:
            rebuilt_parts.append(marker)
            seen.add(marker)
            cursor = idx + len(marker)
    rebuilt_parts.append(result[cursor:])
    return "".join(rebuilt_parts)


def _compress_empty_paragraphs(text: str, sentence_floor: int) -> str:
    """For paragraphs > ``sentence_floor`` sentences and无对话/人称代词, keep first + last sentence."""
    paragraphs = text.split("\n\n")
    out: list[str] = []
    for para in paragraphs:
        if _is_empty_description_paragraph(para, sentence_floor):
            sentences = _split_sentences_keep_terminators(para)
            non_empty = [s for s in sentences if s.strip()]
            if len(non_empty) > 2:
                compressed = non_empty[0] + non_empty[-1]
                out.append(compressed)
                continue
        out.append(para)
    return "\n\n".join(out)


def _is_empty_description_paragraph(paragraph: str, sentence_floor: int) -> bool:
    if not paragraph.strip():
        return False
    if _contains_any(paragraph, _DIALOGUE_QUOTES):
        return False
    if _contains_any(paragraph, _PRONOUN_MARKERS):
        return False
    sentences = [s for s in _split_sentences_keep_terminators(paragraph) if s.strip()]
    return len(sentences) > sentence_floor


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(n in text for n in needles)


__all__ = [
    "SimplificationReport",
    "should_activate_simplification",
    "simplify_text",
]
