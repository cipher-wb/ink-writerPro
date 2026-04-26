"""US-LR-005: validate_jsonl_batch.py 校验 + markdown 报告测试。

覆盖 3 用例：
(a) 5 份正常 jsonl → 退出码 0 + markdown 报告含 'All files passed'
(b) 故意 1 份某行 score=200 → 退出码 1 + stderr 含 BVID + 行号 + 'score' 字段
(c) 报告 markdown 用 markdown_it parse 不抛错
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from markdown_it import MarkdownIt

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRACT_SCRIPT = REPO_ROOT / "scripts" / "live-review" / "extract_one.py"
VALIDATE_SCRIPT = REPO_ROOT / "scripts" / "live-review" / "validate_jsonl_batch.py"

BVIDS = ["BV1AAA", "BV1BBB", "BV1CCC", "BV1DDD", "BV1EEE"]


@pytest.fixture
def jsonl_dir(tmp_path, fixtures_dir: Path) -> Path:
    """Run extract_one.py multi-file mode to produce 5 valid jsonl files."""
    out_dir = tmp_path / "jsonl"
    proc = subprocess.run(
        [
            sys.executable,
            str(EXTRACT_SCRIPT),
            "--bvids",
            ",".join(BVIDS),
            "--input-dir",
            str(fixtures_dir / "raw_5_files"),
            "--output-dir",
            str(out_dir),
            "--mock-llm-dir",
            str(fixtures_dir / "mock_extract_5_files"),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.returncode == 0, proc.stderr
    return out_dir


def _run_validate(
    jsonl_dir: Path, report_out: Path
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATE_SCRIPT),
            "--jsonl-dir",
            str(jsonl_dir),
            "--report-out",
            str(report_out),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )


def test_validate_all_pass_writes_report(tmp_path, jsonl_dir):
    """5 valid jsonl → exit 0 + markdown with 'All files passed'."""
    report = tmp_path / "report.md"
    proc = _run_validate(jsonl_dir, report)
    assert proc.returncode == 0, f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "All files passed" in text
    assert "Per-file Statistics" in text
    assert "Score Signal Distribution" in text
    assert "Validation Issues" in text


def test_validate_score_out_of_range_fails(tmp_path, jsonl_dir):
    """Corrupt one record's score → exit 1 + stderr lists BVID + line + 'score'."""
    target = jsonl_dir / "BV1AAA.jsonl"
    lines = target.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["score"] = 200  # out of [0, 100]
    lines[1] = json.dumps(record, ensure_ascii=False)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = tmp_path / "report.md"
    proc = _run_validate(jsonl_dir, report)
    assert proc.returncode == 1, f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    assert "BV1AAA" in proc.stderr
    assert "line=2" in proc.stderr
    assert "score" in proc.stderr
    assert report.exists(), "report should still be written even on failure"


def test_validate_report_is_valid_markdown(tmp_path, jsonl_dir):
    """markdown 报告用 markdown_it 解析不抛错且渲染出非空 HTML。"""
    report = tmp_path / "report.md"
    proc = _run_validate(jsonl_dir, report)
    assert proc.returncode == 0, proc.stderr
    text = report.read_text(encoding="utf-8")
    md = MarkdownIt("commonmark").enable("table")
    html = md.render(text)
    assert html.strip(), "rendered HTML must not be empty"
    # spot-check that at least one table + heading made it through
    assert "<h1>" in html
    assert "<table>" in html
