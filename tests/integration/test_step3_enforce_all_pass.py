"""v16 US-005：enforce 默认模式下合规章节顺利通过。

AC："构造合规章节，enforce 预期 exit=0"。

实现策略：使用无 ZT 触发词的清洁章节 + stub 模式（CI 安全），验证 DEFAULT_MODE=enforce
不会误杀合规章节。
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent.parent


_CLEAN_CHAPTER = (
    "山风掠过屋檐。少年把剑扛在肩上，数着脚下的青砖。\n\n"
    "他没有回头。身后那扇木门吱呀作响，却终究合上了。\n\n"
    "远处传来钟声，一声，又一声。他停了停，把剑换到另一边。"
)


def _make_project(tmp_path: Path) -> Path:
    project = tmp_path / "book"
    ink_dir = project / ".ink"
    ink_dir.mkdir(parents=True)
    text_dir = project / "正文"
    text_dir.mkdir()
    (text_dir / "第0001章-干净章.md").write_text(_CLEAN_CHAPTER * 20, encoding="utf-8")

    db_path = ink_dir / "index.db"
    with closing(sqlite3.connect(str(db_path))) as conn:
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


def test_enforce_default_passes_clean_chapter_exit_0(tmp_path: Path) -> None:
    """enforce 默认 + 合规章节 → CLI exit=0。"""
    project = _make_project(tmp_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["INK_STEP3_LLM_CHECKER"] = "off"
    env["INK_STEP3_LLM_POLISH"] = "off"
    env.pop("INK_STEP3_RUNNER_MODE", None)

    result = subprocess.run(
        [
            sys.executable, "-m", "ink_writer.checker_pipeline.step3_runner",
            "--chapter-id", "1",
            "--state-dir", str(project / ".ink"),
            "--dry-run", "--json",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=120, encoding="utf-8",
    )

    assert result.returncode == 0, (
        f"expected exit=0 for clean chapter under enforce default, got {result.returncode}. "
        f"stdout={result.stdout[:500]!r} stderr={result.stderr[:500]!r}"
    )
    # 输出应标 enforce 且 passed=True
    assert "mode=enforce" in result.stderr or "enforce" in result.stdout
    assert "passed=True" in result.stderr or '"passed": true' in result.stdout
