"""US-026: ANTHROPIC_API_KEY 入口守卫回归测试。

覆盖 scripts/editor-wisdom/03_classify.py 与 05_extract_rules.py：
当 ANTHROPIC_API_KEY 缺失时必须立即 sys.exit(2) 并把错误写入 stderr，
严禁进入 per-file loop 产生 "API calls: 0" 假成功。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "editor-wisdom"


def _run_without_key(script_name: str) -> subprocess.CompletedProcess[str]:
    """Run script with ANTHROPIC_API_KEY removed from env, capture stderr/exit."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    # Mirror pytest.ini pythonpath so the subprocess can import ink_writer package.
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO_ROOT), existing_pp]))
    script_path = SCRIPTS_DIR / script_name
    assert script_path.exists(), f"missing script: {script_path}"
    return subprocess.run(
        [sys.executable, str(script_path)],
        env=env,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=30, encoding="utf-8",
    )


@pytest.mark.parametrize("script_name", ["03_classify.py", "05_extract_rules.py"])
def test_api_key_guard_exits_2(script_name: str) -> None:
    """Missing ANTHROPIC_API_KEY must trigger exit code 2 immediately."""
    result = _run_without_key(script_name)
    assert result.returncode == 2, (
        f"{script_name} exited {result.returncode}, expected 2. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


@pytest.mark.parametrize("script_name", ["03_classify.py", "05_extract_rules.py"])
def test_api_key_guard_writes_stderr(script_name: str) -> None:
    """Guard must mention ANTHROPIC_API_KEY in stderr so CI logs are searchable."""
    result = _run_without_key(script_name)
    assert "ANTHROPIC_API_KEY" in result.stderr, (
        f"{script_name} stderr missing ANTHROPIC_API_KEY hint: {result.stderr!r}"
    )


@pytest.mark.parametrize("script_name", ["03_classify.py", "05_extract_rules.py"])
def test_api_key_guard_no_stdout_success_lie(script_name: str) -> None:
    """Guard must NOT print 'API calls' success message (pre-US-007 false-pass bug)."""
    result = _run_without_key(script_name)
    assert "API calls" not in result.stdout, (
        f"{script_name} produced fake success stdout without API key: {result.stdout!r}"
    )


def test_max_consecutive_failures_constant_defined() -> None:
    """Both scripts must declare MAX_CONSECUTIVE_FAILURES abort threshold."""
    for script_name in ("03_classify.py", "05_extract_rules.py"):
        text = (SCRIPTS_DIR / script_name).read_text(encoding="utf-8")
        assert "MAX_CONSECUTIVE_FAILURES" in text, (
            f"{script_name} missing MAX_CONSECUTIVE_FAILURES abort counter"
        )
