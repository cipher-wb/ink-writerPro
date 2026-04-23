"""Tests for ink_writer.case_library.ingest.ingest_case."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ink_writer.case_library.ingest import ingest_case
from ink_writer.case_library.store import CaseStore


def _ingest_kwargs(**overrides: object) -> dict:
    base = dict(
        title="主角接到电话 3 秒就不慌，反应不真实",
        raw_text="主角接到电话3秒就不慌了",
        domain="writing_quality",
        layer=["downstream"],
        severity="P1",
        tags=["reader_immersion", "protagonist_reaction"],
        source_type="editor_review",
        ingested_at="2026-04-23",
        failure_description="突发事件→主角理性恢复之间缺情绪缓冲",
        observable=["突发事件后到理性反应之间字符数 < 200"],
    )
    base.update(overrides)
    return base


def test_ingest_creates_case(tmp_path: Path) -> None:
    store = CaseStore(tmp_path / "lib")

    result = ingest_case(store, **_ingest_kwargs())

    assert result.created is True
    assert re.fullmatch(r"CASE-2026-\d{4}", result.case_id)
    assert result.raw_text_hash == hashlib.sha256(
        "主角接到电话3秒就不慌了".encode()
    ).hexdigest()

    # Case YAML is on disk and validates.
    loaded = store.load(result.case_id)
    assert loaded.title == "主角接到电话 3 秒就不慌，反应不真实"
    assert loaded.source.raw_text == "主角接到电话3秒就不慌了"


def test_ingest_same_text_is_deduplicated(tmp_path: Path) -> None:
    store = CaseStore(tmp_path / "lib")

    first = ingest_case(store, **_ingest_kwargs())
    second = ingest_case(store, **_ingest_kwargs(title="different title ignored"))

    assert first.created is True
    assert second.created is False
    assert second.case_id == first.case_id
    assert second.raw_text_hash == first.raw_text_hash

    # Only one YAML on disk.
    assert store.list_ids() == [first.case_id]


def test_ingest_appends_ingest_log(tmp_path: Path) -> None:
    store = CaseStore(tmp_path / "lib")

    result = ingest_case(store, **_ingest_kwargs())

    log_path = tmp_path / "lib" / "ingest_log.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event"] == "ingest"
    assert event["case_id"] == result.case_id
    assert event["raw_text_hash"] == result.raw_text_hash
    assert "at" in event

    # Second (deduped) ingest does NOT append a new log line.
    ingest_case(store, **_ingest_kwargs())
    lines_after = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines_after) == 1
