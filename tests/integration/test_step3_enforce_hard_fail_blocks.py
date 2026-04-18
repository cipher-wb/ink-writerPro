"""v16 US-005：enforce 默认模式下 anti-detection ZT 章节真阻断。

AC："构造 anti-detection ZT 章节（'次日清晨…' 开头），enforce 模式预期 exit=1"。

实现策略：
- 通过 subprocess 启动 ``python -m ink_writer.checker_pipeline.step3_runner``
  的 CLI 入口（覆盖默认模式 = enforce 的 E2E 路径）。
- 章节文本以 '次日清晨' 开头 + '众所周知' AI 套话 + '首先/其次/最后' 条目化
  段落，anti_detection_gate 自带 ZT 正则层会独立 hard-fail（不依赖 LLM）。
- ``INK_STEP3_LLM_CHECKER=off`` + ``INK_STEP3_LLM_POLISH=off`` 强制走 stub
  路径，避免 CI 中尝试 spawn ``claude`` CLI；ZT 拦截纯 Python。
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent.parent


_ZT_BAD_CHAPTER = (
    "次日清晨，主角睁开眼。众所周知，这是他人生最重要的一天。\n\n"
    "首先，他洗漱；其次，他出门；最后，他去工作。\n\n"
    "不仅如此，而且他还顺便救了只猫。与此同时，天空变黑。"
)


def _make_project(tmp_path: Path) -> Path:
    project = tmp_path / "book"
    ink_dir = project / ".ink"
    ink_dir.mkdir(parents=True)
    text_dir = project / "正文"
    text_dir.mkdir()
    (text_dir / "第0001章-ZT违规.md").write_text(_ZT_BAD_CHAPTER * 10, encoding="utf-8")

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


def test_enforce_default_blocks_zt_chapter_exit_1(tmp_path: Path) -> None:
    """enforce 默认 + ZT 章节 → CLI exit=1（真阻断）。"""
    project = _make_project(tmp_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    # 强制 stub 路径，避免 CI spawn claude CLI
    env["INK_STEP3_LLM_CHECKER"] = "off"
    env["INK_STEP3_LLM_POLISH"] = "off"
    # 不传 --mode 也不传 INK_STEP3_RUNNER_MODE，依赖 DEFAULT_MODE=enforce（v16 US-005）
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
        timeout=120,
    )

    assert result.returncode == 1, (
        f"expected exit=1 due to enforce+ZT hard fail, got {result.returncode}. "
        f"stdout={result.stdout[:500]!r} stderr={result.stderr[:500]!r}"
    )
    # 输出应显示 enforce 模式
    assert "mode=enforce" in result.stderr or "enforce" in result.stdout
