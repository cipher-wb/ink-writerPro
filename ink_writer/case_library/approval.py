"""Batch approval for pending cases — approve / reject / defer.

Reads a YAML file matching ``schemas/case_approval_batch_schema.json`` and
applies each approval to the target case: ``approve`` → active, ``reject`` →
retired, ``defer`` → pending (unchanged status, useful for carrying a note).
Every successful transition appends an ``approval`` event to
``ingest_log.jsonl`` for audit; per-case failures are collected and do not
abort the batch.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from ink_writer.case_library.errors import CaseNotFoundError
from ink_writer.case_library.models import CaseStatus
from ink_writer.case_library.store import CaseStore

_ACTION_TO_STATUS: dict[str, CaseStatus] = {
    "approve": CaseStatus.ACTIVE,
    "reject": CaseStatus.RETIRED,
    "defer": CaseStatus.PENDING,
}


@dataclass
class ApprovalReport:
    applied: int = 0
    failed: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


@lru_cache(maxsize=1)
def _load_schema() -> dict[str, Any]:
    schema_path = _repo_root() / "schemas" / "case_approval_batch_schema.json"
    with open(schema_path, encoding="utf-8") as fp:
        return json.load(fp)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def apply_batch_yaml(
    *, yaml_path: Path, library_root: Path
) -> ApprovalReport:
    """Apply one approvals YAML batch to the case library.

    Raises:
        jsonschema.ValidationError: when the YAML does not match the schema.
    """
    with open(yaml_path, encoding="utf-8") as fp:
        data = yaml.safe_load(fp)

    Draft202012Validator(_load_schema()).validate(data)

    store = CaseStore(library_root)
    report = ApprovalReport()

    for entry in data["approvals"]:
        case_id = entry["case_id"]
        action = entry["action"]
        note = entry.get("note")
        try:
            case = store.load(case_id)
            case.status = _ACTION_TO_STATUS[action]
            store.save(case)
            event: dict[str, Any] = {
                "event": "approval",
                "case_id": case_id,
                "action": action,
                "at": _now_iso(),
            }
            if note is not None:
                event["note"] = note
            store.append_ingest_log(event)
            report.applied += 1
        except CaseNotFoundError as err:
            report.failed += 1
            report.failures.append((case_id, f"not found: {err}"))
        except Exception as err:  # noqa: BLE001 — batch-level guard
            report.failed += 1
            report.failures.append((case_id, str(err)))

    return report
