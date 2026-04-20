"""Tests for scripts/fix_utf8_encoding.py (US-002).

覆盖：正常修复 / 二进制模式跳过 / webbrowser.open 跳过 / 已有 encoding 跳过 /
幂等性 / 多行调用保守跳过 / dry-run 不写回。
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fix_utf8_encoding import fix_file, main  # noqa: E402


def test_fix_file_adds_encoding_to_open(tmp_path: Path) -> None:
    src = tmp_path / "sample.py"
    src.write_text(
        textwrap.dedent(
            """\
            def load():
                with open("x.txt") as f:
                    return f.read()
            """
        ),
        encoding="utf-8",
    )
    edits = fix_file(src)
    assert edits == [2]
    after = src.read_text(encoding="utf-8")
    assert 'open("x.txt", encoding="utf-8")' in after


def test_fix_file_adds_encoding_to_write_and_read_text(tmp_path: Path) -> None:
    src = tmp_path / "paths.py"
    src.write_text(
        textwrap.dedent(
            """\
            from pathlib import Path

            def save(data):
                Path("out.txt").write_text(data)

            def load():
                return Path("in.txt").read_text()
            """
        ),
        encoding="utf-8",
    )
    edits = fix_file(src)
    assert edits == [4, 7]
    after = src.read_text(encoding="utf-8")
    assert 'write_text(data, encoding="utf-8")' in after
    assert 'read_text(encoding="utf-8")' in after


def test_fix_file_skips_binary_open(tmp_path: Path) -> None:
    src = tmp_path / "bin.py"
    original = textwrap.dedent(
        """\
        def read_bin():
            with open("x.dat", "rb") as f:
                return f.read()

        def read_bin_kw():
            return open("y.dat", mode="rb")
        """
    )
    src.write_text(original, encoding="utf-8")
    edits = fix_file(src)
    assert edits == []
    assert src.read_text(encoding="utf-8") == original


def test_fix_file_skips_path_open_binary_mode(tmp_path: Path) -> None:
    """Path.open("rb") 首位即 mode，不得误改。"""
    src = tmp_path / "path_bin.py"
    original = textwrap.dedent(
        """\
        from pathlib import Path

        def f():
            with Path("x.bin").open("rb") as fh:
                return fh.read()
        """
    )
    src.write_text(original, encoding="utf-8")
    edits = fix_file(src)
    assert edits == []
    assert src.read_text(encoding="utf-8") == original


def test_fix_file_skips_webbrowser_and_similar(tmp_path: Path) -> None:
    src = tmp_path / "non_file.py"
    original = textwrap.dedent(
        """\
        import webbrowser
        import os

        def nav():
            webbrowser.open("https://example.com")

        def fd():
            return os.open("/tmp/x", os.O_RDONLY)
        """
    )
    src.write_text(original, encoding="utf-8")
    edits = fix_file(src)
    assert edits == []
    assert src.read_text(encoding="utf-8") == original


def test_fix_file_skips_existing_encoding(tmp_path: Path) -> None:
    src = tmp_path / "good.py"
    original = textwrap.dedent(
        """\
        from pathlib import Path

        def f():
            with open("x.txt", encoding="utf-8") as fh:
                return fh.read()
            Path("y.txt").write_text("hi", encoding="utf-8")
        """
    )
    src.write_text(original, encoding="utf-8")
    edits = fix_file(src)
    assert edits == []
    assert src.read_text(encoding="utf-8") == original


def test_fix_file_idempotent(tmp_path: Path) -> None:
    src = tmp_path / "idem.py"
    src.write_text(
        textwrap.dedent(
            """\
            def f():
                open("a")
                open("b")
            """
        ),
        encoding="utf-8",
    )
    first = fix_file(src)
    assert first == [2, 3]
    second = fix_file(src)
    assert second == []
    after = src.read_text(encoding="utf-8")
    # 每个 open 都有且仅有一次 encoding="utf-8"
    assert after.count('encoding="utf-8"') == 2


def test_fix_file_skips_multiline_calls(tmp_path: Path) -> None:
    """多行 open(...) 保守跳过，避免破坏格式。"""
    src = tmp_path / "multiline.py"
    original = textwrap.dedent(
        '''\
        def f():
            with open(
                "x.txt",
            ) as fh:
                return fh.read()
        '''
    )
    src.write_text(original, encoding="utf-8")
    edits = fix_file(src)
    assert edits == []
    assert src.read_text(encoding="utf-8") == original


def test_fix_file_dry_run_does_not_write(tmp_path: Path) -> None:
    src = tmp_path / "dry.py"
    original = 'open("x.txt")\n'
    src.write_text(original, encoding="utf-8")
    edits = fix_file(src, dry_run=True)
    assert edits == [1]
    # 源文件未被修改
    assert src.read_text(encoding="utf-8") == original


def test_fix_file_handles_no_args_open(tmp_path: Path) -> None:
    """open() 无参（极少见，但语法上合法）—— 也不插入逗号。"""
    src = tmp_path / "noargs.py"
    src.write_text(
        textwrap.dedent(
            """\
            def f(opener):
                return opener()
            """
        ),
        encoding="utf-8",
    )
    edits = fix_file(src)
    assert edits == []


def test_fix_file_handles_syntax_error(tmp_path: Path) -> None:
    src = tmp_path / "bad_syntax.py"
    src.write_text("def (", encoding="utf-8")
    # 不应抛异常
    assert fix_file(src) == []


def test_main_cli_default_root(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    sample = tmp_path / "m.py"
    sample.write_text('open("x")\n', encoding="utf-8")
    rc = main(["--root", str(tmp_path)])
    assert rc == 0
    assert 'encoding="utf-8"' in sample.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    assert "fixed 1 call(s)" in captured.out


def test_main_cli_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    sample = tmp_path / "m.py"
    original = 'open("x")\n'
    sample.write_text(original, encoding="utf-8")
    rc = main(["--root", str(tmp_path), "--dry-run"])
    assert rc == 0
    assert sample.read_text(encoding="utf-8") == original
    captured = capsys.readouterr()
    assert "would fix 1 call(s)" in captured.out


def test_main_cli_invalid_root(tmp_path: Path) -> None:
    bogus = tmp_path / "does_not_exist"
    rc = main(["--root", str(bogus)])
    assert rc == 2
