"""US-LR-007: jsonl → CASE-LR-*.yaml 转换器测试。"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "live-review" / "jsonl_to_cases.py"
_FIXTURE_JSONL = _REPO_ROOT / "tests" / "live_review" / "fixtures" / "sample_5_files.jsonl"
_CASE_SCHEMA = _REPO_ROOT / "schemas" / "case_schema.json"


def _run(jsonl_dir: Path, cases_dir: Path, *, dry_run: bool = False) -> subprocess.CompletedProcess:
    args = [
        sys.executable,
        str(_SCRIPT),
        "--jsonl-dir",
        str(jsonl_dir),
        "--cases-dir",
        str(cases_dir),
    ]
    if dry_run:
        args.append("--dry-run")
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8")


@pytest.fixture
def jsonl_dir(tmp_path: Path) -> Path:
    target = tmp_path / "jsonl"
    target.mkdir()
    shutil.copy(_FIXTURE_JSONL, target / "sample.jsonl")
    return target


@pytest.fixture
def cases_dir(tmp_path: Path) -> Path:
    return tmp_path / "cases"


def _load_yamls(cases_dir: Path) -> list[dict]:
    return [
        yaml.safe_load(p.read_text(encoding="utf-8"))
        for p in sorted(cases_dir.glob("CASE-LR-*.yaml"))
    ]


def test_5_jsonl_rows_become_5_yamls_with_sequential_ids(jsonl_dir, cases_dir):
    proc = _run(jsonl_dir, cases_dir)
    assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    yaml_files = sorted(cases_dir.glob("CASE-LR-*.yaml"))
    stems = [p.stem for p in yaml_files]
    assert stems == [
        "CASE-LR-2026-0001",
        "CASE-LR-2026-0002",
        "CASE-LR-2026-0003",
        "CASE-LR-2026-0004",
        "CASE-LR-2026-0005",
    ], stems


def test_all_yamls_validate_case_schema(jsonl_dir, cases_dir):
    proc = _run(jsonl_dir, cases_dir)
    assert proc.returncode == 0
    schema = json.loads(_CASE_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    for path in sorted(cases_dir.glob("CASE-LR-*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        errors = list(validator.iter_errors(data))
        assert not errors, f"{path.name}: {[e.message for e in errors]}"


def test_severity_covers_all_4_priorities(jsonl_dir, cases_dir):
    _run(jsonl_dir, cases_dir)
    cases = _load_yamls(cases_dir)
    severities = [c["severity"] for c in cases]
    # PRD: 5 categories means P0/P1/P2/P3 + null path (null also maps to P3)
    assert set(severities) == {"P0", "P1", "P2", "P3"}, severities
    # P3 occurs at least twice (once for score>=65, once for null)
    assert severities.count("P3") >= 2


def test_layer_derivation_covers_all_branches(jsonl_dir, cases_dir):
    _run(jsonl_dir, cases_dir)
    cases = _load_yamls(cases_dir)
    layer_tuples = [tuple(sorted(c["layer"])) for c in cases]
    # downstream-only (simplicity)
    assert ("downstream",) in layer_tuples, layer_tuples
    # upstream-only (opening / empty default)
    assert ("upstream",) in layer_tuples, layer_tuples
    # dual (pacing covers both)
    assert ("downstream", "upstream") in layer_tuples, layer_tuples


def test_same_bvid_multiple_novels_dont_conflict(jsonl_dir, cases_dir):
    _run(jsonl_dir, cases_dir)
    cases = _load_yamls(cases_dir)
    case_ids = [c["case_id"] for c in cases]
    bvids = [c["live_review_meta"]["source_bvid"] for c in cases]
    assert len(case_ids) == len(set(case_ids)), "case_ids must be unique"
    counter = Counter(bvids)
    # fixture has 2 records sharing BV1AAA
    assert any(count > 1 for count in counter.values()), counter


def test_live_review_meta_fully_populated(jsonl_dir, cases_dir):
    _run(jsonl_dir, cases_dir)
    cases = _load_yamls(cases_dir)
    required = [
        "source_bvid",
        "source_line_range",
        "score_raw",
        "score_signal",
        "verdict",
        "title_guess",
        "genre_guess",
        "overall_comment",
        "comments",
    ]
    for case in cases:
        meta = case["live_review_meta"]
        for key in required:
            assert key in meta, f"missing live_review_meta.{key} in {case['case_id']}"
        assert "score" in meta  # may be null but key must exist
        assert len(meta["source_line_range"]) == 2
        assert len(meta["genre_guess"]) >= 1
        # raw_line_range stripped
        for c in meta["comments"]:
            assert "raw_line_range" not in c, "raw_line_range must be stripped"


def test_failure_pattern_observable_fallback_on_no_negative_comments(jsonl_dir, cases_dir):
    _run(jsonl_dir, cases_dir)
    cases = _load_yamls(cases_dir)
    found = False
    for case in cases:
        meta = case["live_review_meta"]
        has_negative = any(c.get("severity") == "negative" for c in meta["comments"])
        if not has_negative:
            obs = case["failure_pattern"]["observable"]
            assert any("整体被星河直播判定为" in line for line in obs), obs
            found = True
    assert found, "fixture should contain at least one row without negative comments"


def test_severity_and_score_mapping_per_row(jsonl_dir, cases_dir):
    _run(jsonl_dir, cases_dir)
    cases = _load_yamls(cases_dir)
    # Sort by case_id for stable order
    cases.sort(key=lambda c: c["case_id"])
    # fixture order: row1 score=50→P0, row2 score=58→P1, row3 score=63→P2,
    # row4 score=75→P3, row5 score=null→P3
    expected = [("P0", 50), ("P1", 58), ("P2", 63), ("P3", 75), ("P3", None)]
    for case, (sev, score) in zip(cases, expected, strict=True):
        assert case["severity"] == sev, case["case_id"]
        assert case["live_review_meta"]["score"] == score, case["case_id"]


def test_dry_run_does_not_write_yaml(jsonl_dir, cases_dir):
    proc = _run(jsonl_dir, cases_dir, dry_run=True)
    assert proc.returncode == 0
    yaml_files = list(cases_dir.glob("CASE-LR-*.yaml")) if cases_dir.exists() else []
    assert yaml_files == [], f"dry-run should not write yamls, found {yaml_files}"
