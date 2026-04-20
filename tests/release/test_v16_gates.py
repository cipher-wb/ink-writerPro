"""v16.0.0 发版门禁测试（US-027）。

门禁清单：
  G1. 版本号一致性：plugin.json.version == pyproject.toml.version == marketplace.json 内
      ink-writer plugin 的 version == "16.0.0"。
  G2. 全维度 sanity 导入：creativity / checker_pipeline / parallel / editor_wisdom
      四大核心子系统必须 importable（防止循环引用 / 模块被误删的回归）。
  G3. scripts/verify_docs.py 当前仓库状态下跑通（subprocess exit == 0）。

这些测试**只在发版时提供保护**，对日常开发无侵入：它们读取已提交的版本号文件、
导入已存在的模块、子进程跑一个文档守卫脚本，不触达 LLM、DB 与网络。

Ralph v16 US-027 提交。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_VERSION = "21.0.0"


# ---------------------------------------------------------------------------
# G1. 版本号一致性
# ---------------------------------------------------------------------------


def _read_plugin_version() -> str:
    plugin_json = ROOT / "ink-writer" / ".claude-plugin" / "plugin.json"
    data = json.loads(plugin_json.read_text(encoding="utf-8"))
    return data["version"]


def _read_pyproject_version() -> str:
    py = ROOT / "pyproject.toml"
    with py.open("rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


def _read_marketplace_version() -> str:
    mp = ROOT / ".claude-plugin" / "marketplace.json"
    data = json.loads(mp.read_text(encoding="utf-8"))
    for plugin in data.get("plugins", []):
        if plugin.get("name") == "ink-writer":
            return plugin["version"]
    raise AssertionError("ink-writer plugin not found in marketplace.json")


def test_plugin_json_version_matches_expected() -> None:
    assert _read_plugin_version() == EXPECTED_VERSION


def test_pyproject_version_matches_expected() -> None:
    assert _read_pyproject_version() == EXPECTED_VERSION


def test_marketplace_version_matches_expected() -> None:
    assert _read_marketplace_version() == EXPECTED_VERSION


def test_all_three_versions_mutually_consistent() -> None:
    """plugin.json / pyproject.toml / marketplace.json 三处版本号必须相等。"""
    p = _read_plugin_version()
    y = _read_pyproject_version()
    m = _read_marketplace_version()
    assert p == y == m, (
        f"version drift: plugin.json={p} pyproject.toml={y} marketplace.json={m}"
    )


# ---------------------------------------------------------------------------
# G2. 全维度 sanity 导入
# ---------------------------------------------------------------------------


CORE_SUBSYSTEMS = (
    # (module path, attribute or None — 仅 import 即可)
    "ink_writer.creativity",
    "ink_writer.creativity.name_validator",
    "ink_writer.creativity.gf_validator",
    "ink_writer.creativity.sensitive_lexicon_validator",
    "ink_writer.creativity.perturbation_engine",
    "ink_writer.creativity.retry_loop",
    "ink_writer.checker_pipeline",
    "ink_writer.checker_pipeline.runner",
    "ink_writer.checker_pipeline.step3_runner",
    "ink_writer.parallel",
    "ink_writer.parallel.chapter_lock",
    "ink_writer.parallel.pipeline_manager",
    "ink_writer.editor_wisdom",
    "ink_writer.editor_wisdom.checker",
    "ink_writer.editor_wisdom.arbitration",
)


@pytest.mark.parametrize("modname", CORE_SUBSYSTEMS)
def test_core_subsystems_importable(modname: str) -> None:
    """v16 四大核心子系统必须无异常导入（防模块误删 / 循环引用回归）。"""
    __import__(modname)


# ---------------------------------------------------------------------------
# G3. verify_docs.py 跑通
# ---------------------------------------------------------------------------


def test_verify_docs_exit_zero() -> None:
    """scripts/verify_docs.py 当前仓库状态下必须 exit 0。"""
    script = ROOT / "scripts" / "verify_docs.py"
    assert script.exists(), f"verify_docs.py not found at {script}"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120, encoding="utf-8",
    )
    assert result.returncode == 0, (
        f"verify_docs.py failed with exit {result.returncode}\n"
        f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    )
