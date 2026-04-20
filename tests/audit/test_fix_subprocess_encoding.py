"""Tests for scripts/fix_subprocess_encoding.py (US-004).

覆盖：单行/多行 subprocess.run 文本模式补 encoding / 二进制模式跳过 /
universal_newlines 文本模式 / 已有 encoding 跳过 / 幂等性 / shell=True 不动 /
非 subprocess 同名调用不误命中 / dry-run 不写回 / main CLI 入口。
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fix_subprocess_encoding import fix_file, main  # noqa: E402


def _write(path: Path, body: str) -> None:
    path.write_text(textwrap.dedent(body), encoding="utf-8")


# ---------------------------------------------------------------------------
# 单行调用
# ---------------------------------------------------------------------------


def test_single_line_run_with_text_kw(tmp_path: Path) -> None:
    src = tmp_path / "a.py"
    _write(
        src,
        """\
        import subprocess
        def go():
            return subprocess.run(["git", "init"], check=True, text=True)
        """,
    )
    fixed = fix_file(src)
    assert fixed == [3]
    after = src.read_text(encoding="utf-8")
    assert (
        'subprocess.run(["git", "init"], check=True, text=True, encoding="utf-8")'
        in after
    )


def test_single_line_check_output_with_universal_newlines(tmp_path: Path) -> None:
    src = tmp_path / "b.py"
    _write(
        src,
        """\
        import subprocess
        def ver():
            return subprocess.check_output(["git", "--version"], universal_newlines=True)
        """,
    )
    fixed = fix_file(src)
    assert fixed == [3]
    after = src.read_text(encoding="utf-8")
    assert 'universal_newlines=True, encoding="utf-8"' in after


# ---------------------------------------------------------------------------
# 多行调用 — 必须能修
# ---------------------------------------------------------------------------


def test_multiline_run_with_trailing_comma(tmp_path: Path) -> None:
    src = tmp_path / "c.py"
    _write(
        src,
        """\
        import subprocess
        def go():
            return subprocess.run(
                ["git", "log"],
                capture_output=True,
                text=True,
                timeout=120,
            )
        """,
    )
    fixed = fix_file(src)
    assert fixed == [3]
    after = src.read_text(encoding="utf-8")
    # 期望插入在最后一个 keyword (timeout=120) 之后；不破坏 trailing comma
    assert 'timeout=120, encoding="utf-8",' in after
    # 仍然 valid Python：能 ast.parse
    import ast as _ast
    _ast.parse(after)


def test_multiline_run_no_trailing_comma(tmp_path: Path) -> None:
    src = tmp_path / "d.py"
    _write(
        src,
        """\
        import subprocess
        def go():
            return subprocess.run(
                ["echo", "hi"],
                capture_output=True,
                text=True
            )
        """,
    )
    fixed = fix_file(src)
    assert fixed == [3]
    after = src.read_text(encoding="utf-8")
    assert 'text=True, encoding="utf-8"' in after
    import ast as _ast
    _ast.parse(after)


# ---------------------------------------------------------------------------
# 跳过场景
# ---------------------------------------------------------------------------


def test_binary_mode_skipped(tmp_path: Path) -> None:
    """无 text/universal_newlines/encoding 关键字 → 视为二进制模式，不动。"""
    src = tmp_path / "e.py"
    _write(
        src,
        """\
        import subprocess
        def go():
            return subprocess.run(["echo", "hi"], capture_output=True)
        """,
    )
    before = src.read_text(encoding="utf-8")
    fix_file(src)
    after = src.read_text(encoding="utf-8")
    assert before == after


def test_existing_encoding_skipped(tmp_path: Path) -> None:
    src = tmp_path / "f.py"
    body = """\
        import subprocess
        def go():
            return subprocess.run(["echo"], text=True, encoding="utf-8")
        """
    _write(src, body)
    before = src.read_text(encoding="utf-8")
    fix_file(src)
    after = src.read_text(encoding="utf-8")
    assert before == after


def test_text_false_skipped(tmp_path: Path) -> None:
    """text=False（显式）当二进制看待，不动。"""
    src = tmp_path / "g.py"
    _write(
        src,
        """\
        import subprocess
        def go():
            return subprocess.run(["echo"], text=False)
        """,
    )
    before = src.read_text(encoding="utf-8")
    fix_file(src)
    after = src.read_text(encoding="utf-8")
    assert before == after


def test_non_subprocess_same_name_skipped(tmp_path: Path) -> None:
    """名为 .run / .Popen 但非 subprocess 模块的调用不动。"""
    src = tmp_path / "h.py"
    _write(
        src,
        """\
        class Worker:
            def run(self, *a, **kw):
                pass

        w = Worker()
        w.run("cmd", text=True)
        """,
    )
    before = src.read_text(encoding="utf-8")
    fix_file(src)
    after = src.read_text(encoding="utf-8")
    assert before == after


def test_shell_true_left_alone(tmp_path: Path) -> None:
    """shell=True 不在 fixer 范围内（需要人工拆 args）；只要不带 text 就不动。"""
    src = tmp_path / "i.py"
    _write(
        src,
        """\
        import subprocess
        def go():
            return subprocess.run("echo hi", shell=True)
        """,
    )
    before = src.read_text(encoding="utf-8")
    fix_file(src)
    after = src.read_text(encoding="utf-8")
    assert before == after


# ---------------------------------------------------------------------------
# 幂等性
# ---------------------------------------------------------------------------


def test_idempotent(tmp_path: Path) -> None:
    src = tmp_path / "j.py"
    _write(
        src,
        """\
        import subprocess
        def go():
            return subprocess.run(["echo"], text=True)
        """,
    )
    first = fix_file(src)
    after_first = src.read_text(encoding="utf-8")
    second = fix_file(src)
    after_second = src.read_text(encoding="utf-8")
    assert first == [3]
    assert second == []
    assert after_first == after_second


# ---------------------------------------------------------------------------
# dry-run
# ---------------------------------------------------------------------------


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    src = tmp_path / "k.py"
    _write(
        src,
        """\
        import subprocess
        def go():
            return subprocess.run(["echo"], text=True)
        """,
    )
    before = src.read_text(encoding="utf-8")
    reported = fix_file(src, dry_run=True)
    after = src.read_text(encoding="utf-8")
    assert reported == [3]
    assert before == after


# ---------------------------------------------------------------------------
# 多个 call 同文件
# ---------------------------------------------------------------------------


def test_multiple_calls_in_one_file(tmp_path: Path) -> None:
    src = tmp_path / "l.py"
    _write(
        src,
        """\
        import subprocess
        def a():
            return subprocess.run(["x"], text=True)
        def b():
            return subprocess.check_output(["y"], universal_newlines=True)
        def c():
            return subprocess.Popen(["z"], text=True, encoding="utf-8")  # 已有
        """,
    )
    fixed = fix_file(src)
    assert fixed == [3, 5]  # c() 跳过
    after = src.read_text(encoding="utf-8")
    assert after.count('encoding="utf-8"') == 3  # 2 新 + 1 原


# ---------------------------------------------------------------------------
# main CLI
# ---------------------------------------------------------------------------


def test_main_dry_run_returns_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "m.py"
    _write(
        src,
        """\
        import subprocess
        def go():
            return subprocess.run(["echo"], text=True)
        """,
    )
    rc = main(["--root", str(tmp_path), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "would fix 1 call(s) in 1 file(s)" in out
    assert "m.py:3" in out
    # dry-run: 文件不应被改
    assert "encoding=" not in src.read_text(encoding="utf-8")


def test_main_root_invalid_returns_two(tmp_path: Path) -> None:
    rc = main(["--root", str(tmp_path / "missing")])
    assert rc == 2


def test_main_writes_when_not_dry_run(tmp_path: Path) -> None:
    src = tmp_path / "n.py"
    _write(
        src,
        """\
        import subprocess
        def go():
            return subprocess.run(["echo"], text=True)
        """,
    )
    rc = main(["--root", str(tmp_path)])
    assert rc == 0
    assert 'encoding="utf-8"' in src.read_text(encoding="utf-8")
