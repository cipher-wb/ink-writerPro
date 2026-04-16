"""Load cultural lexicon entries from genre-specific JSON files."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cultural_lexicon"


@dataclass(frozen=True)
class LexiconEntry:
    id: str
    term: str
    type: str
    category: str
    usage_example: str
    context_hint: str


def load_lexicon(
    genre: str,
    *,
    data_dir: Path | str | None = None,
) -> list[LexiconEntry]:
    """Load all lexicon entries for a genre.

    Returns an empty list if the genre file does not exist.
    """
    if data_dir is None:
        data_dir = DEFAULT_DATA_DIR
    data_dir = Path(data_dir)

    path = data_dir / f"{genre}.json"
    if not path.exists():
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(raw, dict):
        return []

    entries_raw = raw.get("entries", [])
    if not isinstance(entries_raw, list):
        return []

    entries: list[LexiconEntry] = []
    for item in entries_raw:
        if not isinstance(item, dict):
            continue
        entries.append(LexiconEntry(
            id=str(item.get("id", "")),
            term=str(item.get("term", "")),
            type=str(item.get("type", "")),
            category=str(item.get("category", "")),
            usage_example=str(item.get("usage_example", "")),
            context_hint=str(item.get("context_hint", "")),
        ))
    return entries


def sample_lexicon(
    entries: list[LexiconEntry],
    count: int,
    *,
    chapter_no: int = 1,
    seed_offset: int = 42,
    categories: list[str] | None = None,
) -> list[LexiconEntry]:
    """Sample a diverse subset of entries, seeded by chapter number.

    If categories are specified, ensures at least one entry per category
    (when available) before filling remaining slots randomly.
    """
    if not entries or count <= 0:
        return []

    pool = entries
    if categories:
        cat_set = set(categories)
        pool = [e for e in entries if e.category in cat_set] or entries

    rng = random.Random(chapter_no + seed_offset)

    if categories:
        by_cat: dict[str, list[LexiconEntry]] = {}
        for e in pool:
            by_cat.setdefault(e.category, []).append(e)

        selected: list[LexiconEntry] = []
        seen_ids: set[str] = set()
        for cat_entries in by_cat.values():
            pick = rng.choice(cat_entries)
            if pick.id not in seen_ids:
                selected.append(pick)
                seen_ids.add(pick.id)

        remaining = [e for e in pool if e.id not in seen_ids]
        if len(selected) < count and remaining:
            extra = rng.sample(remaining, min(count - len(selected), len(remaining)))
            selected.extend(extra)
        return selected[:count]

    return rng.sample(pool, min(count, len(pool)))
