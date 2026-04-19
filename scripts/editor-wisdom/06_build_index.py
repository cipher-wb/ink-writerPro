#!/usr/bin/env python3
"""Build a local FAISS vector index over editor-wisdom rules using sentence-transformers."""

from __future__ import annotations

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio
_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    '../../ink-writer/scripts',
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass
import json
import sys
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "editor-wisdom"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def build_index(data_dir: Path) -> dict[str, int]:
    rules_path = data_dir / "rules.json"
    rules: list[dict] = json.loads(rules_path.read_text(encoding="utf-8"))

    if not rules:
        raise ValueError("rules.json is empty — nothing to index")

    model = SentenceTransformer(MODEL_NAME)

    texts = [f"{r['rule']} {r['why']}" for r in rules]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    embeddings = np.array(embeddings, dtype=np.float32)

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    index_dir = data_dir / "vector_index"
    index_dir.mkdir(parents=True, exist_ok=True)

    faiss.write_index(index, str(index_dir / "rules.faiss"))

    metadata = [
        {
            "id": r["id"],
            "category": r["category"],
            "rule": r["rule"],
            "why": r["why"],
            "severity": r["severity"],
            "applies_to": r["applies_to"],
            "source_files": r["source_files"],
        }
        for r in rules
    ]
    (index_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {"rules_indexed": len(rules), "embedding_dim": dim}


def main() -> None:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA_DIR

    if not (data_dir / "rules.json").exists():
        print("Error: rules.json not found. Run 05_extract_rules.py first.", file=sys.stderr)
        sys.exit(1)

    stats = build_index(data_dir)
    print(f"Indexed {stats['rules_indexed']} rules (dim={stats['embedding_dim']})")
    print(f"Output: {data_dir / 'vector_index'}/")


if __name__ == "__main__":
    main()
