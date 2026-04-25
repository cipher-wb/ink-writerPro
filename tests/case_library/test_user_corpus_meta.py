"""US-008: user_corpus history-travel 样例 schema/文件大小/索引校验。

M5 P3 用户扩展接口验证。M2 corpus_chunks 仍 deferred，本测试只验证 meta + 文件 + 索引契约。
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
USER_CORPUS_DIR = REPO_ROOT / "data" / "case_library" / "user_corpus"
HISTORY_TRAVEL_DIR = USER_CORPUS_DIR / "history-travel"


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_meta_yaml_schema_history_travel() -> None:
    meta_path = HISTORY_TRAVEL_DIR / "_meta.yaml"
    assert meta_path.exists(), f"missing {meta_path}"
    meta = _load_yaml(meta_path)

    assert meta.get("genre") == "history-travel"
    assert "license" in meta and isinstance(meta["license"], str)
    assert isinstance(meta.get("files"), list) and len(meta["files"]) >= 1
    for entry in meta["files"]:
        assert isinstance(entry, dict)
        assert "path" in entry and isinstance(entry["path"], str) and entry["path"]
        assert "source" in entry and isinstance(entry["source"], str) and entry["source"]


def test_corpus_files_exist_and_under_size_limit() -> None:
    txt_files = sorted(HISTORY_TRAVEL_DIR.glob("*.txt"))
    assert len(txt_files) >= 2, f"expected ≥ 2 .txt under {HISTORY_TRAVEL_DIR}, got {len(txt_files)}"
    for txt in txt_files:
        text = txt.read_text(encoding="utf-8")
        char_count = len(text)
        assert 100 <= char_count <= 2000, (
            f"{txt.name} char count {char_count} outside fair-use band [100, 2000]"
        )


def test_user_genres_yaml_index() -> None:
    index_path = USER_CORPUS_DIR / "user_genres.yaml"
    assert index_path.exists(), f"missing {index_path}"
    index = _load_yaml(index_path)

    genres = index.get("genres") or {}
    assert "history-travel" in genres, "user_genres.yaml must list history-travel"
    entry = genres["history-travel"]
    assert isinstance(entry, dict)
    assert "path" in entry
    assert "chunks_count" in entry
    assert "last_ingested_at" in entry
