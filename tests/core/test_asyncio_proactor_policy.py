"""tests/core/test_asyncio_proactor_policy.py — US-005 asyncio Proactor 策略验证。

覆盖 CLAUDE.md "Windows 兼容守则" 中关于 asyncio 入口的约束：

1. **`set_windows_proactor_policy()` 是 idempotent**：多次调用无副作用；Mac 返回
   False，Windows 首次 True、之后 True（已设 cache）。
2. **Mac/Linux 不改默认事件循环策略**：helper 只在 ``sys.platform == "win32"``
   时操作策略对象。
3. **跨平台：`asyncio.create_subprocess_exec` 可正常 spawn Python 子进程并回收
   UTF-8 stdout**——Mac 默认 event loop 已可，Windows 需 Proactor。
4. **仓库红线 #1（非 tests）**：任何会调 `asyncio.run` 的非测试入口文件，
   必须显式出现 `set_windows_proactor_policy` 字面量（可用 helper 也可用手写
   equivalent）——防止后续 PR 引入新的 asyncio 入口忘记加策略。
5. **仓库红线 #2（tests 分支）**：``tests/conftest.py`` 必须调
   `set_windows_proactor_policy`，确保所有下游 test file 的 asyncio.run 自动
   继承该策略（pytest 会在 collect 阶段先加载 conftest）。
"""

from __future__ import annotations

import ast
import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

INK_WRITER_SCRIPTS = REPO_ROOT / "ink-writer" / "scripts"
if str(INK_WRITER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(INK_WRITER_SCRIPTS))

from runtime_compat import set_windows_proactor_policy  # noqa: E402

from audit_cross_platform import (  # noqa: E402
    EXCLUDE_DIR_NAMES,
    iter_files,
    safe_read_text,
)


# ---------------------------------------------------------------------------
# helper 行为：idempotent + 平台感知
# ---------------------------------------------------------------------------


def test_set_windows_proactor_policy_is_idempotent_on_mac():
    """Mac/Linux 上 helper 始终返回 False 且不抛异常。"""
    if sys.platform == "win32":  # pragma: no cover - tested on Windows branch
        pytest.skip("mac/linux-only assertion")
    assert set_windows_proactor_policy() is False
    # 反复调不抛、不改变 event loop 策略
    for _ in range(3):
        assert set_windows_proactor_policy() is False


def test_set_windows_proactor_policy_does_not_mutate_mac_policy():
    """Mac 上调 helper 后，默认 event loop policy 类名不应被改为 Proactor。"""
    if sys.platform == "win32":  # pragma: no cover
        pytest.skip("mac/linux-only assertion")
    # Access internal policy state via the deprecated API on purpose: helper
    # only mutates this on Windows; on Mac we merely assert it stays the same.
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        before = asyncio.get_event_loop_policy().__class__.__name__
        set_windows_proactor_policy()
        after = asyncio.get_event_loop_policy().__class__.__name__
    assert before == after


# ---------------------------------------------------------------------------
# 跨平台：asyncio 子进程能跑通
# ---------------------------------------------------------------------------


def test_asyncio_create_subprocess_exec_returns_utf8_stdout():
    """应用 helper 后，asyncio.create_subprocess_exec 能启动子进程并 UTF-8
    解码中文 stdout。Mac 上本来就能跑，Windows 上依赖 Proactor."""
    set_windows_proactor_policy()

    async def _run() -> str:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import sys; sys.stdout.reconfigure(encoding='utf-8'); print('你好世界_测试_🌟')",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode("utf-8").strip()

    result = asyncio.run(_run())
    assert "你好世界_测试_🌟" == result


