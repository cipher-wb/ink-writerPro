"""Case persistence layer — one YAML file per case.

``CaseStore(library_root)`` lays out::

    <library_root>/
        cases/
            CASE-2026-0001.yaml
            CASE-2026-0002.yaml
            ...
        ingest_log.jsonl    (append-only audit trail)

YAML is the authoritative format (human-editable, diff-friendly). ``pack_jsonl``
exists for export/backup only — it does not replace the YAML files. Both
``save`` and ``load`` run the dict through ``validate_case_dict`` so the
on-disk state is always schema-valid.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

from ink_writer.case_library.errors import CaseNotFoundError
from ink_writer.case_library.models import Case
from ink_writer.case_library.schema import validate_case_dict


class CaseStore:
    """YAML-backed case library.

    Args:
        library_root: base directory; ``library_root/cases`` is auto-created.
    """

    def __init__(self, library_root: Path) -> None:
        self.library_root = Path(library_root)
        self.cases_dir = self.library_root / "cases"
        self.cases_dir.mkdir(parents=True, exist_ok=True)

    @property
    def ingest_log_path(self) -> Path:
        return self.library_root / "ingest_log.jsonl"

    def _case_path(self, case_id: str) -> Path:
        return self.cases_dir / f"{case_id}.yaml"

    def save(self, case: Case) -> Path:
        """Validate then write the case to ``cases/<case_id>.yaml``.

        Returns the written path. Raises ``CaseValidationError`` if the
        serialized form does not match the schema.
        """
        data = case.to_dict()
        validate_case_dict(data)
        path = self._case_path(case.case_id)
        with open(path, "w", encoding="utf-8") as fp:
            yaml.safe_dump(
                data,
                fp,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
        return path

    def load(self, case_id: str) -> Case:
        """Load and validate the case YAML; raise ``CaseNotFoundError`` if absent."""
        path = self._case_path(case_id)
        if not path.exists():
            raise CaseNotFoundError(case_id)
        with open(path, encoding="utf-8") as fp:
            data = yaml.safe_load(fp)
        validate_case_dict(data)
        return Case.from_dict(data)

    def list_ids(self) -> list[str]:
        """Return the sorted list of case_ids discoverable on disk."""
        return sorted(p.stem for p in self.cases_dir.glob("CASE-*.yaml"))

    def iter_cases(self) -> Iterator[Case]:
        """Yield every case sorted by case_id ascending."""
        for case_id in self.list_ids():
            yield self.load(case_id)

    def pack_jsonl(self, out_path: Path) -> int:
        """Export all cases as newline-delimited JSON; returns the number written."""
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with open(out_path, "w", encoding="utf-8") as fp:
            for case in self.iter_cases():
                fp.write(json.dumps(case.to_dict(), ensure_ascii=False))
                fp.write("\n")
                count += 1
        return count

    def append_ingest_log(self, event: dict[str, Any]) -> None:
        """Append one JSON object per line to ``ingest_log.jsonl``."""
        with open(self.ingest_log_path, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(event, ensure_ascii=False))
            fp.write("\n")
