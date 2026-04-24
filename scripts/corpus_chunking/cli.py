"""``ink corpus`` CLI — ingest / rebuild / watch (M2 US-005).

``main(argv)`` never raises: every failure is translated into a non-zero
return code with a stderr message so shell callers can rely on exit codes.

This module is the only corpus_chunking entry point with ``__main__``; it
invokes ``runtime_compat.enable_windows_utf8_stdio()`` to satisfy the repo
audit red-line. ``rebuild`` and ``watch`` are stubs here — the full
implementations land in US-006 and US-007.

Usage
-----
::

    python -m scripts.corpus_chunking.cli ingest --book 诡秘之主 --dry-run
    python -m scripts.corpus_chunking.cli ingest --resume
    python -m scripts.corpus_chunking.cli ingest --dir /custom/corpus
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# --- sys.path bootstrap so `python -m scripts.corpus_chunking.cli` from any
# cwd can resolve `ink_writer.*` (repo root) and `runtime_compat`
# (ink-writer/scripts), mirroring scripts/qdrant/migrate_faiss_to_qdrant.py.
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
_INK_SCRIPTS = _REPO_ROOT / "ink-writer" / "scripts"
for _candidate in (_REPO_ROOT, _INK_SCRIPTS):
    _sp = str(_candidate)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import yaml  # noqa: E402

from scripts.corpus_chunking.chunk_indexer import IndexerConfig, index_chunks  # noqa: E402
from scripts.corpus_chunking.chunk_tagger import TaggerConfig, tag_chunk  # noqa: E402
from scripts.corpus_chunking.embedding_client import (  # noqa: E402
    EmbeddingClient,
    EmbeddingConfig,
)
from scripts.corpus_chunking.models import SourceType  # noqa: E402
from scripts.corpus_chunking.scene_segmenter import (  # noqa: E402
    SegmenterConfig,
    segment_chapter,
)

DEFAULT_CONFIG = Path("config/corpus_chunking.yaml")
DEFAULT_CORPUS_DIR = Path("benchmark/reference_corpus")
DEFAULT_DATA_DIR = Path("data/corpus_chunks")


# --- config loading ---------------------------------------------------------


def _load_config(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fp:
        return yaml.safe_load(fp) or {}


def _build_segmenter_config(cfg: dict[str, Any]) -> SegmenterConfig:
    s = cfg.get("scene_segmenter", {}) or {}
    return SegmenterConfig(
        model=str(s.get("model", "claude-haiku-4-5-20251001")),
        min_chunk_chars=int(s.get("min_chunk_chars", 200)),
        max_chunk_chars=int(s.get("max_chunk_chars", 800)),
        max_retries=int(s.get("max_retries", 3)),
    )


def _build_tagger_config(cfg: dict[str, Any]) -> TaggerConfig:
    t = cfg.get("chunk_tagger", {}) or {}
    return TaggerConfig(
        model=str(t.get("model", "claude-haiku-4-5-20251001")),
        batch_size=int(t.get("batch_size", 5)),
        quality_weights=dict(t.get("quality_weights", {}) or {}),
        max_retries=int(t.get("max_retries", 3)),
    )


def _build_indexer_config(cfg: dict[str, Any]) -> IndexerConfig:
    i = cfg.get("chunk_indexer", {}) or {}
    return IndexerConfig(
        qdrant_collection=str(i.get("qdrant_collection", "corpus_chunks")),
        upsert_batch_size=int(i.get("upsert_batch_size", 256)),
    )


def _build_embedding_config(cfg: dict[str, Any]) -> EmbeddingConfig:
    i = cfg.get("chunk_indexer", {}) or {}
    return EmbeddingConfig(
        model=str(i.get("embedding_model", "Qwen/Qwen3-Embedding-8B")),
        base_url=str(
            i.get("embedding_base_url", "https://api-inference.modelscope.cn/v1")
        ),
        api_key=os.environ.get("EMBED_API_KEY", ""),
        batch_size=int(i.get("embed_batch_size", 32)),
        max_retries=int(i.get("embed_max_retries", 3)),
    )


# --- client builders (monkey-patched in tests to avoid real network) --------


def _build_anthropic_client() -> Any:
    import anthropic  # type: ignore[import-not-found]

    return anthropic.Anthropic()


def _build_qdrant_client() -> Any:
    from ink_writer.qdrant.client import QdrantConfig, get_client_from_config

    return get_client_from_config(QdrantConfig())


def _build_embedding_client(cfg: dict[str, Any]) -> EmbeddingClient:
    return EmbeddingClient(_build_embedding_config(cfg))


# --- per-book helpers -------------------------------------------------------


def _read_manifest_genre(book_dir: Path) -> list[str]:
    manifest_path = book_dir / "manifest.json"
    if not manifest_path.exists():
        return ["unknown"]
    with open(manifest_path, encoding="utf-8") as fp:
        data = json.load(fp) or {}
    genre = data.get("genre", "unknown")
    if isinstance(genre, list):
        return [str(g) for g in genre]
    return [str(genre)]


def _already_indexed(book: str, chapter: str, raw_path: Path) -> bool:
    """True iff ``chunks_raw.jsonl`` already has a row for this (book, chapter)."""
    if not raw_path.exists():
        return False
    with open(raw_path, encoding="utf-8") as fp:
        for line in fp:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if (
                row.get("source_book") == book
                and row.get("source_chapter") == chapter
            ):
                return True
    return False


@dataclass
class _BookStats:
    chunks: int = 0
    tagged: int = 0
    indexed: int = 0
    failures: int = 0


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fp:
        fp.write(json.dumps(row, ensure_ascii=False))
        fp.write("\n")


def _append_failure(path: Path, book: str, chapter: str, error: str) -> None:
    _append_jsonl(path, {"book": book, "chapter": chapter, "error": error})


def _ingest_book(
    *,
    book_dir: Path,
    data_dir: Path,
    anthropic_client: Any,
    qdrant_client: Any | None,
    embedder: Any | None,
    seg_cfg: SegmenterConfig,
    tag_cfg: TaggerConfig,
    idx_cfg: IndexerConfig,
    resume: bool,
    dry_run: bool,
) -> _BookStats:
    """Process one book dir end-to-end; failures isolated per chapter."""
    book = book_dir.name
    chapters_dir = book_dir / "chapters"
    stats = _BookStats()
    if not chapters_dir.exists():
        return stats
    genre = _read_manifest_genre(book_dir)
    ingested_at = datetime.now(UTC).strftime("%Y-%m-%d")

    raw_path = data_dir / "chunks_raw.jsonl"
    tagged_path = data_dir / "chunks_tagged.jsonl"
    metadata_path = data_dir / "metadata.jsonl"
    failures_path = data_dir / "failures.jsonl"
    unindexed_path = data_dir / "unindexed.jsonl"
    data_dir.mkdir(parents=True, exist_ok=True)

    for chapter_path in sorted(chapters_dir.glob("ch*.txt")):
        chapter = chapter_path.stem
        if resume and _already_indexed(book, chapter, raw_path):
            continue
        try:
            text = chapter_path.read_text(encoding="utf-8")
        except OSError as err:
            _append_failure(failures_path, book, chapter, f"read_error: {err}")
            stats.failures += 1
            continue

        raw_chunks = segment_chapter(
            client=anthropic_client,
            cfg=seg_cfg,
            book=book,
            chapter=chapter,
            text=text,
        )
        if not raw_chunks:
            _append_failure(failures_path, book, chapter, "segment_returned_empty")
            stats.failures += 1
            continue

        stats.chunks += len(raw_chunks)
        for rc in raw_chunks:
            _append_jsonl(raw_path, rc.to_dict())

        tagged_chunks = []
        for rc in raw_chunks:
            tc = tag_chunk(
                client=anthropic_client,
                cfg=tag_cfg,
                chunk=rc,
                genre=genre,
                ingested_at=ingested_at,
                source_type=SourceType.BUILTIN,
            )
            tagged_chunks.append(tc)
            _append_jsonl(tagged_path, tc.to_dict())
        stats.tagged += len(tagged_chunks)

        if not dry_run and qdrant_client is not None and embedder is not None:
            n = index_chunks(
                chunks=tagged_chunks,
                qdrant_client=qdrant_client,
                embedder=embedder,
                cfg=idx_cfg,
                metadata_path=metadata_path,
                unindexed_path=unindexed_path,
            )
            stats.indexed += n

    return stats


# --- sub-commands -----------------------------------------------------------


def _cmd_ingest(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    dir_path = Path(args.dir)
    data_dir = DEFAULT_DATA_DIR
    seg_cfg = _build_segmenter_config(cfg)
    tag_cfg = _build_tagger_config(cfg)
    idx_cfg = _build_indexer_config(cfg)

    anthropic_client = _build_anthropic_client()
    qdrant_client: Any | None = None
    embedder: Any | None = None
    if not args.dry_run:
        qdrant_client = _build_qdrant_client()
        embedder = _build_embedding_client(cfg)

    if args.book:
        book_dirs = [dir_path / args.book]
    elif dir_path.exists():
        book_dirs = sorted(p for p in dir_path.iterdir() if p.is_dir())
    else:
        print(f"corpus dir does not exist: {dir_path}", file=sys.stderr)
        return 2

    total = _BookStats()
    n = len(book_dirs)
    for i, book_dir in enumerate(book_dirs, start=1):
        if not book_dir.exists():
            print(
                f"[{i}/{n}] {book_dir.name:25s} MISSING (skipped)",
                flush=True,
            )
            continue
        s = _ingest_book(
            book_dir=book_dir,
            data_dir=data_dir,
            anthropic_client=anthropic_client,
            qdrant_client=qdrant_client,
            embedder=embedder,
            seg_cfg=seg_cfg,
            tag_cfg=tag_cfg,
            idx_cfg=idx_cfg,
            resume=args.resume,
            dry_run=args.dry_run,
        )
        total.chunks += s.chunks
        total.tagged += s.tagged
        total.indexed += s.indexed
        total.failures += s.failures
        print(
            f"[{i}/{n}] {book_dir.name:25s} "
            f"chunks={s.chunks} tagged={s.tagged} "
            f"indexed={s.indexed} failures={s.failures}",
            flush=True,
        )

    print(
        f"TOTAL chunks={total.chunks} tagged={total.tagged} "
        f"indexed={total.indexed} failures={total.failures}",
        flush=True,
    )
    return 0


_FULL_REBUILD_FILES = (
    "chunks_raw.jsonl",
    "chunks_tagged.jsonl",
    "metadata.jsonl",
    "failures.jsonl",
    "unindexed.jsonl",
)
_PER_BOOK_FILTER_FILES = (
    "chunks_raw.jsonl",
    "chunks_tagged.jsonl",
    "metadata.jsonl",
)


def _filter_jsonl_drop_book(path: Path, book: str) -> None:
    """Rewrite ``path`` keeping only rows where ``source_book != book``.

    Unparseable rows are preserved as-is (safer than silent data loss).
    """
    kept: list[str] = []
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            stripped = line.rstrip("\n")
            if not stripped.strip():
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                kept.append(stripped)
                continue
            if row.get("source_book") != book:
                kept.append(stripped)
    with open(path, "w", encoding="utf-8") as fp:
        for line in kept:
            fp.write(line)
            fp.write("\n")


def _cmd_rebuild(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    if not args.yes:
        print(
            "ERROR: rebuild is destructive; pass --yes to confirm.",
            file=sys.stderr,
        )
        return 2

    data_dir = DEFAULT_DATA_DIR

    if args.book:
        # Per-book path: only filter 3 jsonl files; leave Qdrant collection alone.
        for fname in _PER_BOOK_FILTER_FILES:
            path = data_dir / fname
            if path.is_file():
                _filter_jsonl_drop_book(path, args.book)
    else:
        # Full rebuild: delete 5 jsonl, drop + re-create Qdrant collection.
        for fname in _FULL_REBUILD_FILES:
            path = data_dir / fname
            if path.is_file():
                path.unlink()

        qd = _build_qdrant_client()
        collection = (cfg.get("chunk_indexer") or {}).get(
            "qdrant_collection", "corpus_chunks"
        )
        try:
            qd.delete_collection(collection_name=collection)
        except Exception as err:  # noqa: BLE001 — collection may not exist
            print(f"warn: delete_collection: {err}", file=sys.stderr)
        from ink_writer.qdrant.payload_schema import (
            CORPUS_CHUNKS_SPEC,
            ensure_collection,
        )

        ensure_collection(qd, CORPUS_CHUNKS_SPEC)

    # Re-trigger ingest (full or per-book depending on args.book).
    ing_args = argparse.Namespace(
        dir=DEFAULT_CORPUS_DIR,
        book=args.book,
        resume=False,
        dry_run=False,
    )
    return _cmd_ingest(ing_args, cfg)


def _ingest_single_file(file_path: Path, cfg: dict[str, Any]) -> None:
    """Ingest one chapter file via ``_ingest_book`` in resume mode.

    ``book_dir`` is inferred as ``file_path.parent.parent`` (convention:
    ``<corpus>/<book>/chapters/ch###.txt``). Resume=True skips already-
    indexed chapters so a single-file trigger only processes the new file.
    """
    book_dir = file_path.parent.parent
    data_dir = DEFAULT_DATA_DIR
    seg_cfg = _build_segmenter_config(cfg)
    tag_cfg = _build_tagger_config(cfg)
    idx_cfg = _build_indexer_config(cfg)

    anthropic_client = _build_anthropic_client()
    qdrant_client = _build_qdrant_client()
    embedder = _build_embedding_client(cfg)

    _ingest_book(
        book_dir=book_dir,
        data_dir=data_dir,
        anthropic_client=anthropic_client,
        qdrant_client=qdrant_client,
        embedder=embedder,
        seg_cfg=seg_cfg,
        tag_cfg=tag_cfg,
        idx_cfg=idx_cfg,
        resume=True,
        dry_run=False,
    )


def _cmd_watch(args: argparse.Namespace, cfg: dict[str, Any]) -> int:
    """Polling watcher: detect new/changed ``*.txt`` under ``--dir``.

    ``--iterations`` defaults to -1 (infinite loop). Finite values are for
    tests only so the loop terminates deterministically.
    """
    watch_dir = Path(args.dir)
    if not watch_dir.exists():
        print(f"watch dir does not exist: {watch_dir}", file=sys.stderr)
        return 2

    interval = max(0, int(args.interval))
    iterations = int(args.iterations)
    seen: dict[Path, float] = {}
    loops = 0

    try:
        while iterations < 0 or loops < iterations:
            for txt_path in watch_dir.rglob("*.txt"):
                try:
                    mtime = txt_path.stat().st_mtime
                except OSError:
                    continue
                if seen.get(txt_path) == mtime:
                    continue
                seen[txt_path] = mtime
                try:
                    _ingest_single_file(txt_path, cfg)
                except Exception as err:  # noqa: BLE001 — never abort watcher
                    print(f"warn: ingest failed for {txt_path}: {err}", file=sys.stderr)
            loops += 1
            if iterations < 0 or loops < iterations:
                time.sleep(interval)
    except KeyboardInterrupt:
        print("watch: interrupted, exiting gracefully", file=sys.stderr)
        return 0

    return 0


# --- argparse scaffolding ---------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ink-corpus",
        description="Corpus chunking operator CLI (segment + tag + index).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="YAML config path (default: config/corpus_chunking.yaml)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Segment + tag + index corpus")
    ingest.add_argument("--dir", type=Path, default=DEFAULT_CORPUS_DIR)
    ingest.add_argument("--book", default=None)
    ingest.add_argument("--resume", action="store_true")
    ingest.add_argument("--dry-run", action="store_true")

    rebuild = sub.add_parser("rebuild", help="Drop + re-create corpus_chunks")
    rebuild.add_argument("--yes", action="store_true")
    rebuild.add_argument("--book", default=None)

    watch = sub.add_parser("watch", help="Polling watch of corpus dir")
    watch.add_argument("--dir", type=Path, required=True)
    watch.add_argument("--interval", type=int, default=30)
    watch.add_argument("--iterations", type=int, default=-1)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Top-level entry point. Never raises — returns non-zero on error."""
    try:
        from runtime_compat import enable_windows_utf8_stdio

        enable_windows_utf8_stdio()
    except Exception:  # pragma: no cover — optional helper; Mac/Linux no-op
        pass

    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        return code

    try:
        cfg = _load_config(args.config) if args.config.exists() else {}
        if args.command == "ingest":
            return _cmd_ingest(args, cfg)
        if args.command == "rebuild":
            return _cmd_rebuild(args, cfg)
        if args.command == "watch":
            return _cmd_watch(args, cfg)
        print(f"unknown command: {args.command}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — CLI top-level guard
        print(f"unexpected error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
