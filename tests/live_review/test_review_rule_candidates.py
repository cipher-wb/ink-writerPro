"""US-LR-010: 规则候选交互式审核 CLI 测试。

review_rule_candidates.py 通过 stdin 接收 y/n/s/q 输入，把结果写回 approved 字段。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "live-review" / "review_rule_candidates.py"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def candidates_copy(tmp_path) -> Path:
    """每个测试拷一份 sample_rule_candidates.json 到 tmp_path（避免污染 fixture）。"""
    src = FIXTURES / "sample_rule_candidates.json"
    dst = tmp_path / "rule_candidates.json"
    shutil.copy(src, dst)
    return dst


def _run(candidates_path: Path, stdin_input: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--candidates", str(candidates_path)],
        input=stdin_input,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )


def test_review_writes_approved_back(candidates_copy):
    """5 条候选全 null → stdin 'y\\nn\\ny\\ns\\ny\\n' → approved 写回 [T,F,T,None,T]。"""
    proc = _run(candidates_copy, "y\nn\ny\ns\ny\n")
    assert proc.returncode == 0, (
        f"exit={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    data = json.loads(candidates_copy.read_text(encoding="utf-8"))
    approved_seq = [c["approved"] for c in data]
    assert approved_seq == [True, False, True, None, True], (
        f"got {approved_seq}"
    )


def test_review_quit_keeps_unmodified(candidates_copy):
    """1 条响应 'y'，第 2 条响应 'q' → c1=True，c2-5 仍是初始 None。"""
    proc = _run(candidates_copy, "y\nq\n")
    assert proc.returncode == 0, (
        f"exit={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    data = json.loads(candidates_copy.read_text(encoding="utf-8"))
    approved_seq = [c["approved"] for c in data]
    assert approved_seq == [True, None, None, None, None], (
        f"got {approved_seq}; expected only c1 modified"
    )


def test_review_uppercase_and_whitespace_accepted(candidates_copy):
    """大小写 + 前后空白都接受，确保用户友好。"""
    proc = _run(candidates_copy, " Y \n N \n y \n S \n y \n")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(candidates_copy.read_text(encoding="utf-8"))
    approved_seq = [c["approved"] for c in data]
    assert approved_seq == [True, False, True, None, True]


def test_review_invalid_input_re_prompts(candidates_copy):
    """无效输入 'x' 后再正确输入仍能继续，不应中断或炸掉。"""
    # c1: 'x' (invalid, re-prompt) -> 'y'; c2-5: 'y' each
    proc = _run(candidates_copy, "x\ny\ny\ny\ny\ny\n")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(candidates_copy.read_text(encoding="utf-8"))
    approved_seq = [c["approved"] for c in data]
    assert approved_seq == [True, True, True, True, True]
