"""US-011 tests — ``approve --batch <yaml>`` CLI subcommand."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from ink_writer.case_library.cli import main
from ink_writer.case_library.ingest import ingest_case
from ink_writer.case_library.store import CaseStore


def _make_pending_case(store: CaseStore, *, raw_text: str, title: str) -> str:
    result = ingest_case(
        store,
        title=title,
        raw_text=raw_text,
        domain="writing_quality",
        layer=["downstream"],
        severity="P2",
        tags=["from_editor_wisdom", "opening"],
        source_type="editor_review",
        ingested_at="2026-04-24",
        failure_description=f"desc for {title}",
        observable=[f"placeholder {title}"],
        initial_status="pending",
    )
    assert result.created, "fixture should always create a fresh case"
    return result.case_id


def test_approve_batch_three_actions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library_root = tmp_path / "lib"
    store = CaseStore(library_root)
    id1 = _make_pending_case(store, raw_text="r1 | w1", title="t1")
    id2 = _make_pending_case(store, raw_text="r2 | w2", title="t2")
    id3 = _make_pending_case(store, raw_text="r3 | w3", title="t3")

    batch = {
        "approvals": [
            {"case_id": id1, "action": "approve", "note": "hard rule, ship it"},
            {"case_id": id2, "action": "reject"},
            {"case_id": id3, "action": "defer", "note": "revisit in M3"},
        ]
    }
    batch_path = tmp_path / "batch.yaml"
    batch_path.write_text(yaml.safe_dump(batch, allow_unicode=True), encoding="utf-8")

    rc = main(
        [
            "--library-root",
            str(library_root),
            "approve",
            "--batch",
            str(batch_path),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "applied=3" in out
    assert "failed=0" in out

    # Verify each case status transitioned correctly.
    assert store.load(id1).status.value == "active"
    assert store.load(id2).status.value == "retired"
    assert store.load(id3).status.value == "pending"

    # ingest_log.jsonl should contain 3 approval events (plus 3 ingest events).
    log_lines = store.ingest_log_path.read_text(encoding="utf-8").strip().splitlines()
    approval_events = [
        json.loads(line) for line in log_lines if '"event": "approval"' in line
    ]
    assert len(approval_events) == 3
    actions_by_id = {ev["case_id"]: ev["action"] for ev in approval_events}
    assert actions_by_id == {id1: "approve", id2: "reject", id3: "defer"}
    # notes preserved where provided
    notes_by_id = {ev["case_id"]: ev.get("note") for ev in approval_events}
    assert notes_by_id[id1] == "hard rule, ship it"
    assert notes_by_id[id3] == "revisit in M3"
    assert "note" not in next(ev for ev in approval_events if ev["case_id"] == id2)


def test_approve_batch_invalid_yaml_returns_3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library_root = tmp_path / "lib"
    CaseStore(library_root)  # ensure root exists

    # Missing required "action" field.
    bad_batch = {"approvals": [{"case_id": "CASE-2026-0001"}]}
    batch_path = tmp_path / "bad.yaml"
    batch_path.write_text(yaml.safe_dump(bad_batch), encoding="utf-8")

    rc = main(
        [
            "--library-root",
            str(library_root),
            "approve",
            "--batch",
            str(batch_path),
        ]
    )
    err = capsys.readouterr().err
    assert rc == 3
    assert "schema violation" in err


def test_approve_batch_unknown_case_records_failure_continues(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library_root = tmp_path / "lib"
    store = CaseStore(library_root)
    real_id = _make_pending_case(store, raw_text="r1 | w1", title="t1")

    batch = {
        "approvals": [
            {"case_id": "CASE-2026-9999", "action": "approve"},
            {"case_id": real_id, "action": "approve"},
        ]
    }
    batch_path = tmp_path / "batch.yaml"
    batch_path.write_text(yaml.safe_dump(batch), encoding="utf-8")

    rc = main(
        [
            "--library-root",
            str(library_root),
            "approve",
            "--batch",
            str(batch_path),
        ]
    )
    captured = capsys.readouterr()
    # rc=1 because some failures; real case was still applied.
    assert rc == 1, captured.out
    assert "applied=1" in captured.out
    assert "failed=1" in captured.out
    assert "CASE-2026-9999" in captured.err
    # The real case got promoted despite the earlier unknown case.
    assert store.load(real_id).status.value == "active"
