"""Case JSON Schema loader and validator.

The schema lives in ``schemas/case_schema.json`` at the repo root. We load it
once on first use and cache it. Validation errors are raised as
:class:`CaseValidationError` with the JSON pointer of the offending field
included in the message so that CLI consumers can show useful diagnostics.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from ink_writer.case_library.errors import CaseValidationError


def _repo_root() -> Path:
    # ink_writer/case_library/schema.py -> repo root is parent.parent.parent
    return Path(__file__).resolve().parent.parent.parent


@lru_cache(maxsize=1)
def _load_schema() -> dict[str, Any]:
    schema_path = _repo_root() / "schemas" / "case_schema.json"
    with open(schema_path, encoding="utf-8") as fp:
        return json.load(fp)


def validate_case_dict(case: dict[str, Any]) -> None:
    """Validate ``case`` against the Case JSON Schema.

    Raises:
        CaseValidationError: with an error message containing the JSON path of
            the first offending field.
    """
    schema = _load_schema()
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(case), key=lambda e: list(e.absolute_path))
    if not errors:
        return
    first = errors[0]
    pointer = (
        "/" + "/".join(str(p) for p in first.absolute_path)
        if first.absolute_path
        else "/"
    )
    raise CaseValidationError(f"{pointer}: {first.message}")
