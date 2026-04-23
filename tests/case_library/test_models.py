"""Tests for Case dataclass + enums (US-004)."""
from __future__ import annotations

import pytest
from ink_writer.case_library.models import (
    Case,
    CaseDomain,
    CaseLayer,
    CaseSeverity,
    CaseStatus,
    SourceType,
)
from ink_writer.case_library.schema import validate_case_dict


def test_case_round_trip(sample_case_dict: dict) -> None:
    case = Case.from_dict(sample_case_dict)

    assert case.case_id == sample_case_dict["case_id"]
    assert case.status is CaseStatus.ACTIVE
    assert case.severity is CaseSeverity.P1
    assert case.domain is CaseDomain.WRITING_QUALITY
    assert case.layer == [CaseLayer.DOWNSTREAM]
    assert case.source.type is SourceType.EDITOR_REVIEW

    round_tripped = case.to_dict()
    validate_case_dict(round_tripped)

    assert round_tripped["case_id"] == sample_case_dict["case_id"]
    assert round_tripped["status"] == "active"
    assert round_tripped["layer"] == ["downstream"]
    assert round_tripped["scope"]["genre"] == ["all"]
    assert round_tripped["source"]["type"] == "editor_review"


def test_case_unknown_status_rejected() -> None:
    with pytest.raises(ValueError):
        CaseStatus("unknown")
    with pytest.raises(ValueError):
        CaseSeverity("P9")
    with pytest.raises(ValueError):
        CaseDomain("nonsense")
    with pytest.raises(ValueError):
        CaseLayer("sideways")
    with pytest.raises(ValueError):
        SourceType("ghost")


def test_case_to_dict_omits_empty_optional_blocks(sample_case_dict: dict) -> None:
    case = Case.from_dict(sample_case_dict)
    out = case.to_dict()

    assert "trigger" not in out["scope"]
    assert "reviewer" not in out["source"]
    assert "ingested_from" not in out["source"]

    case.scope.trigger = "主角接到电话场景"
    case.source.reviewer = "编辑星河"
    case.source.ingested_from = "editor_review_2026_04.md"
    filled = case.to_dict()
    assert filled["scope"]["trigger"] == "主角接到电话场景"
    assert filled["source"]["reviewer"] == "编辑星河"
    assert filled["source"]["ingested_from"] == "editor_review_2026_04.md"
    validate_case_dict(filled)
