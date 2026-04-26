"""US-LR-010: 规则候选 promote 工具测试 — 仅 approved=true 的项写入 rules.json。"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "live-review" / "promote_approved_rules.py"
FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_PATH = REPO_ROOT / "schemas" / "editor-rules.schema.json"


def _hash_rule(rule: dict) -> str:
    """字节级 hash 用于校验现有规则未被改动。"""
    blob = json.dumps(rule, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@pytest.fixture
def candidates_with_3_approved(tmp_path) -> Path:
    """5 条候选：3 标 approved=true (RC-0003/0004/0005) / 2 标 false (RC-0001/0002)。"""
    src = FIXTURES / "sample_rule_candidates.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    # RC-0001/0002 是 dup_with EW-0001/0002 的 → 标 false (不应被 promote)
    # RC-0003/0004/0005 不重复 → 标 true (应被 promote)
    approvals = [False, False, True, True, True]
    for c, a in zip(data, approvals, strict=True):
        c["approved"] = a
    dst = tmp_path / "rule_candidates_reviewed.json"
    dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return dst


@pytest.fixture
def rules_copy(tmp_path) -> Path:
    """拷一份 sample_rules_for_promote.json (EW-0001..EW-0080) 到 tmp_path。"""
    src = FIXTURES / "sample_rules_for_promote.json"
    dst = tmp_path / "rules.json"
    shutil.copy(src, dst)
    return dst


def _run(
    *,
    candidates: Path,
    rules: Path,
    dry_run: bool = False,
) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--candidates",
        str(candidates),
        "--rules",
        str(rules),
    ]
    if dry_run:
        cmd.append("--dry-run")
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )


def test_promote_appends_only_approved_true(candidates_with_3_approved, rules_copy):
    """3 个 approved=true → 新文件含 EW-0001..EW-0083 (80 + 3)。"""
    proc = _run(candidates=candidates_with_3_approved, rules=rules_copy)
    assert proc.returncode == 0, (
        f"exit={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    data = json.loads(rules_copy.read_text(encoding="utf-8"))
    assert len(data) == 83, f"expected 83 rules, got {len(data)}"
    ids = [r["id"] for r in data]
    assert ids[-3:] == ["EW-0081", "EW-0082", "EW-0083"]


def test_promote_keeps_existing_rules_byte_identical(
    candidates_with_3_approved, rules_copy
):
    """现有 EW-0001..EW-0080 字节级 hash 完全相同。"""
    src_data = json.loads(
        (FIXTURES / "sample_rules_for_promote.json").read_text(encoding="utf-8")
    )
    src_hashes = [_hash_rule(r) for r in src_data]

    proc = _run(candidates=candidates_with_3_approved, rules=rules_copy)
    assert proc.returncode == 0, proc.stderr

    new_data = json.loads(rules_copy.read_text(encoding="utf-8"))
    new_hashes = [_hash_rule(r) for r in new_data[:80]]
    assert new_hashes == src_hashes, "existing rules must not be modified"


def test_promote_new_rules_have_source_live_review(
    candidates_with_3_approved, rules_copy
):
    """新加 3 条均含 source == 'live_review'。"""
    proc = _run(candidates=candidates_with_3_approved, rules=rules_copy)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(rules_copy.read_text(encoding="utf-8"))
    new_rules = data[80:]
    assert len(new_rules) == 3
    for r in new_rules:
        assert r.get("source") == "live_review", (
            f"{r['id']}: source={r.get('source')!r}, expected 'live_review'"
        )


def test_promote_output_validates_strict_schema(
    candidates_with_3_approved, rules_copy
):
    """整个输出文件用 schemas/editor-rules.schema.json 严格校验通过。"""
    proc = _run(candidates=candidates_with_3_approved, rules=rules_copy)
    assert proc.returncode == 0, proc.stderr

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)

    data = json.loads(rules_copy.read_text(encoding="utf-8"))
    errs = list(Draft202012Validator(schema).iter_errors(data))
    assert not errs, [
        f"{list(e.absolute_path)[:3]}: {e.message[:80]}" for e in errs[:5]
    ]


def test_promote_strips_candidate_only_fields(
    candidates_with_3_approved, rules_copy
):
    """新加项不应含 dup_with / approved / source_bvids / id 候选 RC-NNNN。"""
    proc = _run(candidates=candidates_with_3_approved, rules=rules_copy)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(rules_copy.read_text(encoding="utf-8"))
    new_rules = data[80:]
    forbidden = {"dup_with", "approved", "source_bvids"}
    for r in new_rules:
        present = forbidden & set(r.keys())
        assert not present, f"{r['id']}: has candidate-only fields: {present}"
        assert r["id"].startswith("EW-"), f"{r['id']}: should be EW-NNNN not RC-"


def test_promote_dry_run_does_not_write(candidates_with_3_approved, rules_copy):
    """--dry-run 不修改 rules.json。"""
    before = rules_copy.read_bytes()
    proc = _run(candidates=candidates_with_3_approved, rules=rules_copy, dry_run=True)
    assert proc.returncode == 0, proc.stderr
    after = rules_copy.read_bytes()
    assert before == after, "dry-run must not modify rules.json"


def test_promote_no_approved_no_change(rules_copy, tmp_path):
    """全部 approved=false → rules.json 不变。"""
    src = FIXTURES / "sample_rule_candidates.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    for c in data:
        c["approved"] = False
    cand = tmp_path / "all_false.json"
    cand.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    before = rules_copy.read_bytes()
    proc = _run(candidates=cand, rules=rules_copy)
    assert proc.returncode == 0, proc.stderr
    after = rules_copy.read_bytes()
    assert before == after, "no approved=true → rules.json should be unchanged"
