"""US-LR-009: 规则候选抽取器测试（LLM mock + bge cosine 去重）。"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "live-review" / "extract_rule_candidates.py"
FIXTURES = Path(__file__).parent / "fixtures"

# 候选扩展 schema：基于 editor-rules.schema.json 加 dup_with / approved / source_bvids。
# US-009 候选 ID 用 RC-NNNN 不取 EW-；US-010 promote 时再剥除这些扩展字段后用
# 严格 editor-rules.schema.json 校验。
CANDIDATE_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "array",
    "items": {
        "type": "object",
        "required": [
            "id",
            "category",
            "rule",
            "why",
            "severity",
            "applies_to",
            "source_files",
            "dup_with",
            "approved",
            "source_bvids",
        ],
        "properties": {
            "id": {"type": "string", "pattern": r"^RC-\d{4}$"},
            "category": {
                "type": "string",
                "enum": [
                    "opening",
                    "hook",
                    "golden_finger",
                    "character",
                    "pacing",
                    "highpoint",
                    "taboo",
                    "genre",
                    "ops",
                    "misc",
                ],
            },
            "rule": {"type": "string", "maxLength": 120},
            "why": {"type": "string"},
            "severity": {"type": "string", "enum": ["hard", "soft", "info"]},
            "applies_to": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["all_chapters", "golden_three", "opening_only"],
                },
                "minItems": 1,
            },
            "source_files": {"type": "array", "items": {"type": "string"}},
            "dup_with": {
                "oneOf": [
                    {"type": "null"},
                    {
                        "type": "array",
                        "items": {"type": "string", "pattern": r"^EW-\d{4}$"},
                        "minItems": 1,
                    },
                ]
            },
            "approved": {
                "oneOf": [{"type": "null"}, {"type": "boolean"}],
            },
            "source_bvids": {
                "type": "array",
                "items": {"type": "string", "pattern": r"^BV[A-Za-z0-9]+$"},
                "minItems": 1,
            },
        },
        "additionalProperties": False,
    },
}


@pytest.fixture(scope="module")
def jsonl_dir(tmp_path_factory) -> Path:
    """复制 sample_5_files.jsonl 到隔离目录，避免污染 fixtures。"""
    d = tmp_path_factory.mktemp("jsonl_in")
    shutil.copy(FIXTURES / "sample_5_files.jsonl", d / "sample.jsonl")
    return d


@pytest.fixture(scope="module")
def candidates_file(tmp_path_factory, jsonl_dir) -> Path:
    """跑一次脚本，6 个非异常用例共享结果（避免重复加载 bge 模型 30s）。"""
    out = tmp_path_factory.mktemp("rc_out") / "rule_candidates.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--jsonl-dir",
            str(jsonl_dir),
            "--rules-json",
            str(FIXTURES / "existing_rules_fixture.json"),
            "--out",
            str(out),
            "--mock-llm",
            str(FIXTURES / "mock_rule_extract.json"),
            "--threshold",
            "0.85",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"extract_rule_candidates.py exit={proc.returncode}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
    assert out.exists(), f"missing output: {out}"
    return out


@pytest.fixture(scope="module")
def candidates(candidates_file) -> list[dict]:
    return json.loads(candidates_file.read_text(encoding="utf-8"))


def test_mock_returns_5_candidates(candidates):
    assert len(candidates) == 5


def test_at_least_2_candidates_have_dup_with(candidates):
    dups = [c for c in candidates if c["dup_with"]]
    assert len(dups) >= 2, f"expected >=2 with dup_with, got {len(dups)}: {dups}"


def test_dup_with_targets_existing_EW_ids(candidates):
    """前 2 条 mock 故意接近 EW-0001/0002，应命中至少 1 个 EW-0001|0002。"""
    hit_ids: set[str] = set()
    for c in candidates:
        for eid in c["dup_with"] or []:
            hit_ids.add(eid)
    assert {"EW-0001", "EW-0002"} & hit_ids, (
        f"expected EW-0001 or EW-0002 in dup_with, got {hit_ids}"
    )


def test_source_bvids_filled_from_jsonl(candidates):
    expected = {"BV1AAA", "BV1BBB", "BV1CCC", "BV1DDD"}
    for c in candidates:
        assert c["source_bvids"], f"empty source_bvids in {c['id']}"
        assert set(c["source_bvids"]) <= expected, (
            f"{c['id']} source_bvids has unknown bvid: {c['source_bvids']}"
        )
        assert set(c["source_bvids"]) == expected, (
            f"{c['id']} should cover all jsonl bvids, got {c['source_bvids']}"
        )


def test_approved_field_all_null(candidates):
    for c in candidates:
        assert c["approved"] is None, f"{c['id']} approved={c['approved']!r}"


def test_ids_well_formed_and_unique(candidates):
    ids = [c["id"] for c in candidates]
    assert ids == sorted(ids), "RC IDs should be sorted"
    assert len(ids) == len(set(ids)), "RC IDs should be unique"
    for cid in ids:
        assert cid.startswith("RC-"), f"{cid} should use RC- prefix"


def test_validates_against_extended_schema(candidates):
    Draft202012Validator.check_schema(CANDIDATE_SCHEMA)
    errs = list(Draft202012Validator(CANDIDATE_SCHEMA).iter_errors(candidates))
    assert not errs, [
        f"{list(e.absolute_path)}: {e.message}" for e in errs[:5]
    ]


def test_fail_loud_on_non_json_llm_output(tmp_path, jsonl_dir):
    bad = tmp_path / "bad.txt"
    bad.write_text("this is not JSON at all", encoding="utf-8")
    out = tmp_path / "out.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--jsonl-dir",
            str(jsonl_dir),
            "--rules-json",
            str(FIXTURES / "existing_rules_fixture.json"),
            "--out",
            str(out),
            "--mock-llm",
            str(bad),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 1, f"expected exit 1, got {proc.returncode}\nstderr={proc.stderr}"
    assert "JSON" in proc.stderr or "json" in proc.stderr, proc.stderr
    assert not out.exists(), "should not write output on failure"


def test_fail_loud_on_missing_required_field(tmp_path, jsonl_dir):
    bad = tmp_path / "missing_fields.json"
    bad.write_text(
        json.dumps([{"rule": "no other fields", "why": "broken"}]),
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--jsonl-dir",
            str(jsonl_dir),
            "--rules-json",
            str(FIXTURES / "existing_rules_fixture.json"),
            "--out",
            str(out),
            "--mock-llm",
            str(bad),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 1, f"expected exit 1, got {proc.returncode}"
    assert "category" in proc.stderr or "missing" in proc.stderr.lower()


def test_threshold_zero_marks_everything_as_dup(tmp_path, jsonl_dir):
    """threshold=0 时所有候选与第一条 EW 都达标 → dup_with 至少含 1 个 EW-id。"""
    out = tmp_path / "out.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--jsonl-dir",
            str(jsonl_dir),
            "--rules-json",
            str(FIXTURES / "existing_rules_fixture.json"),
            "--out",
            str(out),
            "--mock-llm",
            str(FIXTURES / "mock_rule_extract.json"),
            "--threshold",
            "0.0",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert all(c["dup_with"] for c in data), (
        "with threshold=0, every candidate should pick up at least 1 dup_with"
    )
