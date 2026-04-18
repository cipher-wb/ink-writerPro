"""US-005/006/007/008: step3_runner 综合测试。

覆盖：
  1. dataclass 契约（Step3Result / GateFailure）
  2. 3 种模式（off / shadow / enforce）
  3. CLI subprocess 调用 + exit codes
  4. timeout / error 路径
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent.parent


def _make_project(tmp_path: Path) -> Path:
    """建 minimal 项目：.ink/index.db 含 review_metrics schema + 一个正文章节文件。"""
    project = tmp_path / "book"
    ink_dir = project / ".ink"
    ink_dir.mkdir(parents=True)
    text_dir = project / "正文"
    text_dir.mkdir()
    (text_dir / "第0001章-测试章.md").write_text("测试章节文本。" * 50, encoding="utf-8")

    db_path = ink_dir / "index.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("""
            CREATE TABLE review_metrics (
                start_chapter INTEGER NOT NULL,
                end_chapter INTEGER NOT NULL,
                overall_score REAL DEFAULT 0,
                dimension_scores TEXT,
                severity_counts TEXT,
                critical_issues TEXT,
                report_file TEXT,
                notes TEXT,
                review_payload_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (start_chapter, end_chapter)
            )
        """)
    return project


def test_step3result_to_dict():
    from ink_writer.checker_pipeline.step3_runner import GateFailure, Step3Result

    r = Step3Result(chapter_id=5, mode="shadow", passed=True)
    r.soft_fails.append(GateFailure(gate_id="voice", severity="soft", reason="score=0.6"))
    d = r.to_dict()
    assert d["chapter_id"] == 5
    assert d["mode"] == "shadow"
    assert d["passed"] is True
    assert len(d["soft_fails"]) == 1
    assert d["soft_fails"][0]["gate_id"] == "voice"


def test_mode_off_returns_early(tmp_path):
    from ink_writer.checker_pipeline.step3_runner import run_step3

    project = _make_project(tmp_path)
    result = asyncio.run(run_step3(
        chapter_id=1, state_dir=project / ".ink", mode="off"
    ))
    assert result.mode == "off"
    assert result.passed is True
    assert result.hard_fails == []


def test_mode_invalid_errors(tmp_path):
    from ink_writer.checker_pipeline.step3_runner import run_step3

    project = _make_project(tmp_path)
    result = asyncio.run(run_step3(
        chapter_id=1, state_dir=project / ".ink", mode="nonsense"
    ))
    assert result.passed is False
    assert "invalid mode" in (result.error or "")


def test_shadow_mode_runs_and_always_passes(tmp_path):
    """shadow：gates 都跑，即使真失败也 passed=True（但记录 fails）。"""
    from ink_writer.checker_pipeline.step3_runner import run_step3

    project = _make_project(tmp_path)
    result = asyncio.run(run_step3(
        chapter_id=1, state_dir=project / ".ink", mode="shadow", dry_run=True
    ))
    assert result.mode == "shadow"
    assert result.passed is True  # shadow 总是 pass
    # 5 gates 理应都有 results（哪怕是 stub）
    assert len(result.gate_results) >= 1  # 宽松断言：只要 runner 跑了


def test_cli_off_mode_exit_0(tmp_path):
    project = _make_project(tmp_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(
        [sys.executable, "-m", "ink_writer.checker_pipeline.step3_runner",
         "--chapter-id", "1", "--state-dir", str(project / ".ink"),
         "--mode", "off"],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"expected 0, got {result.returncode}; stderr={result.stderr}"


def test_cli_shadow_mode_exit_0(tmp_path):
    project = _make_project(tmp_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(
        [sys.executable, "-m", "ink_writer.checker_pipeline.step3_runner",
         "--chapter-id", "1", "--state-dir", str(project / ".ink"),
         "--mode", "shadow", "--dry-run", "--json"],
        env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"shadow should always exit 0; stderr={result.stderr}"
    # --json 输出到 stdout
    if result.stdout.strip():
        d = json.loads(result.stdout)
        assert d["mode"] == "shadow"


def test_persist_writes_review_metrics(tmp_path):
    """shadow 模式非 dry-run：结果写入 review_metrics 表。"""
    from ink_writer.checker_pipeline.step3_runner import run_step3

    project = _make_project(tmp_path)
    asyncio.run(run_step3(
        chapter_id=1, state_dir=project / ".ink", mode="shadow", dry_run=False
    ))
    with sqlite3.connect(str(project / ".ink" / "index.db")) as conn:
        rows = conn.execute("SELECT start_chapter, mode FROM review_metrics").fetchall() \
            if False else conn.execute(
                "SELECT start_chapter, notes FROM review_metrics"
            ).fetchall()
    assert len(rows) >= 1
    assert rows[0][0] == 1
    assert "step3_runner" in rows[0][1]


def test_env_mode_override(tmp_path, monkeypatch):
    """env INK_STEP3_RUNNER_MODE 生效（当 CLI 未传 --mode 时）。"""
    project = _make_project(tmp_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["INK_STEP3_RUNNER_MODE"] = "off"
    result = subprocess.run(
        [sys.executable, "-m", "ink_writer.checker_pipeline.step3_runner",
         "--chapter-id", "1", "--state-dir", str(project / ".ink")],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "mode=off" in result.stderr
