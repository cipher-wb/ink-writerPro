"""Load and query the prose directness blacklist (US-003).

The YAML lives at ``ink-writer/assets/prose-blacklist.yaml`` and is consumed by:

* ``writer-agent`` 直白模式（展示前 20 条作反例，US-006）
* ``polish-agent`` 精简 pass（命中删除/替换，US-008）
* ``directness-checker``（D3 抽象词密度维度，US-005）
* ``scripts/analyze_prose_directness.py``（``--blacklist`` 覆盖种子表）

Hot reload
----------
An in-process cache keyed by ``(resolved_path, mtime_ns)`` lets callers re-load
the file without restart — edit YAML, call :func:`load_blacklist` again, and the
updated contents come back. :func:`clear_cache` flushes the cache explicitly for
tests that patch ``mtime_ns`` equality.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

CATEGORIES: tuple[str, ...] = (
    "abstract_adjectives",
    "empty_phrases",
    "pretentious_metaphors",
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
class Blacklist:
    """Immutable bundle of all blacklist entries grouped by category."""

    version: int
    entries: tuple[BlacklistEntry, ...]

    @property
    def abstract_adjectives(self) -> tuple[BlacklistEntry, ...]:
        return tuple(e for e in self.entries if e.category == "abstract_adjectives")

    @property
    def empty_phrases(self) -> tuple[BlacklistEntry, ...]:
        return tuple(e for e in self.entries if e.category == "empty_phrases")

    @property
    def pretentious_metaphors(self) -> tuple[BlacklistEntry, ...]:
        return tuple(e for e in self.entries if e.category == "pretentious_metaphors")

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

    bundle = Blacklist(version=version, entries=tuple(entries))
    _CACHE[cache_key] = bundle
    return bundle


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


def _empty() -> Blacklist:
    return Blacklist(version=0, entries=())


def _count_occurrences(text: str, word: str) -> int:
    """Count occurrences of ``word`` in ``text``; handles ``…`` as a soft wildcard."""
    if not word or not text:
        return 0
    if "\u2026" not in word and "..." not in word:
        return text.count(word)

    placeholder = "\u2026" if "\u2026" in word else "..."
    parts = [p for p in word.split(placeholder) if p]
    if not parts:
        return 0
    # Each part must appear; hit count = min across parts. Avoids false-positive
    # explosion when one fragment is very common.
    return min(text.count(p) for p in parts)
