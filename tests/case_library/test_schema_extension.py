"""US-001 — Case schema M5 extension (recurrence_history / meta_rule_id / sovereign).

The 3 new fields are *optional* — existing 410 active cases must round-trip with
``recurrence_history=[]``, ``meta_rule_id=None``, ``sovereign=False``.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ink_writer.case_library.models import Case
from ink_writer.case_library.schema import validate_case_dict


REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = REPO_ROOT / "data" / "case_library" / "cases"


def test_case_defaults_to_empty_recurrence_and_no_meta_rule_and_not_sovereign(
    sample_case_dict: dict,
) -> None:
    case = Case.from_dict(sample_case_dict)

    assert case.recurrence_history == []
    assert case.meta_rule_id is None
    assert case.sovereign is False


def test_to_dict_includes_m5_fields(sample_case_dict: dict) -> None:
    case = Case.from_dict(sample_case_dict)
    case.recurrence_history.append(
        {
            "chapter": "001",
            "evidence_chain_path": "data/test/chapters/001.evidence.json",
            "regressed_at": "2026-04-25",
            "severity_before": "P3",
            "severity_after": "P2",
        }
    )
    case.meta_rule_id = "MR-0001"
    case.sovereign = True

    out = case.to_dict()
    assert out["recurrence_history"][0]["chapter"] == "001"
    assert out["meta_rule_id"] == "MR-0001"
    assert out["sovereign"] is True
    validate_case_dict(out)


def test_from_dict_backward_compatible_missing_m5_fields(sample_case_dict: dict) -> None:
    # sample_case_dict 不含 M5 三字段 — 模拟 410 个旧 case
    assert "recurrence_history" not in sample_case_dict
    assert "meta_rule_id" not in sample_case_dict
    assert "sovereign" not in sample_case_dict

    case = Case.from_dict(sample_case_dict)
    assert case.recurrence_history == []
    assert case.meta_rule_id is None
    assert case.sovereign is False

    # to_dict 后 schema 仍然合法（M5 字段默认值不破坏 schema）
    validate_case_dict(case.to_dict())


def test_existing_410_cases_still_load() -> None:
    """扫 data/case_library/cases/*.yaml round-trip 全部合法。"""
    yaml_files = sorted(CASES_DIR.glob("CASE-*.yaml"))
    assert len(yaml_files) >= 400, f"expected ≥400 cases on disk, got {len(yaml_files)}"

    failures: list[tuple[str, Exception]] = []
    for path in yaml_files:
        with open(path, encoding="utf-8") as fp:
            data = yaml.safe_load(fp)
        try:
            validate_case_dict(data)
            case = Case.from_dict(data)
            # round-trip 一次也能再次通过 schema
            validate_case_dict(case.to_dict())
            # 旧 case 的 M5 默认值
            assert case.recurrence_history == []
            assert case.meta_rule_id is None
            assert case.sovereign is False
        except Exception as exc:  # noqa: BLE001
            failures.append((path.name, exc))

    assert not failures, f"{len(failures)} legacy cases failed M5 round-trip: {failures[:3]}"


def test_sovereign_explicit_true(sample_case_dict: dict) -> None:
    sample_case_dict["sovereign"] = True
    case = Case.from_dict(sample_case_dict)
    assert case.sovereign is True
    out = case.to_dict()
    assert out["sovereign"] is True
    validate_case_dict(out)
