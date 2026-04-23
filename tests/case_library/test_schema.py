from __future__ import annotations

import pytest
from ink_writer.case_library.errors import CaseValidationError
from ink_writer.case_library.schema import validate_case_dict


def test_minimum_valid_case_passes(sample_case_dict: dict) -> None:
    validate_case_dict(sample_case_dict)  # no raise


def test_missing_required_case_id_raises(sample_case_dict: dict) -> None:
    sample_case_dict.pop("case_id")
    with pytest.raises(CaseValidationError, match="case_id"):
        validate_case_dict(sample_case_dict)


def test_invalid_status_raises(sample_case_dict: dict) -> None:
    sample_case_dict["status"] = "not-a-status"
    with pytest.raises(CaseValidationError, match="status"):
        validate_case_dict(sample_case_dict)


def test_invalid_severity_raises(sample_case_dict: dict) -> None:
    sample_case_dict["severity"] = "P9"
    with pytest.raises(CaseValidationError, match="severity"):
        validate_case_dict(sample_case_dict)


def test_invalid_domain_raises(sample_case_dict: dict) -> None:
    sample_case_dict["domain"] = "marketing"
    with pytest.raises(CaseValidationError, match="domain"):
        validate_case_dict(sample_case_dict)


def test_layer_must_be_array(sample_case_dict: dict) -> None:
    sample_case_dict["layer"] = "downstream"
    with pytest.raises(CaseValidationError, match="layer"):
        validate_case_dict(sample_case_dict)


def test_case_id_pattern_enforced(sample_case_dict: dict) -> None:
    sample_case_dict["case_id"] = "case-2026-1"
    with pytest.raises(CaseValidationError, match="case_id"):
        validate_case_dict(sample_case_dict)
