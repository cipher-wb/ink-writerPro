"""US-LR-004: extract_one.py 单文件冒烟脚本测试。

覆盖 5 用例：
1. mock 模式产出合法 jsonl
2. 每行 jsonl 用 schema 校验通过
3. 3 本小说覆盖 score_signal 三类
4. 输入文件不存在 → exit 2
5. 不传 --bvid 时从 BV*_raw.txt 文件名自动提取
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "live-review" / "extract_one.py"
SCHEMA = REPO_ROOT / "schemas" / "live_review_extracted.schema.json"


def _run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Invoke extract_one.py as subprocess, repo root on sys.path."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        **kwargs,
    )


@pytest.fixture
def schema_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))


@pytest.fixture
def mock_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "mock_extract_BV12yBoBAEEn.json"


@pytest.fixture
def raw_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "raw_BV12yBoBAEEn.txt"


def test_extract_one_with_mock_creates_jsonl(tmp_path, mock_path, raw_path):
    out = tmp_path / "out.jsonl"
    proc = _run(
        [
            "--bvid",
            "BV12yBoBAEEn",
            "--input",
            str(raw_path),
            "--out",
            str(out),
            "--mock-llm",
            str(mock_path),
        ]
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
    assert out.exists()
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3


def test_extract_one_jsonl_lines_are_valid_records(
    tmp_path, mock_path, raw_path, schema_validator
):
    out = tmp_path / "out.jsonl"
    proc = _run(
        [
            "--bvid",
            "BV12yBoBAEEn",
            "--input",
            str(raw_path),
            "--out",
            str(out),
            "--mock-llm",
            str(mock_path),
        ]
    )
    assert proc.returncode == 0, proc.stderr
    for line in out.read_text(encoding="utf-8").strip().splitlines():
        record = json.loads(line)
        errors = list(schema_validator.iter_errors(record))
        assert errors == [], f"schema errors: {[e.message for e in errors]}"


def test_extract_one_score_signal_distribution(tmp_path, mock_path, raw_path):
    """fixture 故意覆盖 explicit_number / sign_phrase / fuzzy 三类。"""
    out = tmp_path / "out.jsonl"
    proc = _run(
        [
            "--bvid",
            "BV12yBoBAEEn",
            "--input",
            str(raw_path),
            "--out",
            str(out),
            "--mock-llm",
            str(mock_path),
        ]
    )
    assert proc.returncode == 0, proc.stderr
    signals = {
        json.loads(line)["score_signal"]
        for line in out.read_text(encoding="utf-8").strip().splitlines()
    }
    assert signals == {"explicit_number", "sign_phrase", "fuzzy"}


def test_extract_one_missing_input_exits_2(tmp_path):
    out = tmp_path / "out.jsonl"
    proc = _run(
        [
            "--bvid",
            "BV12yBoBAEEn",
            "--input",
            str(tmp_path / "does_not_exist_BV1xxxx_raw.txt"),
            "--out",
            str(out),
        ]
    )
    assert proc.returncode == 2, f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    assert not out.exists()


def test_extract_one_bvid_extracted_from_filename(
    tmp_path, mock_path, raw_path
):
    """不传 --bvid 时从文件名 BV<id>_raw.txt 正则提取。"""
    # copy fixture raw file into tmp_path with conventional BV*_raw.txt name
    staged = tmp_path / "BV12yBoBAEEn_raw.txt"
    shutil.copyfile(raw_path, staged)
    out = tmp_path / "out.jsonl"
    proc = _run(
        [
            "--input",
            str(staged),
            "--out",
            str(out),
            "--mock-llm",
            str(mock_path),
        ]
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    bvids = {
        json.loads(line)["bvid"]
        for line in out.read_text(encoding="utf-8").strip().splitlines()
    }
    assert bvids == {"BV12yBoBAEEn"}
