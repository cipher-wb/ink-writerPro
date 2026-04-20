"""US-013: Validate @pytest.mark.windows / @pytest.mark.mac infrastructure.

Rationale: before US-013 every platform-gated test used
``@pytest.mark.skipif(sys.platform != "win32", ...)``. That boilerplate was
散落、易写错（写成 `== "win32"` / `!= "darwin"` 语义相反）而且 reason 文案各
异。US-013 统一为 ``@pytest.mark.windows`` / ``@pytest.mark.mac`` 两个声明式
marker，配合 ``tests/conftest.py::pytest_collection_modifyitems`` 的 autoskip
逻辑。

This module verifies:

1. Both markers are registered in ``pytest.ini`` (so ``--strict-markers`` 不炸)
2. Autoskip works on current platform (通过 pytester 内跑小 suite 验证)
3. 仓库红线：不允许在非 ``tests/conftest.py`` 之外继续用
   ``pytest.mark.skipif(sys.platform ...)`` 做纯平台门禁——这是本 US 要消除
   的 boilerplate。环境性 skipif（如 ``shutil.which("bash") is None``）允许
   保留，因为 marker 无法表达"环境缺某个可执行"的含义。
"""
from __future__ import annotations

import ast
import configparser
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTEST_INI = REPO_ROOT / "pytest.ini"
TESTS_CONFTEST = REPO_ROOT / "tests" / "conftest.py"


# ═══════════════════════════════════════════════════════════════════════════
# Rule 1: markers are registered
# ═══════════════════════════════════════════════════════════════════════════


def _parse_registered_markers() -> set[str]:
    """Return the set of marker names registered in pytest.ini."""
    parser = configparser.ConfigParser()
    parser.read(PYTEST_INI, encoding="utf-8")
    markers_block = parser["pytest"].get("markers", "")
    names: set[str] = set()
    for line in markers_block.splitlines():
        line = line.strip()
        if not line:
            continue
        # "name: description" or just "name"
        name = line.split(":", 1)[0].strip()
        if name:
            names.add(name)
    return names


def test_windows_marker_registered() -> None:
    assert "windows" in _parse_registered_markers(), (
        "US-013: pytest.ini 必须在 markers 下注册 `windows`，否则 --strict-markers 会告警。"
    )


