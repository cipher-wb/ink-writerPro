"""US-010: 仓库级红线 — 所有 Python CLI 入口必调 ``enable_windows_utf8_stdio()``.

策略：复用 ``scripts/audit_cross_platform.py:scan_c9_cli_utf8_stdio`` 作为权威
扫描器，确保实现与 audit 报告一致，避免"两套规则漂移"。

守护点：
- 新增带 ``if __name__ == "__main__":`` 的 Python 脚本必须在源码中出现
  ``enable_windows_utf8_stdio`` 字面量（import 或调用均可）——否则 Windows 用户
  中文输出会乱码（cp936 解码）。
- 除了整仓红线扫描，另外对 US-010 修复过的 4 处 CLI 入口做参数化固化测试，
  防止后续重构误删该 helper 引用。
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from audit_cross_platform import (  # noqa: E402
    collect_python_files,
    scan_c9_cli_utf8_stdio,
)


# ---------------------------------------------------------------------------
# 仓库红线
# ---------------------------------------------------------------------------


def test_repo_has_no_cli_entry_missing_utf8_stdio() -> None:
    """全仓扫描：每个 ``if __name__ == "__main__":`` 文件都必须出现
    ``enable_windows_utf8_stdio`` 字面量。"""
    py_files = collect_python_files(REPO_ROOT)
    findings = scan_c9_cli_utf8_stdio(py_files)
    offenders = [f"{f.path}:{f.line}" for f in findings]
    assert not offenders, (
        "发现 CLI 入口未调 enable_windows_utf8_stdio():\n  - "
        + "\n  - ".join(offenders)
        + "\n\n修复：文件顶部或 __main__ 块内 import runtime_compat 并调一次"
        " enable_windows_utf8_stdio()（Mac no-op）。"
    )


# ---------------------------------------------------------------------------
# US-010 修复文件逐个固化
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel_path",
    [
        "ink-writer/dashboard/server.py",
        "ink-writer/scripts/sync_plugin_version.py",
        "scripts/build_chapter_index.py",
        "tests/data_modules/test_data_modules.py",
    ],
)
def test_us010_fixed_file_references_helper(rel_path: str) -> None:
    """US-010 已修复的 4 个文件必须持续包含 ``enable_windows_utf8_stdio`` 字面量。"""
    path = REPO_ROOT / rel_path
    assert path.exists(), f"US-010 固化点缺失: {rel_path}"
    src = path.read_text(encoding="utf-8")
    assert "enable_windows_utf8_stdio" in src, (
        f"{rel_path} 丢失 enable_windows_utf8_stdio 引用——US-010 修复被回退"
    )


# ---------------------------------------------------------------------------
# Scanner 语义反例（确保规则没有被悄悄放宽）
# ---------------------------------------------------------------------------


def test_scanner_flags_synthetic_cli_without_helper(tmp_path: Path) -> None:
    """合成：一个带 ``__main__`` 但无 helper 的文件必须被 scanner 报告。"""
    bad = tmp_path / "bad_cli.py"
    bad.write_text(
        textwrap.dedent(
            """\
            def main():
                print("hello")


            if __name__ == "__main__":
                main()
            """
        ),
        encoding="utf-8",
    )
    findings = scan_c9_cli_utf8_stdio([bad])
    assert len(findings) == 1
    assert findings[0].category == "C9"
    assert str(bad) in findings[0].path


def test_scanner_skips_synthetic_cli_with_helper(tmp_path: Path) -> None:
    """合成：含 helper 引用的 ``__main__`` 文件不报告。"""
    good = tmp_path / "good_cli.py"
    good.write_text(
        textwrap.dedent(
            """\
            from runtime_compat import enable_windows_utf8_stdio


            def main():
                enable_windows_utf8_stdio()
                print("hello")


            if __name__ == "__main__":
                main()
            """
        ),
        encoding="utf-8",
    )
    findings = scan_c9_cli_utf8_stdio([good])
    assert findings == []


def test_scanner_skips_non_cli_files(tmp_path: Path) -> None:
    """合成：无 ``__main__`` 块的普通模块文件不报告。"""
    plain = tmp_path / "plain_module.py"
    plain.write_text(
        textwrap.dedent(
            """\
            def helper() -> int:
                return 42
            """
        ),
        encoding="utf-8",
    )
    findings = scan_c9_cli_utf8_stdio([plain])
    assert findings == []
