"""C8 — Python launcher 硬编码根除的专项测试（US-009）。

覆盖三条线：

1. ``runtime_compat.find_python_launcher()`` 的 Python helper 已在
   ``tests/infra/test_runtime_compat.py`` 测过；本文件补测 bash 侧
   的 ``find_python_launcher_bash`` —— 抠出函数体注入子 shell 验证
   Mac / Windows-style OSTYPE 两条分支。
2. ``env-setup.sh`` / ``ink-auto.sh`` 的 detector 抽取后在实跑中应
   正确设置 ``PYTHON_LAUNCHER`` / ``PY_LAUNCHER`` 变量。
3. 仓库红线：直接跑 ``scripts/audit_cross_platform.py`` 的 C8 scanner
   断言 finding 数 == 0；任何新增未打 pragma 的 ``python3`` / ``py -3``
   硬编码会直接挂 CI，守护 US-009 的承诺不回退。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


_BASH_FUNC_RE = re.compile(
    r"find_python_launcher_bash\s*\(\s*\)\s*\{.*?\n\}\n",
    re.DOTALL,
)


def _extract_bash_detector(script_path: Path) -> str:
    text = script_path.read_text(encoding="utf-8")
    match = _BASH_FUNC_RE.search(text)
    assert match is not None, f"find_python_launcher_bash not found in {script_path}"
    return match.group(0)


def _run_bash(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@pytest.fixture(scope="module")
def env_setup_detector() -> str:
    return _extract_bash_detector(REPO_ROOT / "ink-writer/scripts/env-setup.sh")


@pytest.fixture(scope="module")
def ink_auto_detector() -> str:
    return _extract_bash_detector(REPO_ROOT / "ink-writer/scripts/ink-auto.sh")


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
class TestBashDetectorEnvSetup:
    """env-setup.sh:find_python_launcher_bash → 设置 PYTHON_LAUNCHER。"""

    def test_macos_style_ostype_returns_python3(self, env_setup_detector: str) -> None:
        script = f"""
        set -eu
        OSTYPE=darwin23
        {env_setup_detector}
        find_python_launcher_bash
        echo "${{PYTHON_LAUNCHER}}"
        """
        result = _run_bash(script)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "python3"

    def test_linux_style_ostype_returns_python3(self, env_setup_detector: str) -> None:
        script = f"""
        set -eu
        OSTYPE=linux-gnu
        {env_setup_detector}
        find_python_launcher_bash
        echo "${{PYTHON_LAUNCHER}}"
        """
        result = _run_bash(script)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "python3"

    def test_msys_ostype_probes_runtime_candidates(
        self, env_setup_detector: str
    ) -> None:
        # 在 Mac 本机模拟 OSTYPE=msys 分支：py 多半不存在 → 回落到 python3
        # （假设 CI/开发机上 python3 可用）。
        script = f"""
        set -eu
        OSTYPE=msys
        {env_setup_detector}
        find_python_launcher_bash
        echo "${{PYTHON_LAUNCHER}}"
        """
        result = _run_bash(script)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() in {"py -3", "python3", "python"}


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
class TestBashDetectorInkAuto:
    """ink-auto.sh:find_python_launcher_bash → 设置 PY_LAUNCHER。"""

    def test_macos_style_ostype_returns_python3(self, ink_auto_detector: str) -> None:
        script = f"""
        set -eu
        OSTYPE=darwin23
        {ink_auto_detector}
        find_python_launcher_bash
        echo "${{PY_LAUNCHER}}"
        """
        result = _run_bash(script)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "python3"

    def test_msys_ostype_probes_runtime_candidates(
        self, ink_auto_detector: str
    ) -> None:
        script = f"""
        set -eu
        OSTYPE=msys
        {ink_auto_detector}
        find_python_launcher_bash
        echo "${{PY_LAUNCHER}}"
        """
        result = _run_bash(script)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() in {"py -3", "python3", "python"}


class TestSourceLevelInvariants:
    """源码级不变量 —— 无需运行，只读字符串即可断言。"""

    def test_env_setup_sh_exports_python_launcher(self) -> None:
        text = (REPO_ROOT / "ink-writer/scripts/env-setup.sh").read_text(
            encoding="utf-8"
        )
        assert "find_python_launcher_bash" in text
        # Step 6/7 必须走 $PYTHON_LAUNCHER
        assert "$PYTHON_LAUNCHER -X utf8" in text
        # export PYTHON_LAUNCHER 使下游脚本（ink.py / 其他 sourcer）可继承
        assert re.search(r"^export PYTHON_LAUNCHER\s*$", text, re.MULTILINE)

    def test_ink_auto_sh_uses_py_launcher_variable(self) -> None:
        text = (REPO_ROOT / "ink-writer/scripts/ink-auto.sh").read_text(
            encoding="utf-8"
        )
        assert "find_python_launcher_bash" in text
        # 所有 python3 调用（除 detector primitive）必须已替换为 $PY_LAUNCHER
        # 数一数字面量数量：detector 内部 3 处（注释+数组+赋值），其余应为 0
        lines = text.splitlines()
        bare_python3_invocations = [
            (idx + 1, line)
            for idx, line in enumerate(lines)
            if re.search(r"(?<![\w/])python3(?![\w/])", line)
            and "c8-ok" not in line
            and not line.lstrip().startswith("#")
        ]
        assert bare_python3_invocations == [], (
            f"未打 pragma 的 python3 硬编码残留: {bare_python3_invocations}"
        )

    def test_env_setup_ps1_find_pythonlauncher_has_pragma(self) -> None:
        text = (REPO_ROOT / "ink-writer/scripts/env-setup.ps1").read_text(
            encoding="utf-8-sig"
        )
        # Find-PythonLauncher 内含 'python3' 字面量必须带 c8-ok 标记
        assert "Find-PythonLauncher" in text
        for lineno, line in enumerate(text.splitlines(), start=1):
            if re.search(r"(?<![\w/])python3(?![\w/])", line) and not line.lstrip().startswith("#"):
                assert "c8-ok" in line, (
                    f"env-setup.ps1:{lineno} 出现非注释的 python3 字面量但未打 c8-ok pragma"
                )

    def test_ink_auto_ps1_has_no_raw_python3_invocation(self) -> None:
        text = (REPO_ROOT / "ink-writer/scripts/ink-auto.ps1").read_text(
            encoding="utf-8-sig"
        )
        for lineno, line in enumerate(text.splitlines(), start=1):
            if re.search(r"(?<![\w/])python3(?![\w/])", line) and not line.lstrip().startswith("#"):
                assert "c8-ok" in line, (
                    f"ink-auto.ps1:{lineno} 非注释 python3 字面量未打 c8-ok"
                )


class TestRepoRedLineC8:
    """仓库红线：scanner 的 C8 类别当前必须为 0。"""

    def test_scan_c8_python_launcher_returns_empty(self) -> None:
        # 延迟 import 避免全局副作用
        audit_root = REPO_ROOT / "scripts"
        sys.path.insert(0, str(audit_root))
        try:
            import audit_cross_platform as acp
        finally:
            sys.path.pop(0)

        findings = acp.scan_c8_python_launcher(REPO_ROOT)
        assert findings == [], (
            "C8 类别应该为 0 —— 新增的 python3/py -3 硬编码未打 pragma"
            f"\n具体 findings: {findings}"
        )


@pytest.mark.skipif(
    shutil.which("bash") is None or sys.platform == "win32",
    reason="Mac/Linux only: verify byte-level behavior preserved",
)
class TestMacByteLevelParity:
    """Mac 字节级一致：$PY_LAUNCHER 展开后与原来 python3 行为等价。"""

    def test_py_launcher_on_mac_expands_to_python3(
        self, ink_auto_detector: str
    ) -> None:
        # 在 Mac 的 darwin OSTYPE 下，$PY_LAUNCHER 必须 == "python3"
        script = f"""
        set -eu
        OSTYPE=darwin23
        {ink_auto_detector}
        find_python_launcher_bash
        # 用 $PY_LAUNCHER 跑一个真实 Python 单行，验证可执行
        $PY_LAUNCHER -c 'import sys; print(sys.version_info[0])'
        """
        result = _run_bash(script)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "3"
