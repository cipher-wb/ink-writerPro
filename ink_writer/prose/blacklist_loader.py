"""Load and query the prose directness blacklist (US-003) + 爆款风装逼词三域 (US-002).

The YAML lives at ``ink-writer/assets/prose-blacklist.yaml`` and is consumed by:

* ``writer-agent`` 直白模式（展示前 20 条作反例，US-006）
* ``polish-agent`` 精简 pass（命中删除/替换，US-008/US-003）
* ``directness-checker``（D3 抽象词密度维度，US-005）
* ``scripts/analyze_prose_directness.py``（``--blacklist`` 覆盖种子表）
* ``polish-agent`` simplification_pass（``replacement_map`` 机械替换，PRD US-002/003）

Hot reload
----------
An in-process cache keyed by ``(resolved_path, mtime_ns)`` lets callers re-load
the file without restart — edit YAML, call :func:`load_blacklist` again, and the
updated contents come back. :func:`clear_cache` flushes the cache explicitly for
tests that patch ``mtime_ns`` equality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CATEGORIES: tuple[str, ...] = (
    "abstract_adjectives",
    "empty_phrases",
    "pretentious_metaphors",
    "pretentious_verbs",
    "pretentious_nouns",
    "pretentious_adverbs",
)

DEFAULT_BLACKLIST_PATH = (
    Path(__file__).resolve().parent.parent.parent / "ink-writer" / "assets" / "prose-blacklist.yaml"
)


@dataclass(frozen=True)
class BlacklistEntry:
    """One blacklisted word/phrase plus a showing-replacement hint."""

    word: str
    category: str
    replacement: str


@dataclass(frozen=True)
class ReplacementMap:
    """Bidirectional view of 装逼词 → 爆款替换 (PRD US-002).

    ``forward`` maps a blacklisted source word to an ordered tuple of popular
    replacements (first item is the polish-agent default). ``reverse`` maps any
    replacement word back to the source words that suggest it (a single
    replacement may serve multiple originals — e.g. ``盯着`` is suggested by
    both ``凝视`` and ``凝望``).
    """

    forward: dict[str, tuple[str, ...]] = field(default_factory=dict)
    reverse: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def lookup(self, word: str) -> tuple[str, ...]:
        """Forward query: ``凝视`` → ``("盯着", "看着", "死盯")``. Empty if absent."""
        return self.forward.get(word, ())

    def origins(self, replacement: str) -> tuple[str, ...]:
        """Reverse query: ``盯着`` → ``("凝视", "凝望", ...)``. Empty if absent."""
        return self.reverse.get(replacement, ())

    def words(self) -> tuple[str, ...]:
        """Source words (forward keys), order preserved from YAML."""
        return tuple(self.forward.keys())

    def __len__(self) -> int:
        return len(self.forward)

    def __bool__(self) -> bool:
        return bool(self.forward)


@dataclass(frozen=True)
class Blacklist:
    """Immutable bundle of all blacklist entries grouped by category."""

    version: int
    entries: tuple[BlacklistEntry, ...]
    replacement_map: ReplacementMap = field(default_factory=ReplacementMap)

    @property
    def abstract_adjectives(self) -> tuple[BlacklistEntry, ...]:
        return tuple(e for e in self.entries if e.category == "abstract_adjectives")

    @property
    def empty_phrases(self) -> tuple[BlacklistEntry, ...]:
        return tuple(e for e in self.entries if e.category == "empty_phrases")

    @property
    def pretentious_metaphors(self) -> tuple[BlacklistEntry, ...]:
        return tuple(e for e in self.entries if e.category == "pretentious_metaphors")

    @property
    def pretentious_verbs(self) -> tuple[BlacklistEntry, ...]:
        return tuple(e for e in self.entries if e.category == "pretentious_verbs")

    @property
    def pretentious_nouns(self) -> tuple[BlacklistEntry, ...]:
        return tuple(e for e in self.entries if e.category == "pretentious_nouns")

    @property
    def pretentious_adverbs(self) -> tuple[BlacklistEntry, ...]:
        return tuple(e for e in self.entries if e.category == "pretentious_adverbs")

    def words(self, category: str | None = None) -> tuple[str, ...]:
        """Flat list of words, optionally filtered by category."""
        if category is None:
            return tuple(e.word for e in self.entries)
        if category not in CATEGORIES:
            raise ValueError(f"unknown category: {category!r}; expected one of {CATEGORIES}")
        return tuple(e.word for e in self.entries if e.category == category)

    def match(self, text: str) -> list[tuple[BlacklistEntry, int]]:
        """Return ``(entry, hit_count)`` pairs for entries whose word appears in ``text``.

        Multi-character Chinese phrases use :meth:`str.count` which handles overlap
        safely for the expected corpus (phrases don't self-overlap in practice).
        ``"…"`` in an entry word is treated as a wildcard-like placeholder: the
        surrounding tokens are matched as separate substrings (both must appear),
        and the count is the min of the two.
        """
        hits: list[tuple[BlacklistEntry, int]] = []
        for entry in self.entries:
            count = _count_occurrences(text, entry.word)
            if count > 0:
                hits.append((entry, count))
        return hits


_CACHE: dict[tuple[str, int], Blacklist] = {}


def clear_cache() -> None:
    """Drop cached blacklists. Test helper + manual invalidation."""
    _CACHE.clear()


def load_blacklist(path: Path | str | None = None) -> Blacklist:
    """Load and cache a blacklist YAML.

    Returns an empty :class:`Blacklist` (version=0) if the file is missing,
    unreadable, or structurally invalid. Cache key is ``(resolved_path,
    mtime_ns)`` so editing the file transparently refreshes subsequent loads.
    """
    target = Path(path) if path is not None else DEFAULT_BLACKLIST_PATH
    if not target.exists() or not target.is_file():
        return _empty()

    try:
        resolved = str(target.resolve())
        mtime_ns = target.stat().st_mtime_ns
    except OSError:
        return _empty()

    cache_key = (resolved, mtime_ns)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        import yaml
    except ImportError:
        return _empty()

    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError, UnicodeDecodeError):
        return _empty()

    if not isinstance(raw, dict):
        return _empty()

    version_raw = raw.get("version", 0)
    try:
        version = int(version_raw)
    except (TypeError, ValueError):
        version = 0

    entries: list[BlacklistEntry] = []
    for category in CATEGORIES:
        section = raw.get(category)
        if not isinstance(section, list):
            continue
        for item in section:
            entry = _parse_entry(item, category)
            if entry is not None:
                entries.append(entry)

    replacement_map = _parse_replacement_map(raw.get("replacement_map"))

    bundle = Blacklist(
        version=version,
        entries=tuple(entries),
        replacement_map=replacement_map,
    )
    _CACHE[cache_key] = bundle
    return bundle


# ---------------------------------------------------------------------------
# Convenience loaders for new categories (PRD US-002 验收点)
# ---------------------------------------------------------------------------


def load_pretentious_verbs(path: Path | str | None = None) -> tuple[BlacklistEntry, ...]:
    """Just the ``pretentious_verbs`` slice of the shipped (or custom) YAML."""
    return load_blacklist(path).pretentious_verbs


def load_pretentious_nouns(path: Path | str | None = None) -> tuple[BlacklistEntry, ...]:
    """Just the ``pretentious_nouns`` slice."""
    return load_blacklist(path).pretentious_nouns


def load_pretentious_adverbs(path: Path | str | None = None) -> tuple[BlacklistEntry, ...]:
    """Just the ``pretentious_adverbs`` slice."""
    return load_blacklist(path).pretentious_adverbs


def load_replacement_map(path: Path | str | None = None) -> ReplacementMap:
    """Just the ``replacement_map`` section, with both forward + reverse indices."""
    return load_blacklist(path).replacement_map


def _parse_entry(item: Any, category: str) -> BlacklistEntry | None:
    """Parse one YAML list item into :class:`BlacklistEntry`.

    Accepts either a bare string (no replacement) or ``{word, replacement}`` dict.
    Empty / malformed entries are dropped.
    """
    if isinstance(item, str):
        word = item.strip()
        if not word:
            return None
        return BlacklistEntry(word=word, category=category, replacement="")
    if isinstance(item, dict):
        word_raw = item.get("word", "")
        word = str(word_raw).strip() if word_raw is not None else ""
        if not word:
            return None
        replacement_raw = item.get("replacement", "")
        replacement = str(replacement_raw).strip() if replacement_raw is not None else ""
        return BlacklistEntry(word=word, category=category, replacement=replacement)
    return None


def _parse_replacement_map(raw: Any) -> ReplacementMap:
    """Parse the ``replacement_map`` YAML dict into bidirectional indices.

    Accepted value shapes per key:
        - list of strings: each becomes one replacement
        - single string: becomes a one-element replacement tuple
        - everything else (None, dict, etc.): silently dropped
    Empty or whitespace-only words / replacements are skipped. Reverse map is
    built such that ``reverse[r]`` lists every source word for which ``r``
    appeared as a replacement (order = first-seen, dedup'd).
    """
    if not isinstance(raw, dict):
        return ReplacementMap()

    forward: dict[str, tuple[str, ...]] = {}
    reverse_lists: dict[str, list[str]] = {}

    for key, value in raw.items():
        word = str(key).strip() if key is not None else ""
        if not word:
            continue

        if isinstance(value, list):
            replacements = tuple(
                str(item).strip()
                for item in value
                if item is not None and str(item).strip()
            )
        elif isinstance(value, str):
            cleaned = value.strip()
            replacements = (cleaned,) if cleaned else ()
        else:
            replacements = ()

        if not replacements:
            continue

        forward[word] = replacements
        for replacement in replacements:
            bucket = reverse_lists.setdefault(replacement, [])
            if word not in bucket:
                bucket.append(word)

    reverse = {r: tuple(srcs) for r, srcs in reverse_lists.items()}
    return ReplacementMap(forward=forward, reverse=reverse)


def _empty() -> Blacklist:
    return Blacklist(version=0, entries=(), replacement_map=ReplacementMap())


def _count_occurrences(text: str, word: str) -> int:
    """Count occurrences of ``word`` in ``text``; handles ``…`` as a soft wildcard."""
    if not word or not text:
        return 0
    if "…" not in word and "..." not in word:
        return text.count(word)

    placeholder = "…" if "…" in word else "..."
    parts = [p for p in word.split(placeholder) if p]
    if not parts:
        return 0
    # Each part must appear; hit count = min across parts. Avoids false-positive
    # explosion when one fragment is very common.
    return min(text.count(p) for p in parts)
