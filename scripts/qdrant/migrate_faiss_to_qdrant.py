#!/usr/bin/env python3
"""Migrate a FAISS index + metadata.jsonl into a Qdrant collection (M1 US-013).

Pairs with :mod:`ink_writer.qdrant.payload_schema` :class:`CollectionSpec`.
Idempotent: re-running upserts points with the same UUID5-derived ids so
``points_count`` stays stable.

The ``metadata.jsonl`` format is one JSON object per line. Each object MUST
contain an ``id`` field used as the *original* point id; remaining keys are
written verbatim into the Qdrant payload (plus ``original_id`` mirroring the
source id, so callers can look points up without decoding the UUID).
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# --- sys.path bootstrap so `python scripts/qdrant/migrate_faiss_to_qdrant.py`
# can resolve `ink_writer.*` (repo root) and `runtime_compat` (ink-writer/scripts)
# exactly the way the other scripts/<subdir>/*.py entries do.
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
_INK_SCRIPTS = _REPO_ROOT / "ink-writer" / "scripts"
for _candidate in (_REPO_ROOT, _INK_SCRIPTS):
    _sp = str(_candidate)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import faiss  # noqa: E402
import numpy as np  # noqa: E402
from ink_writer.qdrant.client import QdrantConfig, get_client_from_config  # noqa: E402
from ink_writer.qdrant.payload_schema import (  # noqa: E402
    CORPUS_CHUNKS_SPEC,
    EDITOR_WISDOM_RULES_SPEC,
    CollectionSpec,
    ensure_collection,
)
from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.http import models as rest  # noqa: E402


@dataclass(frozen=True)
class MigrationReport:
    """Summary of a single migration run."""

    collection: str
    uploaded: int
    skipped: int = 0


def _load_metadata(jsonl_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(jsonl_path, encoding="utf-8") as fp:
        for line in fp:
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
    return rows


def _stable_uuid_from_id(string_id: str) -> str:
    """Map an arbitrary string id to a deterministic UUID5.

    Qdrant accepts either int or UUID strings as point ids; UUID5 keeps the
    mapping stable across runs so re-running the script upserts the same
    points (idempotent).
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, string_id))


def migrate_faiss_index(
    client: QdrantClient,
    spec: CollectionSpec,
    faiss_index_path: Path,
    metadata_jsonl: Path,
    batch_size: int = 256,
) -> MigrationReport:
    """Upsert every FAISS vector into the Qdrant *spec* collection.

    Refuses to proceed (``ValueError``) if ``index.ntotal`` disagrees with the
    jsonl row count; half-migrations are worse than no migration.
    """

    ensure_collection(client, spec)

    index = faiss.read_index(str(faiss_index_path))
    n = index.ntotal
    metadata = _load_metadata(metadata_jsonl)
    if len(metadata) != n:
        raise ValueError(
            f"FAISS ntotal={n} != metadata rows={len(metadata)}; refusing to migrate."
        )

    vectors = np.zeros((n, index.d), dtype=np.float32)
    index.reconstruct_n(0, n, vectors)

    uploaded = 0
    for start in range(0, n, batch_size):
        end = min(start + batch_size, n)
        points: list[rest.PointStruct] = []
        for i in range(start, end):
            row = metadata[i]
            raw_id = row.get("id")
            if raw_id is None:
                raise ValueError(f"metadata row {i} missing 'id' field")
            string_id = str(raw_id)
            if not string_id:
                raise ValueError(f"metadata row {i} has empty 'id' field")
            payload = {k: v for k, v in row.items() if k != "id"}
            payload["original_id"] = string_id
            points.append(
                rest.PointStruct(
                    id=_stable_uuid_from_id(string_id),
                    vector=vectors[i].tolist(),
                    payload=payload,
                )
            )
        client.upsert(collection_name=spec.name, points=points)
        uploaded += len(points)

    return MigrationReport(collection=spec.name, uploaded=uploaded)


_PRESETS: dict[str, CollectionSpec] = {
    "editor_wisdom_rules": EDITOR_WISDOM_RULES_SPEC,
    "corpus_chunks": CORPUS_CHUNKS_SPEC,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preset",
        choices=sorted(_PRESETS.keys()),
        required=True,
        help="Target CollectionSpec preset.",
    )
    parser.add_argument("--faiss-index", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--qdrant-host", default="127.0.0.1")
    parser.add_argument("--qdrant-port", type=int, default=6333)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        from runtime_compat import enable_windows_utf8_stdio

        enable_windows_utf8_stdio()
    except Exception:  # pragma: no cover — optional helper; Mac/Linux no-op
        pass

    args = _build_parser().parse_args(argv)

    client = get_client_from_config(
        QdrantConfig(host=args.qdrant_host, port=args.qdrant_port)
    )
    report = migrate_faiss_index(
        client=client,
        spec=_PRESETS[args.preset],
        faiss_index_path=args.faiss_index,
        metadata_jsonl=args.metadata,
    )
    print(f"collection={report.collection} uploaded={report.uploaded}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