def test_asyncio_create_subprocess_exec_with_chinese_arg():
    """中文参数透传到 asyncio 子进程，echo 回来能正确 UTF-8 解码。"""
    set_windows_proactor_policy()

    async def _run(arg: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import sys; sys.stdout.reconfigure(encoding='utf-8'); "
            "print(sys.argv[1])",
            arg,
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode("utf-8").strip()

    assert asyncio.run(_run("参数_✓")) == "参数_✓"


# ---------------------------------------------------------------------------
# 仓库红线：非 tests 的 asyncio 入口文件必含 set_windows_proactor_policy 字面量
# ---------------------------------------------------------------------------


def _uses_asyncio_entry(text: str) -> bool:
    triggers = (
        "asyncio.run(",
        "asyncio.new_event_loop(",
        "asyncio.get_event_loop(",
        "asyncio.run_until_complete(",
    )
    return any(t in text for t in triggers)


def test_repo_non_test_asyncio_entries_declare_proactor_policy():
    """所有非 tests/ 的 .py 文件，只要调 asyncio.run 等入口，就必须在同一文件
    内出现 set_windows_proactor_policy 字面量。守护后续 PR 不回退。"""
    offenders: list[str] = []
    for path in iter_files(REPO_ROOT, (".py",)):
        rel = path.relative_to(REPO_ROOT)
        parts = set(rel.parts)
        if "tests" in parts:
            continue
        # archive 等已由 iter_files 的 EXCLUDE_DIR_NAMES 排除
        text = safe_read_text(path)
        if not text:
            continue
        if not _uses_asyncio_entry(text):
            continue
        if "set_windows_proactor_policy" not in text:
            offenders.append(str(rel))
    assert not offenders, (
        f"以下非测试入口调用了 asyncio.run 但未声明 set_windows_proactor_policy："
        f" {offenders}"
    )


def test_tests_conftest_declares_proactor_policy():
    """tests/conftest.py 必须调 set_windows_proactor_policy，让下游 test
    file 自动继承策略，避免每个 test 文件都要显式调。"""
    conftest = REPO_ROOT / "tests" / "conftest.py"
    assert conftest.is_file(), conftest
    text = safe_read_text(conftest)
    assert text, conftest
    assert "set_windows_proactor_policy" in text, (
        "tests/conftest.py 必须在 module load 时调 set_windows_proactor_policy，"
        "否则 asyncio.run 的 test 在 Windows 上会遇到 NotImplementedError"
    )

    # 进一步静态验证：必须是 call（不是注释或文档字符串里提及）
    tree = ast.parse(text)
    call_found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name == "set_windows_proactor_policy":
                call_found = True
                break
    assert call_found, "conftest 仅提及但未真实调用 set_windows_proactor_policy"


# ---------------------------------------------------------------------------
# 扫描器行为：ancestor conftest 覆盖的 test 文件不应被 C4 报告
# ---------------------------------------------------------------------------


def test_c4_scanner_honors_ancestor_conftest(tmp_path: Path):
    """tmp_path 下放一个伪 test file（调 asyncio.run，无 policy），但
    ancestor conftest 里有 policy 调用——scanner 不应 C4 报错。"""
    from audit_cross_platform import scan_c4_asyncio

    (tmp_path / "conftest.py").write_text(
        "from runtime_compat import set_windows_proactor_policy\n"
        "set_windows_proactor_policy()\n",
        encoding="utf-8",
    )
    test_file = tmp_path / "test_fake_asyncio.py"
    test_file.write_text(
        "import asyncio\n"
        "async def noop():\n"
        "    return 1\n"
        "asyncio.run(noop())\n",
        encoding="utf-8",
    )

    findings = scan_c4_asyncio([test_file], root=tmp_path)
    assert findings == [], findings


def test_c4_scanner_still_reports_when_no_ancestor_conftest(tmp_path: Path):
    """无 ancestor conftest 时，scanner 仍应报告 C4（守护 inverse 逻辑不出错）。"""
    from audit_cross_platform import scan_c4_asyncio

    test_file = tmp_path / "lone_cli.py"
    test_file.write_text(
        "import asyncio\n"
        "async def noop():\n"
        "    return 1\n"
        "asyncio.run(noop())\n",
        encoding="utf-8",
    )

    findings = scan_c4_asyncio([test_file], root=tmp_path)
    assert len(findings) == 1
    assert findings[0].category == "C4"
    assert findings[0].severity == "High"
