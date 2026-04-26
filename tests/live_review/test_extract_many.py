"""US-LR-005: extract_one.py 多份模式 (--bvids / --input-dir / --output-dir)。

覆盖 2 用例：
1. 5 份 mock 全跑通 → 5 个 jsonl 存在 + 全部 schema 校验通过 + 总 novel 数 == 26
2. 不同 BV 的 record 不串号（每个 jsonl 文件 bvid 字段全部一致且对应 BV）
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "live-review" / "extract_one.py"
SCHEMA = REPO_ROOT / "schemas" / "live_review_extracted.schema.json"

BVIDS = ["BV1AAA", "BV1BBB", "BV1CCC", "BV1DDD", "BV1EEE"]
EXPECTED_COUNTS = {"BV1AAA": 3, "BV1BBB": 4, "BV1CCC": 2, "BV1DDD": 2, "BV1EEE": 15}
TOTAL_EXPECTED = sum(EXPECTED_COUNTS.values())


@pytest.fixture
def schema_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))


@pytest.fixture
def raw_dir(fixtures_dir: Path) -> Path:
    return fixtures_dir / "raw_5_files"


@pytest.fixture
def mock_dir(fixtures_dir: Path) -> Path:
    return fixtures_dir / "mock_extract_5_files"


def _run_many(tmp_out: Path, raw_dir: Path, mock_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--bvids",
            ",".join(BVIDS),
            "--input-dir",
            str(raw_dir),
            "--output-dir",
            str(tmp_out),
            "--mock-llm-dir",
            str(mock_dir),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )


def test_extract_many_creates_5_jsonl_with_total_26_records(
    tmp_path, raw_dir, mock_dir, schema_validator
):
    out_dir = tmp_path / "out"
    proc = _run_many(out_dir, raw_dir, mock_dir)
    assert proc.returncode == 0, f"stderr: {proc.stderr}\nstdout: {proc.stdout}"

    total = 0
    for bvid in BVIDS:
        jsonl = out_dir / f"{bvid}.jsonl"
        assert jsonl.exists(), f"missing {jsonl}"
        lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == EXPECTED_COUNTS[bvid], (
            f"{bvid}: expected {EXPECTED_COUNTS[bvid]} records, got {len(lines)}"
        )
        for line in lines:
            record = json.loads(line)
            errors = list(schema_validator.iter_errors(record))
            assert errors == [], (
                f"{bvid} schema errors: {[e.message for e in errors]}"
            )
        total += len(lines)

    assert total == TOTAL_EXPECTED


def test_extract_many_records_do_not_cross_bvids(tmp_path, raw_dir, mock_dir):
    """每份 jsonl 内 bvid 字段必须严格等于文件名 BV，不串号。"""
    out_dir = tmp_path / "out"
    proc = _run_many(out_dir, raw_dir, mock_dir)
    assert proc.returncode == 0, proc.stderr

    for bvid in BVIDS:
        jsonl = out_dir / f"{bvid}.jsonl"
        observed = {
            json.loads(line)["bvid"]
            for line in jsonl.read_text(encoding="utf-8").strip().splitlines()
        }
        assert observed == {bvid}, f"{bvid}.jsonl bvids: {observed}"
