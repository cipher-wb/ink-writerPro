"""Tests for scripts/audit_cross_platform.py (US-001).

构造已知风险文件，验证 9 类扫描器都能正确检出（覆盖率 ≥95%）。
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from audit_cross_platform import (  # noqa: E402
    AuditReport,
    Finding,
    SEVERITY_ORDER,
    render_markdown,
    run_audit,
    scan_c1_open_encoding,
    scan_c2_hardcoded_paths,
    scan_c3_subprocess,
    scan_c4_asyncio,
    scan_c5_symlink,
    scan_c6_sh_ps1_cmd_parity,
    scan_c7_skill_md_windows_block,
    scan_c8_python_launcher,
    scan_c9_cli_utf8_stdio,
)


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------


def _detection_rate(findings: list[Finding], expected_files: list[Path]) -> float:
    """统计 findings 是否覆盖了所有 expected_files（按文件计）。"""
    if not expected_files:
        return 1.0
    detected = {Path(f.path).resolve() for f in findings}
    expected = {p.resolve() for p in expected_files}
    return len(detected & expected) / len(expected)


# ---------------------------------------------------------------------------
# C1: open / read_text / write_text 缺 encoding
# ---------------------------------------------------------------------------


def test_c1_detects_open_without_encoding(tmp_path: Path) -> None:
    bad = tmp_path / "bad_open.py"
    bad.write_text(
        textwrap.dedent(
            """\
            from pathlib import Path

            def load():
                with open("foo.txt") as fh:  # 缺 encoding
                    return fh.read()

            def save(data):
                Path("out.txt").write_text(data)  # 缺 encoding

            def read_path():
                return Path("in.txt").read_text()  # 缺 encoding
            """
        ),
        encoding="utf-8",
    )
    good = tmp_path / "good_open.py"
    good.write_text(
        textwrap.dedent(
            """\
            from pathlib import Path

            def load():
                with open("foo.txt", encoding="utf-8") as fh:
                    return fh.read()

            def save(data):
                Path("out.txt").write_text(data, encoding="utf-8")

            def binary():
                with open("bin.dat", "rb") as fh:
                    return fh.read()
            """
        ),
        encoding="utf-8",
    )
    findings = scan_c1_open_encoding([bad, good])
    bad_findings = [f for f in findings if f.path == str(bad)]
    good_findings = [f for f in findings if f.path == str(good)]
    assert len(bad_findings) >= 3, f"应检出 3 处，实得 {bad_findings}"
    assert good_findings == [], f"good 文件不应有 finding，实得 {good_findings}"
    assert all(f.category == "C1" for f in bad_findings)


def test_c1_skips_binary_open_with_keyword(tmp_path: Path) -> None:
    src = tmp_path / "kw_binary.py"
    src.write_text(
        textwrap.dedent(
            """\
            def f():
                return open("x.bin", mode="rb")
            """
        ),
        encoding="utf-8",
    )
    assert scan_c1_open_encoding([src]) == []


def test_c1_skips_path_open_binary_mode(tmp_path: Path) -> None:
    """Path.open("rb") —— 首位置参数即 mode，不得误报（US-002 修复）。"""
    src = tmp_path / "path_bin.py"
    src.write_text(
        textwrap.dedent(
            """\
            from pathlib import Path

            def load():
                with Path("x.bin").open("rb") as fh:
                    return fh.read()
            """
        ),
        encoding="utf-8",
    )
    assert scan_c1_open_encoding([src]) == []


def test_c1_skips_non_file_open_receivers(tmp_path: Path) -> None:
    """webbrowser.open / os.open / socket.open 等非文件 I/O 不得误报（US-002 修复）。"""
    src = tmp_path / "non_file.py"
    src.write_text(
        textwrap.dedent(
            """\
            import webbrowser
            import os
            import socket

            def nav():
                webbrowser.open("https://example.com")

            def fd():
                return os.open("/tmp/x", os.O_RDONLY)

            class Wrapper:
                def run(self, conn):
                    self.driver.open("/page")
                    conn.open()
            """
        ),
        encoding="utf-8",
    )
    findings = scan_c1_open_encoding([src])
    assert findings == [], f"不应误报非文件 I/O 的 .open()，实得 {findings}"


# ---------------------------------------------------------------------------
# C2: 硬编码路径
# ---------------------------------------------------------------------------


def test_c2_detects_hardcoded_path_literal(tmp_path: Path) -> None:
    src = tmp_path / "paths.py"
    src.write_text(
        textwrap.dedent(
            """\
            ROOT = "ink-writer/scripts/runtime_compat.py"
            DEEP = "a/b/c/d/e.txt"
            URL = "https://example.com/some/page"
            SHORT = "a/b"
            SENTENCE = "this is a/some text with spaces"
            """
        ),
        encoding="utf-8",
    )
    findings = scan_c2_hardcoded_paths([src])
    msgs = [f.message for f in findings]
    # 应检出 ROOT / DEEP，不应误报 URL / SHORT / SENTENCE
    assert any("ink-writer/scripts/runtime_compat.py" in m for m in msgs)
    assert any("a/b/c/d/e.txt" in m for m in msgs)
    assert not any("example.com" in m for m in msgs)
    assert not any('"a/b"' in m for m in msgs)


# ---------------------------------------------------------------------------
# C3: subprocess
# ---------------------------------------------------------------------------


def test_c3_detects_subprocess_text_without_encoding(tmp_path: Path) -> None:
    src = tmp_path / "sub.py"
    src.write_text(
        textwrap.dedent(
            """\
            import subprocess

            def a():
                subprocess.run(["ls"], text=True)  # text=True 缺 encoding

            def b():
                subprocess.Popen(["echo", "hi"], shell=True)  # shell=True

            def good():
                subprocess.run(["ls"], encoding="utf-8", text=True)

            def bin_ok():
                subprocess.run(["ls"])  # 二进制模式 OK
            """
        ),
        encoding="utf-8",
    )
    findings = scan_c3_subprocess([src])
    cats = [(f.line, f.message) for f in findings]
    # 至少 2 条：一条 text without encoding，一条 shell=True
    assert any("text=True 缺" in m or "缺 encoding" in m for _, m in cats)
    assert any("shell=True" in m for _, m in cats)


# ---------------------------------------------------------------------------
# C4: asyncio
# ---------------------------------------------------------------------------


def test_c4_detects_asyncio_without_proactor_policy(tmp_path: Path) -> None:
    bad = tmp_path / "async_bad.py"
    bad.write_text(
        textwrap.dedent(
            """\
            import asyncio

            async def main():
                pass

            asyncio.run(main())
            """
        ),
        encoding="utf-8",
    )
    good = tmp_path / "async_good.py"
    good.write_text(
        textwrap.dedent(
            """\
            import asyncio
            from runtime_compat import set_windows_proactor_policy

            async def main():
                pass

            set_windows_proactor_policy()
            asyncio.run(main())
            """
        ),
        encoding="utf-8",
    )
    findings = scan_c4_asyncio([bad, good])
    bad_findings = [f for f in findings if f.path == str(bad)]
    good_findings = [f for f in findings if f.path == str(good)]
    assert len(bad_findings) == 1
    assert good_findings == []


# ---------------------------------------------------------------------------
# C5: symlink
# ---------------------------------------------------------------------------


def test_c5_detects_raw_symlink(tmp_path: Path) -> None:
    src = tmp_path / "links.py"
    src.write_text(
        textwrap.dedent(
            """\
            import os
            from pathlib import Path

            def make():
                os.symlink("a", "b")  # 裸调用

            def make_path():
                Path("a").symlink_to("b")  # 裸调用

            def safe():
                from runtime_compat import safe_symlink
                safe_symlink("a", "b")  # 已包装
            """
        ),
        encoding="utf-8",
    )
    findings = scan_c5_symlink([src])
    assert len(findings) == 2
    assert all(f.category == "C5" for f in findings)


# ---------------------------------------------------------------------------
# C6: .sh / .ps1 / .cmd 对等
# ---------------------------------------------------------------------------


def test_c6_detects_missing_ps1_cmd(tmp_path: Path) -> None:
    (tmp_path / "alone.sh").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    (tmp_path / "paired.sh").write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    (tmp_path / "paired.ps1").write_text("Write-Host ok\n", encoding="utf-8")
    (tmp_path / "paired.cmd").write_text("@echo off\r\n", encoding="utf-8")
    findings = scan_c6_sh_ps1_cmd_parity(tmp_path)
    paths = [Path(f.path).name for f in findings]
    assert "alone.sh" in paths
    assert "paired.sh" not in paths


# ---------------------------------------------------------------------------
# C7: SKILL.md Windows sibling 块
# ---------------------------------------------------------------------------


def test_c7_detects_skill_md_missing_windows_block(tmp_path: Path) -> None:
    bad_dir = tmp_path / "bad-skill"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text(
        textwrap.dedent(
            """\
            ## Run

            ```bash
            bash scripts/foo.sh 5
            ```
            """
        ),
        encoding="utf-8",
    )
    good_dir = tmp_path / "good-skill"
    good_dir.mkdir()
    (good_dir / "SKILL.md").write_text(
        textwrap.dedent(
            """\
            ## Run

            ```bash
            bash scripts/foo.sh 5
            ```
            <!-- windows-ps1-sibling -->
            ```powershell
            & "$env:SCRIPTS_DIR/foo.ps1" 5
            ```
            """
        ),
        encoding="utf-8",
    )
    findings = scan_c7_skill_md_windows_block(tmp_path)
    bad_findings = [f for f in findings if str(bad_dir) in f.path]
    good_findings = [f for f in findings if str(good_dir) in f.path]
    assert len(bad_findings) == 1
    assert good_findings == []


# ---------------------------------------------------------------------------
# C8: 硬编码 python3
# ---------------------------------------------------------------------------


def test_c8_detects_hardcoded_python(tmp_path: Path) -> None:
    sh = tmp_path / "run.sh"
    sh.write_text(
        textwrap.dedent(
            """\
            #!/bin/bash
            # shebang 不算
            python3 -m foo
            py -3 -m bar
            """
        ),
        encoding="utf-8",
    )
    ps = tmp_path / "run.ps1"
    ps.write_text(
        textwrap.dedent(
            """\
            # comment py -3 (注释行不算)
            python3 -m foo
            $py = (find_python_launcher)
            & $py -m bar
            """
        ),
        encoding="utf-8",
    )
    findings = scan_c8_python_launcher(tmp_path)
    # 至少 3 处 (sh: 2 行, ps1: 1 行)
    assert len(findings) >= 3
    assert all(f.category == "C8" for f in findings)


# ---------------------------------------------------------------------------
# C9: CLI 入口缺 enable_windows_utf8_stdio
# ---------------------------------------------------------------------------


def test_c9_detects_cli_entry_missing_utf8_stdio(tmp_path: Path) -> None:
    bad = tmp_path / "cli_bad.py"
    bad.write_text(
        textwrap.dedent(
            '''\
            """A CLI."""
            def main():
                print("hi")

            if __name__ == "__main__":
                main()
            '''
        ),
        encoding="utf-8",
    )
    good = tmp_path / "cli_good.py"
    good.write_text(
        textwrap.dedent(
            '''\
            """A CLI."""
            from runtime_compat import enable_windows_utf8_stdio

            def main():
                enable_windows_utf8_stdio()
                print("hi")

            if __name__ == "__main__":
                main()
            '''
        ),
        encoding="utf-8",
    )
    not_main = tmp_path / "lib.py"
    not_main.write_text("def f():\n    return 1\n", encoding="utf-8")
    findings = scan_c9_cli_utf8_stdio([bad, good, not_main])
    bad_findings = [f for f in findings if f.path == str(bad)]
    good_findings = [f for f in findings if f.path == str(good)]
    lib_findings = [f for f in findings if f.path == str(not_main)]
    assert len(bad_findings) == 1
    assert good_findings == []
    assert lib_findings == []


# ---------------------------------------------------------------------------
# 顶层 run_audit + 95% 覆盖率断言
# ---------------------------------------------------------------------------


@pytest.fixture()
def synthetic_project(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    """构造一个带每类 C1~C9 至少 1 处已知风险的微型项目。"""
    proj = tmp_path / "proj"
    proj.mkdir()

    # C1
    c1 = proj / "c1_open.py"
    c1.write_text(
        'with open("x.txt") as f: pass\n',
        encoding="utf-8",
    )

    # C2
    c2 = proj / "c2_path.py"
    c2.write_text('P = "ink-writer/scripts/runtime_compat.py"\n', encoding="utf-8")

    # C3
    c3 = proj / "c3_sub.py"
    c3.write_text(
        textwrap.dedent(
            """\
            import subprocess
            subprocess.run(["ls"], text=True)
            """
        ),
        encoding="utf-8",
    )

    # C4
    c4 = proj / "c4_async.py"
    c4.write_text(
        textwrap.dedent(
            """\
            import asyncio
            async def m(): pass
            asyncio.run(m())
            """
        ),
        encoding="utf-8",
    )

    # C5
    c5 = proj / "c5_link.py"
    c5.write_text("import os\nos.symlink('a', 'b')\n", encoding="utf-8")

    # C6
    c6 = proj / "c6_alone.sh"
    c6.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")

    # C7
    skill_dir = proj / "skill-x"
    skill_dir.mkdir()
    c7 = skill_dir / "SKILL.md"
    c7.write_text("```bash\nbash run.sh 1\n```\n", encoding="utf-8")

    # C8
    c8 = proj / "c8_run.sh"
    c8.write_text("#!/bin/bash\npython3 -m mod\n", encoding="utf-8")

    # C9
    c9 = proj / "c9_cli.py"
    c9.write_text(
        textwrap.dedent(
            '''\
            def main(): pass
            if __name__ == "__main__":
                main()
            '''
        ),
        encoding="utf-8",
    )

    expected = {
        "C1": c1,
        "C2": c2,
        "C3": c3,
        "C4": c4,
        "C5": c5,
        "C6": c6,
        "C7": c7,
        "C8": c8,
        "C9": c9,
    }
    return proj, expected


def test_run_audit_covers_all_9_categories(
    synthetic_project: tuple[Path, dict[str, Path]],
) -> None:
    proj, expected = synthetic_project
    report = run_audit(proj)

    by_cat = report.by_category()
    missing = [cat for cat in expected if not by_cat.get(cat)]
    coverage = (len(expected) - len(missing)) / len(expected)
    assert coverage >= 0.95, (
        f"9 类风险检测覆盖率 {coverage:.0%} < 95%; 漏检: {missing}"
    )
    # 每类期望文件至少有一条 finding
    for cat, expected_path in expected.items():
        cat_findings = by_cat[cat]
        detected_paths = {Path(f.path).resolve() for f in cat_findings}
        assert expected_path.resolve() in detected_paths, (
            f"{cat} 漏检 {expected_path}; findings={cat_findings}"
        )


def test_render_markdown_contains_all_sections(
    synthetic_project: tuple[Path, dict[str, Path]],
) -> None:
    proj, _ = synthetic_project
    report = run_audit(proj)
    md = render_markdown(report, proj)
    assert "# 跨平台兼容性审计 Findings 报告" in md
    assert "## 按类别汇总" in md
    assert "## Seed US List" in md
    # 至少出现 1 个具体 US 引用
    assert "US-002" in md
    assert "US-010" in md


def test_severity_order_complete() -> None:
    """SEVERITY_ORDER 必须包含所有四级。"""
    assert set(SEVERITY_ORDER.keys()) == {"Blocker", "High", "Medium", "Low"}


def test_audit_report_severity_counts_empty() -> None:
    """空报告四级计数都是 0。"""
    rep = AuditReport()
    counts = rep.severity_counts()
    assert counts == {"Blocker": 0, "High": 0, "Medium": 0, "Low": 0}


def test_finding_as_md_row_relative_path(tmp_path: Path) -> None:
    """Finding.as_md_row 在 root 下的文件应用相对路径。"""
    f = Finding(
        category="C1",
        severity="High",
        path=str(tmp_path / "a" / "b.py"),
        line=42,
        message="msg",
        suggestion="sug",
    )
    row = f.as_md_row(root=tmp_path)
    assert "a/b.py:42" in row or "a\\b.py:42" in row
    assert "High" in row


def test_main_writes_report(tmp_path: Path) -> None:
    """main() CLI 应能写出报告并 exit 0（fail-on=never）。"""
    from audit_cross_platform import main

    out = tmp_path / "report.md"
    rc = main(["--root", str(tmp_path), "--output", str(out), "--fail-on", "never"])
    assert rc == 0
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert "Findings 报告" in body
