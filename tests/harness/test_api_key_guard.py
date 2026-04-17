"""US-007: editor-wisdom 脚本的 API Key 入口校验测试。

验证 03_classify.py / 05_extract_rules.py 在无 ANTHROPIC_API_KEY 时立即退出 exit code 1 + stderr 含 key 名称。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = [
    ROOT / "scripts" / "editor-wisdom" / "03_classify.py",
    ROOT / "scripts" / "editor-wisdom" / "05_extract_rules.py",
]


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_missing_api_key_fails_fast(script: Path):
    """无 ANTHROPIC_API_KEY 时脚本立即 exit 1 + stderr 提示。"""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["PYTHONPATH"] = f"{ROOT / 'ink-writer' / 'scripts'}:{ROOT}"

    result = subprocess.run(
        [sys.executable, str(script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0, f"expected non-zero exit, got 0; stdout={result.stdout}"
    combined = result.stdout + result.stderr
    assert "ANTHROPIC_API_KEY" in combined, (
        f"expected 'ANTHROPIC_API_KEY' in output; got:\n{combined}"
    )
