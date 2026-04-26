"""Live-review 病例向量索引（bge-small-zh-v1.5 + faiss-cpu IndexFlatIP）。

Used by US-LR-011 init-injection genre retrieval.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import faiss
import numpy as np
import yaml
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-zh-v1.5"


@dataclass
class IndexData:
    index: Any
    meta: list[dict]
    model: SentenceTransformer


def _load_case(yaml_path: Path) -> dict | None:
    """Read CASE-LR-*.yaml and extract the fields needed for retrieval."""
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not raw:
        return None
    meta = raw.get("live_review_meta") or {}
    title = meta.get("title_guess", "")
    genre_guess = list(meta.get("genre_guess", []) or [])
    overall = meta.get("overall_comment", "")
    embedding_text = " ".join(filter(None, [title, " ".join(genre_guess), overall]))
    return {
        "case_id": raw.get("case_id"),
        "title_guess": title,
        "genre_guess": genre_guess,
        "overall_comment": overall,
        "verdict": meta.get("verdict"),
        "score": meta.get("score"),
        "source_bvid": meta.get("source_bvid"),
        "embedding_text": embedding_text,
    }


def _iter_case_yaml(cases_dir: Path) -> Iterable[Path]:
    yield from sorted(cases_dir.glob("CASE-LR-*.yaml"))


def build_index(cases_dir: Path, out_dir: Path) -> dict[str, int]:
    """Build FAISS index over CASE-LR-*.yaml files in cases_dir.

    Writes <out_dir>/index.faiss + <out_dir>/meta.jsonl.
    Returns {'cases_indexed': N, 'embedding_dim': D}.
    """
    cases_dir = Path(cases_dir)
    out_dir = Path(out_dir)
    records: list[dict] = []
    for yaml_path in _iter_case_yaml(cases_dir):
        rec = _load_case(yaml_path)
        if rec is None or not rec.get("embedding_text"):
            continue
        records.append(rec)
    if not records:
        raise ValueError(f"no CASE-LR-*.yaml found in {cases_dir}")

    model = SentenceTransformer(MODEL_NAME)
    texts = [r["embedding_text"] for r in records]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    embeddings = np.array(embeddings, dtype=np.float32)
    dim = embeddings.shape[1]

    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    out_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(out_dir / "index.faiss"))
    with (out_dir / "meta.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return {"cases_indexed": len(records), "embedding_dim": int(dim)}


def load_index(index_dir: Path) -> IndexData:
    """Load FAISS + meta.jsonl + sentence-transformers model from index_dir.

    Raises FileNotFoundError if index files are missing.
    """
    index_dir = Path(index_dir)
    faiss_path = index_dir / "index.faiss"
    meta_path = index_dir / "meta.jsonl"
    missing = [p for p in (faiss_path, meta_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Live-review index files missing: {[str(p) for p in missing]}. "
            f"Run scripts/live-review/build_vector_index.py to (re)generate."
        )
    index = faiss.read_index(str(faiss_path))
    with meta_path.open(encoding="utf-8") as f:
        meta = [json.loads(line) for line in f if line.strip()]
    model = SentenceTransformer(MODEL_NAME)
    return IndexData(index=index, meta=meta, model=model)


def search(index_data: IndexData, query: str, top_k: int = 3) -> list[dict]:
    """Return top_k metadata dicts (with cosine_sim) for the query."""
    if not query:
        return []
    q_emb = index_data.model.encode(
        [query], normalize_embeddings=True, show_progress_bar=False
    )
    q_vec = np.array(q_emb, dtype=np.float32).reshape(1, -1)
    k = min(top_k, len(index_data.meta))
    if k == 0:
        return []
    sims, indices = index_data.index.search(q_vec, k)
    out: list[dict] = []
    for sim, idx in zip(sims[0], indices[0]):
        if idx < 0:
            continue
        rec = dict(index_data.meta[idx])
        rec["cosine_sim"] = float(sim)
        out.append(rec)
    return out


__all__ = ["IndexData", "MODEL_NAME", "build_index", "load_index", "search"]
