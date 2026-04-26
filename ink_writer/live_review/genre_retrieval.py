"""Genre-aware semantic retrieval over live-review CASE-LR cases.

Used by US-LR-011 ink-init Step 99.5 + US-LR-012 ink-review Step 3.6.
"""
from __future__ import annotations

from pathlib import Path

from ink_writer.live_review._vector_index import IndexData, load_index, search

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX_DIR = _REPO_ROOT / "data" / "live-review" / "vector_index"

_INDEX_CACHE: dict[str, IndexData] = {}


def _get_index(index_dir: Path) -> IndexData:
    """Process-level cache to avoid reloading bge model + faiss index."""
    key = str(Path(index_dir).resolve())
    if key not in _INDEX_CACHE:
        _INDEX_CACHE[key] = load_index(index_dir)
    return _INDEX_CACHE[key]


def clear_index_cache() -> None:
    """Test hook: clear module-level cache."""
    _INDEX_CACHE.clear()


def retrieve_similar_cases(
    query: str,
    top_k: int = 3,
    *,
    index_dir: Path | None = None,
) -> list[dict]:
    """Return top_k similar cases for the query string.

    Each result dict contains: case_id / title_guess / genre_guess / verdict /
    score / overall_comment / source_bvid / cosine_sim.
    """
    idx_dir = Path(index_dir) if index_dir is not None else DEFAULT_INDEX_DIR
    index_data = _get_index(idx_dir)
    return search(index_data, query, top_k=top_k)


__all__ = ["DEFAULT_INDEX_DIR", "retrieve_similar_cases", "clear_index_cache"]