def test_mac_marker_registered() -> None:
    assert "mac" in _parse_registered_markers(), (
        "US-013: pytest.ini 必须在 markers 下注册 `mac`，否则 --strict-markers 会告警。"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Rule 2: autoskip works on current platform
# ═══════════════════════════════════════════════════════════════════════════


def _run_pytest_subprocess(
    tmp_path: Path, test_source: str, *extra_args: str
) -> subprocess.CompletedProcess[str]:
    """Run pytest in a clean tmpdir containing a copied conftest + test file.

    Using subprocess.run（而非 pytester plugin）的理由：仓库顶层 conftest.py
    不 opt-in pytester（需要 ``pytest_plugins = ["pytester"]``），加进去会影
    响所有测试。subprocess 隔离更彻底，和 US-011/US-012 的 fake-claude 子进
    程 pattern 同构。
    """
    # 复制 conftest（提供 autoskip 逻辑）
    (tmp_path / "conftest.py").write_text(
        TESTS_CONFTEST.read_text(encoding="utf-8"), encoding="utf-8"
    )
    # 最小 pytest.ini 注册两个 marker
    (tmp_path / "pytest.ini").write_text(
        textwrap.dedent(
            """
            [pytest]
            markers =
                windows: Windows-only tests
                mac: Mac/Linux only tests
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "test_sample.py").write_text(test_source, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-v",
            "-p",
            "no:cacheprovider",
            "--no-header",
            "--no-cov",
            *extra_args,
            "test_sample.py",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_windows_marked_test_is_skipped_on_non_windows(tmp_path: Path) -> None:
    """在 Mac 上跑 @pytest.mark.windows 装饰的测试必须被 autoskip。"""
    if sys.platform == "win32":  # pragma: no cover - only exercised on Mac CI
        pytest.skip("本断言只在非 Windows 平台有意义")
    source = textwrap.dedent(
        """
        import pytest

        @pytest.mark.windows
        def test_windows_only():
            assert False, '应该被 autoskip，永不执行'

        def test_default_runs():
            assert True
        """
    ).lstrip()
    result = _run_pytest_subprocess(tmp_path, source)
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "1 passed" in combined and "1 skipped" in combined, combined


def test_mac_marked_test_runs_on_non_windows(tmp_path: Path) -> None:
    """在 Mac 上 @pytest.mark.mac 装饰的测试必须正常执行，不被 autoskip。"""
    if sys.platform == "win32":  # pragma: no cover
        pytest.skip("本断言只在非 Windows 平台有意义")
    source = textwrap.dedent(
        """
        import pytest

        @pytest.mark.mac
        def test_mac_runs():
            assert True
        """
    ).lstrip()
    result = _run_pytest_subprocess(tmp_path, source)
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "1 passed" in combined and "skipped" not in combined, combined


def test_skip_reason_mentions_marker_name(tmp_path: Path) -> None:
    """autoskip 的 reason 必须包含 marker 名——方便 grep 日志定位。"""
    if sys.platform == "win32":  # pragma: no cover
        pytest.skip("本断言只在非 Windows 平台有意义")
    source = textwrap.dedent(
        """
        import pytest

        @pytest.mark.windows
        def test_windows_only():
            pass
        """
    ).lstrip()
    result = _run_pytest_subprocess(tmp_path, source, "-rs")
    combined = result.stdout + result.stderr
    # -rs 段会打印 skip reason；我们的 reason 包含 "@pytest.mark.windows"
    assert "pytest.mark.windows" in combined, combined
    assert "Windows-only" in combined, combined


# ═══════════════════════════════════════════════════════════════════════════
# Rule 3: repo red-line — no new platform-gated skipif decorators outside
# tests/conftest.py (quarantine list 是 conftest 内部实现细节，不算)
# ═══════════════════════════════════════════════════════════════════════════


# 扫描范围：所有 tests/**/*.py，除 conftest.py 本身
_SYS_PLATFORM_NAMES = {"sys", "_sys"}  # 允许 _sys 别名


def _iter_test_files() -> list[Path]:
    return [
        p for p in (REPO_ROOT / "tests").rglob("*.py")
        if p.name != "conftest.py" and "__pycache__" not in p.parts
    ]


def _is_sys_platform_attr(node: ast.AST) -> bool:
    """匹配 `sys.platform` / `_sys.platform` Attribute 节点。"""
    if not isinstance(node, ast.Attribute):
        return False
    if node.attr != "platform":
        return False
    return isinstance(node.value, ast.Name) and node.value.id in _SYS_PLATFORM_NAMES


def _contains_sys_platform(node: ast.AST) -> bool:
    """递归扫描 AST 子树内是否出现 sys.platform。"""
    return any(_is_sys_platform_attr(sub) for sub in ast.walk(node))


def _is_skipif_call(node: ast.Call) -> bool:
    """匹配 `pytest.mark.skipif(...)`（或已 import 的别名，保守按 suffix 判）。"""
    func = node.func
    # 处理 pytest.mark.skipif / mark.skipif / skipif 三种书写
    if isinstance(func, ast.Attribute) and func.attr == "skipif":
        return True
    return isinstance(func, ast.Name) and func.id == "skipif"


def _find_platform_skipif_violations(path: Path) -> list[tuple[int, str]]:
    """在单文件中找到使用 sys.platform 的 skipif 调用。

    返回 (行号, 上下文片段)。允许保留那些与 env gate 组合的（如
    `shutil.which("bash") is None or sys.platform == "win32"`），因为 US-013
    的 pattern 已经要求把平台部分拆出去——但如果代码里还保留这种组合，我们
    也报告，督促作者拆分。
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_skipif_call(node):
            continue
        if any(_contains_sys_platform(arg) for arg in node.args):
            src = ast.unparse(node)
            violations.append((node.lineno, src[:120]))
    return violations


def test_repo_has_no_platform_skipif_outside_conftest() -> None:
    """仓库红线：非 conftest.py 文件不得用 ``pytest.mark.skipif(sys.platform ...)``。

    US-013 已消除所有已知违规点。未来 PR 若再用 skipif 门 sys.platform，CI
    直接挂——要么改用 ``@pytest.mark.windows`` / ``@pytest.mark.mac``，要么
    把平台检测拆出来放在 conftest.py（conftest.py 是允许的，因为 autoskip
    逻辑本身需要读 sys.platform）。
    """
    violations: list[str] = []
    for path in _iter_test_files():
        for lineno, snippet in _find_platform_skipif_violations(path):
            rel = path.relative_to(REPO_ROOT)
            violations.append(f"  {rel}:{lineno}  {snippet}")
    assert not violations, (
        "US-013 红线：请把下列 `pytest.mark.skipif(sys.platform ...)` 改为 "
        "`@pytest.mark.windows` 或 `@pytest.mark.mac`（或拆出环境 gate）:\n"
        + "\n".join(violations)
    )


# ═══════════════════════════════════════════════════════════════════════════
# Rule 4: 固化已迁移文件——防止 revert
# ═══════════════════════════════════════════════════════════════════════════


_MIGRATED_FILES = (
    "tests/infra/test_runtime_compat.py",
    "tests/scripts/test_ralph_sh_smoke.py",
    "tests/scripts/test_ink_auto_smoke.py",
    "tests/core/test_python_launcher.py",
)


@pytest.mark.parametrize("rel_path", _MIGRATED_FILES)
def test_migrated_file_uses_platform_marker(rel_path: str) -> None:
    """已迁移文件必须出现 `pytest.mark.windows` 或 `pytest.mark.mac` 字面量。"""
    text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
    has_marker = ("pytest.mark.windows" in text) or ("pytest.mark.mac" in text)
    assert has_marker, (
        f"US-013: {rel_path} 应使用 @pytest.mark.windows / @pytest.mark.mac，"
        "不能回退到 pytest.mark.skipif(sys.platform ...) boilerplate。"
    )
