"""ink-auto.sh find_project_root 优先级回归（针对 2026-04-29 cipher cwd-mismatch bug）

历史现象：
  Claude Code 调 bash 子 shell 时 cwd 不在用户小说目录，env-setup.sh
  已 export PROJECT_ROOT=/Users/cipher/ai/小说/农村养殖场，但 ink-auto.sh
  里的 find_project_root **只看 $PWD 上溯**，完全无视 env var。
  → 已初始化项目被当成空目录 → 走 v27 自动 init → 用户每次跑都"重新初始化"

修复：find_project_root 解析顺序改为
  1. INK_PROJECT_ROOT env var
  2. PROJECT_ROOT env var
  3. CLAUDE_PROJECT_DIR env var
  4. PWD 上溯（兜底）

每个候选都要验证 .ink/state.json 实际存在才返回。

本测试用真实 bash 子 shell + 控制 cwd / env 来验证不同路径下的行为。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INK_AUTO_SH = REPO_ROOT / "ink-writer" / "scripts" / "ink-auto.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="需要 bash")


def _extract_bash_function(source: str, fn_name: str) -> str:
    pattern = re.compile(
        r"^" + re.escape(fn_name) + r"\s*\(\s*\)\s*\{\s*\n(?P<body>.*?)\n\}\s*\n",
        re.DOTALL | re.MULTILINE,
    )
    m = pattern.search(source)
    if not m:
        raise AssertionError(f"未能抠到 {fn_name} 函数体")
    return f"{fn_name}() {{\n{m.group('body')}\n}}\n"


def _make_inited_project(root: Path) -> Path:
    """在 root 下创建一个含 .ink/state.json 的最小已初始化项目结构。"""
    (root / ".ink").mkdir(parents=True)
    (root / ".ink" / "state.json").write_text(
        json.dumps({"progress": {"current_chapter": 1}}, ensure_ascii=False),
        encoding="utf-8",
    )
    return root


def _run_find_project_root(
    *, cwd: Path, env: dict[str, str]
) -> tuple[int, str, str]:
    """抠出 find_project_root 函数体，在指定 cwd + env 下调用，返回 (rc, stdout, stderr)。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    func_body = _extract_bash_function(src, "find_project_root")

    harness_dir = cwd  # 直接用 cwd 作 harness 目录
    harness = harness_dir / "_harness_find_proj.sh"
    harness.write_text(
        "#!/bin/bash\n"
        "set -uo pipefail\n"
        f"{func_body}\n"
        'find_project_root || echo "__NOT_FOUND__"\n',
        encoding="utf-8",
    )

    full_env = {"PATH": "/usr/bin:/bin"}  # 最小 PATH 避免污染
    full_env.update(env)

    result = subprocess.run(
        ["bash", str(harness)],
        capture_output=True, text=True, encoding="utf-8",
        timeout=10, check=False,
        cwd=str(cwd), env=full_env,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


# ───────────────────────────────────────────────────────────────
# Bug 复现：cwd 不在小说目录时，旧实现会找不到项目
# ───────────────────────────────────────────────────────────────


def test_finds_via_ink_project_root_env_var(tmp_path):
    """INK_PROJECT_ROOT env var 指向已初始化项目时，cwd 在哪都应找到。

    覆盖场景：用户/上层显式注入 INK_PROJECT_ROOT 时（最高优先级）。
    """
    novel = _make_inited_project(tmp_path / "我的小说")
    other_cwd = tmp_path / "elsewhere"  # 完全无关的 cwd
    other_cwd.mkdir()

    rc, stdout, _ = _run_find_project_root(
        cwd=other_cwd,
        env={"INK_PROJECT_ROOT": str(novel)},
    )
    assert rc == 0
    assert Path(stdout).resolve() == novel.resolve(), (
        f"INK_PROJECT_ROOT 优先级最高，应直接返回 {novel}，实际 {stdout}"
    )


def test_finds_via_project_root_env_var(tmp_path):
    """PROJECT_ROOT env var（env-setup.sh 已 export）应被识别。

    这是 cipher 实测的具体场景：env-setup.sh 算好 PROJECT_ROOT，
    但旧 find_project_root 完全忽略它。
    """
    novel = _make_inited_project(tmp_path / "农村养殖场")
    other_cwd = tmp_path / "claude-cwd"
    other_cwd.mkdir()

    rc, stdout, _ = _run_find_project_root(
        cwd=other_cwd,
        env={"PROJECT_ROOT": str(novel)},
    )
    assert rc == 0
    assert Path(stdout).resolve() == novel.resolve(), (
        f"PROJECT_ROOT env 指向 {novel}，应被采用，实际 {stdout}"
    )


def test_finds_via_claude_project_dir_env_var(tmp_path):
    """CLAUDE_PROJECT_DIR 兜底优先级。"""
    novel = _make_inited_project(tmp_path / "claude-novel")
    other_cwd = tmp_path / "wrong-cwd"
    other_cwd.mkdir()

    rc, stdout, _ = _run_find_project_root(
        cwd=other_cwd,
        env={"CLAUDE_PROJECT_DIR": str(novel)},
    )
    assert rc == 0
    assert Path(stdout).resolve() == novel.resolve()


def test_priority_order_ink_project_root_wins(tmp_path):
    """三个 env var 同时设置时，INK_PROJECT_ROOT 优先级最高。"""
    a = _make_inited_project(tmp_path / "A_ink_proj_root")
    b = _make_inited_project(tmp_path / "B_proj_root")
    c = _make_inited_project(tmp_path / "C_claude_dir")
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()

    rc, stdout, _ = _run_find_project_root(
        cwd=other_cwd,
        env={
            "INK_PROJECT_ROOT": str(a),
            "PROJECT_ROOT": str(b),
            "CLAUDE_PROJECT_DIR": str(c),
        },
    )
    assert rc == 0
    assert Path(stdout).resolve() == a.resolve(), (
        "INK_PROJECT_ROOT 优先级应最高"
    )


def test_skips_invalid_env_falls_through_to_next(tmp_path):
    """env var 指向无 .ink/state.json 的目录时跳过，走下一个候选。

    防止"用户设错了 INK_PROJECT_ROOT 之后整个解析链坏掉"。
    """
    fake_ink_root = tmp_path / "fake_no_state"
    fake_ink_root.mkdir()  # 没 .ink/state.json

    real_novel = _make_inited_project(tmp_path / "real-novel")
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()

    rc, stdout, _ = _run_find_project_root(
        cwd=other_cwd,
        env={
            "INK_PROJECT_ROOT": str(fake_ink_root),  # 无效，应跳过
            "PROJECT_ROOT": str(real_novel),         # 有效，应采用
        },
    )
    assert rc == 0
    assert Path(stdout).resolve() == real_novel.resolve()


# ───────────────────────────────────────────────────────────────
# 兜底：PWD 上溯（旧行为）保留
# ───────────────────────────────────────────────────────────────


def test_pwd_upward_search_still_works(tmp_path):
    """env var 都没设时，从 cwd 向上找 .ink/state.json（保留旧 fallback）。"""
    novel = _make_inited_project(tmp_path / "fallback-novel")
    deep_cwd = novel / "正文" / "subdir"
    deep_cwd.mkdir(parents=True)

    rc, stdout, _ = _run_find_project_root(
        cwd=deep_cwd,
        env={},  # 不设任何 env var
    )
    assert rc == 0
    assert Path(stdout).resolve() == novel.resolve(), (
        "兜底 PWD 上溯应能从子目录找到根"
    )


def test_returns_failure_when_nothing_found(tmp_path):
    """所有候选都失败时返回非 0 + 空 stdout（让 v27 路径接管）。"""
    other_cwd = tmp_path / "totally-empty"
    other_cwd.mkdir()

    rc, stdout, _ = _run_find_project_root(
        cwd=other_cwd,
        env={},
    )
    assert rc != 0 or stdout == "" or stdout == "__NOT_FOUND__", (
        f"无任何已初始化项目时应失败，rc={rc}, stdout={stdout!r}"
    )


# ───────────────────────────────────────────────────────────────
# 静态守护
# ───────────────────────────────────────────────────────────────


def test_function_consults_env_vars_in_source():
    """源码层守护：find_project_root 必须查询三个 env var 之一。"""
    src = INK_AUTO_SH.read_text(encoding="utf-8")
    func_body = _extract_bash_function(src, "find_project_root")

    assert "INK_PROJECT_ROOT" in func_body, (
        "find_project_root 必须支持 INK_PROJECT_ROOT env var 优先级"
    )
    assert "PROJECT_ROOT" in func_body, (
        "find_project_root 必须支持 PROJECT_ROOT env var"
    )
    assert "CLAUDE_PROJECT_DIR" in func_body, (
        "find_project_root 必须支持 CLAUDE_PROJECT_DIR env var"
    )
