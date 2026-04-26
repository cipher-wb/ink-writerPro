"""US-LR-001: case_schema 1.0→1.1 后，全部 410+ 现存 case yaml 仍解析通过。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).parents[2]
CASES_DIR = REPO_ROOT / "data" / "case_library" / "cases"
SCHEMA_PATH = REPO_ROOT / "schemas" / "case_schema.json"


@pytest.fixture(scope="module")
def case_validator():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _iter_case_files():
    if not CASES_DIR.exists():
        return
    for path in sorted(CASES_DIR.rglob("*.yaml")):
        if path.name.startswith("."):
            continue  # 跳 hidden / counter file
        yield path


def test_all_existing_cases_still_validate(case_validator):
    """schema 1.1 须严格全过现存 case yaml。"""
    failures = []
    count = 0
    for path in _iter_case_files():
        count += 1
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            failures.append(f"{path.name}: YAML parse error: {e}")
            continue
        if data is None:
            failures.append(f"{path.name}: empty yaml")
            continue
        errors = list(case_validator.iter_errors(data))
        if errors:
            failures.append(f"{path.name}: {[e.message for e in errors[:3]]}")
    assert count > 0, f"no case yaml found under {CASES_DIR}"
    assert not failures, (
        f"{len(failures)}/{count} cases failed schema 1.1 validation:\n"
        + "\n".join(failures[:20])
    )


def test_new_live_review_case_validates(case_validator):
    """新增 schema 1.1 字段的 sample 病例须通过。"""
    sample = {
        "case_id": "CASE-LR-2026-0001",
        "title": "都市/重生/律师 (borderline / 68分)",
        "status": "active",
        "severity": "P2",
        "domain": "live_review",
        "layer": ["upstream"],
        "tags": ["live_review", "都市"],
        "scope": {"genre": ["都市"], "trigger": "投稿前 3 章被星河审稿"},
        "source": {
            "type": "editor_review",
            "raw_text": "68 吧是吧 / 设定太复杂",
            "ingested_at": "2026-04-27",
            "ingested_from": "data/live-review/extracted/BV12yBoBAEEn.jsonl",
        },
        "failure_pattern": {
            "description": "开篇 800 字铺设定，金手指第 5 章才出，节奏拖沓",
            "observable": ["前 800 字无核心冲突", "金手指出场超过 3 章"],
        },
        "live_review_meta": {
            "source_bvid": "BV12yBoBAEEn",
            "source_line_range": [105, 192],
            "score": 68,
            "score_raw": "68 吧是吧",
            "score_signal": "explicit_number",
            "verdict": "borderline",
            "title_guess": "都市重生律师文",
            "genre_guess": ["都市", "重生"],
            "overall_comment": "节奏不错但金手指出现太晚",
            "comments": [
                {"dimension": "pacing", "severity": "negative", "content": "开篇拖沓"}
            ],
        },
    }
    errs = list(case_validator.iter_errors(sample))
    assert not errs, [e.message for e in errs]


def test_invalid_domain_still_rejected(case_validator):
    """domain enum 之外的值仍应被拒绝（防止过度宽松）。"""
    sample = {
        "case_id": "CASE-2026-0001",
        "title": "x",
        "status": "active",
        "severity": "P0",
        "domain": "totally_made_up_domain",
        "layer": ["upstream"],
        "tags": [],
        "scope": {},
        "source": {
            "type": "self_audit",
            "raw_text": "x",
            "ingested_at": "2026-04-27",
        },
        "failure_pattern": {"description": "x", "observable": ["x"]},
    }
    errs = list(case_validator.iter_errors(sample))
    assert any(
        "domain" in str(e.path) or "live_review" in e.message for e in errs
    )
