"""US-014 端到端 smoke 脚本集成测试。

目标：
1. 直接导入 `scripts.e2e_smoke_harness` 并跑一轮 smoke（Mac/Linux 本地真实执行），
   断言 init/write/verify/cleanup 四阶段全部 ok、`recent_full_texts` 被装填、
   `.ink/state.json` 与 index.db 章节游标一致。
2. 仓库级红线：`scripts/e2e_smoke.sh` / `.ps1` / `.cmd` 必须存在 + 关键安全字面量
   （`set -euo pipefail`、`Find-PythonLauncher`、BOM、powershell 转发）仍在源码里，
   防后续 PR 误删。

PRD 允许的首版退化路径（首版允许 skip LLM 实调用 / 用 mock adapter 替换）——
harness 用合成中文正文替代 writer-agent，测试的是数据流水线的跨平台健康度，
不是 writer 质量。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
HARNESS_PATH = SCRIPTS_DIR / "e2e_smoke_harness.py"
SH_PATH = SCRIPTS_DIR / "e2e_smoke.sh"
PS1_PATH = SCRIPTS_DIR / "e2e_smoke.ps1"
CMD_PATH = SCRIPTS_DIR / "e2e_smoke.cmd"


def _load_harness_module():
    """延迟加载 harness：避免 test collection 时触发 init_project import 副作用。

    用 importlib.util + sys.modules 预注册，防止 `@dataclass` 解析
    `StepResult.__module__` 拿到 None 时走到 `sys.modules.get(None).__dict__` 崩。
    """
    ink_scripts = REPO_ROOT / "ink-writer" / "scripts"
    scripts_dir = REPO_ROOT / "scripts"
    for candidate in (str(ink_scripts), str(scripts_dir), str(REPO_ROOT)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    module_name = "e2e_smoke_harness_under_test"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, HARNESS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # 先注册，再 exec，dataclass 才能解析 __module__
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


# ═══════════════════════════════════════════
# 集成：harness 真实跑一轮
# ═══════════════════════════════════════════


@pytest.mark.mac  # US-013: autoskip via conftest（Windows 单独路径 e2e_smoke.ps1 覆盖）
def test_harness_runs_end_to_end(tmp_path: Path, monkeypatch) -> None:
    """真实跑一轮 smoke：init/write/verify/cleanup 全部 ok。

    关键断言：
      - 整体 ok=True
      - 四个 step 全部 status=ok
      - verify.extra 包含 recent_full_texts_count=chapters
      - 日志文件真的写出来
    """
    harness = _load_harness_module()

    # 指向 tmp 的临时父目录（含中文 + 空格），避免污染 /tmp
    temp_parent = tmp_path / "smoke parent 目录"
    log_path = tmp_path / "reports" / "e2e-smoke-test.log"

    # 隔离 CWD 到 tmp_path，防止 init_project 把 pointer 写到 repo 的 .claude/
    monkeypatch.chdir(tmp_path)

    result: Dict[str, Any] = harness.run_smoke(
        chapters=3,
        keep=False,
        log_path=log_path,
        temp_parent=temp_parent,
    )

    assert result["ok"], f"smoke 整体失败: {json.dumps(result, ensure_ascii=False, indent=2)}"
    steps = {step["step"]: step for step in result["steps"]}
    assert set(steps.keys()) == {"init", "write", "verify", "cleanup"}
    for name in ("init", "write", "verify", "cleanup"):
        assert steps[name]["status"] == "ok", (name, steps[name])

    verify_extra = steps["verify"]["extra"]
    assert verify_extra["recent_full_texts_count"] == 3
    assert verify_extra["state_chapter"] == 3
    assert verify_extra["db_chapter"] == 3

    assert log_path.exists()
    log_text = log_path.read_text(encoding="utf-8")
    for expected in (
        "step=init status=ok",
        "step=write status=ok",
        "step=verify status=ok",
        "step=cleanup status=ok",
        "step=summary status=ok",
    ):
        assert expected in log_text, expected


@pytest.mark.mac  # US-013: autoskip via conftest
def test_harness_generates_chinese_and_space_path(tmp_path: Path, monkeypatch) -> None:
    """临时项目目录必须同时包含中文 + 空格（PRD 验收准则硬性要求）。"""
    harness = _load_harness_module()
    monkeypatch.chdir(tmp_path)

    project_dir = harness.create_temp_project_root(parent=tmp_path)
    name = str(project_dir)
    assert " " in name, f"路径未包含空格: {name}"
    assert any(0x4E00 <= ord(c) <= 0x9FFF for c in name), (
        f"路径未包含中文字符: {name}"
    )


# ═══════════════════════════════════════════
# 仓库级红线：三个脚本 + harness 必须存在 + 关键字面量守护
# ═══════════════════════════════════════════


def test_smoke_wrappers_present() -> None:
    for path in (HARNESS_PATH, SH_PATH, PS1_PATH, CMD_PATH):
        assert path.exists(), f"缺 {path.relative_to(REPO_ROOT)}"


def test_sh_wrapper_has_safety_header() -> None:
    body = SH_PATH.read_text(encoding="utf-8")
    assert body.startswith("#!/bin/bash"), "缺 shebang"
    assert "set -euo pipefail" in body, (
        "缺 set -euo pipefail（US-011/US-012 long-running agent-loop 脚本三件套之一）"
    )
    assert "find_python_launcher_bash" in body, (
        "缺 find_python_launcher_bash（US-009 跨平台 launcher primitive）"
    )
    assert "e2e_smoke_harness.py" in body, "必须转发到 harness"


def test_ps1_wrapper_has_utf8_bom_and_launcher() -> None:
    head = PS1_PATH.read_bytes()[:3]
    assert head == b"\xef\xbb\xbf", (
        f"e2e_smoke.ps1 缺 UTF-8 BOM（US-007 红线）"
    )
    body = PS1_PATH.read_text(encoding="utf-8-sig")
    assert "Find-PythonLauncher" in body, "缺 Find-PythonLauncher primitive"
    assert "$ErrorActionPreference" in body, "缺 $ErrorActionPreference"
    assert "e2e_smoke_harness.py" in body, "必须转发到 harness"


def test_cmd_wrapper_forwards_to_ps1() -> None:
    body = CMD_PATH.read_text(encoding="utf-8").lower()
    assert "powershell" in body
    assert "e2e_smoke.ps1" in body


def test_harness_exposes_cli_entry() -> None:
    """harness 本身必须是可运行 CLI（__main__ + enable_windows_utf8_stdio）。"""
    body = HARNESS_PATH.read_text(encoding="utf-8")
    assert 'if __name__ == "__main__"' in body
    assert "enable_windows_utf8_stdio" in body, (
        "CLI 入口必须声明 enable_windows_utf8_stdio（US-010 C9 红线）"
    )
    assert "def run_smoke" in body, "harness 必须暴露 run_smoke 公共 API 供测试复用"


def test_log_filename_template_stable() -> None:
    """reports/e2e-smoke-{mac,windows}.log 是 PRD 验收契约的一部分。"""
    body = HARNESS_PATH.read_text(encoding="utf-8")
    assert 'f"e2e-smoke-{tag}.log"' in body
