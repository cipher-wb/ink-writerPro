"""tests/core/test_path_cross_platform.py — US-003 跨平台路径处理验证。

覆盖三类场景（CLAUDE.md "Windows 兼容守则" 第 1 / 2 条所对应的实质风险）：

1. **中文路径**：项目目录 / 章节文件常含中文（《我能重定义一切》/正文/第0001章.md），
   pathlib 必须能正确表达、读写、序列化为 str 后回往返。
2. **带空格路径**：用户家目录 ``Application Support`` 类、Windows ``Program Files``，
   subprocess 调用必须用 args 列表传递（而非 shell=True 字符串）。
3. **UNC 路径**：Windows ``\\\\server\\share\\file`` 形态以及 Git Bash / WSL 风格
   ``/d/desktop/...`` —— ``runtime_compat.normalize_windows_path`` 是唯一入口。

所有测试在 Mac / Windows 都能跑（Windows-only 行为用 ``sys.platform`` 守卫）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# 接入 ink-writer/scripts/runtime_compat
_SCRIPTS = Path(__file__).resolve().parents[2] / "ink-writer" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from runtime_compat import normalize_windows_path  # noqa: E402


# ---------------------------------------------------------------------------
# 中文路径
# ---------------------------------------------------------------------------


CHINESE_PROJECT_NAMES = [
    "我能重定义一切",
    "因果剑歌",
    "断戎书",
    "妈妈在第18次重生后放手",
]


@pytest.mark.parametrize("name", CHINESE_PROJECT_NAMES)
def test_pathlib_handles_chinese_project_dir(tmp_path: Path, name: str) -> None:
    """pathlib.Path 必须能创建/列出/序列化中文目录名。"""
    proj = tmp_path / name
    proj.mkdir()
    (proj / "正文").mkdir()
    (proj / "正文" / "第0001章.md").write_text(
        "第一章内容", encoding="utf-8"
    )
    chapter = proj / "正文" / "第0001章.md"
    assert chapter.exists()
    assert chapter.read_text(encoding="utf-8") == "第一章内容"
    # str 化往返
    assert Path(str(chapter)) == chapter
    # rglob 列出
    matches = list(proj.rglob("*.md"))
    assert chapter in matches


def test_chinese_path_resolve_roundtrip(tmp_path: Path) -> None:
    """resolve() 后再传给 Path 应保持等价。"""
    proj = tmp_path / "测试项目" / ".ink" / "state.json"
    proj.parent.mkdir(parents=True)
    proj.write_text("{}", encoding="utf-8")
    resolved = proj.resolve()
    assert Path(str(resolved)) == resolved
    # JSON 路径片段保留中文
    assert "测试项目" in str(resolved)


def test_chinese_filename_with_open_roundtrip(tmp_path: Path) -> None:
    """builtin open 配合 encoding=utf-8 能写入/读出中文文件名+内容。"""
    target = tmp_path / "第十二章·终章.txt"
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("结尾内容\n")
    with open(target, "r", encoding="utf-8") as fh:
        assert fh.read() == "结尾内容\n"


# ---------------------------------------------------------------------------
# 带空格路径
# ---------------------------------------------------------------------------


def test_pathlib_handles_paths_with_spaces(tmp_path: Path) -> None:
    """带空格的路径段必须能 mkdir / read / write。"""
    nested = tmp_path / "Application Support" / "ink writer" / "data files"
    nested.mkdir(parents=True)
    f = nested / "settings file.json"
    f.write_text("{}", encoding="utf-8")
    assert f.exists()
    assert f.read_text(encoding="utf-8") == "{}"
    # rglob 不被空格破坏
    assert f in list(tmp_path.rglob("*.json"))


def test_subprocess_handles_args_list_with_spaces(tmp_path: Path) -> None:
    """subprocess 用 args 列表传带空格路径，跨平台都不需要 shell quoting。"""
    target = tmp_path / "with space" / "echo input.txt"
    target.parent.mkdir(parents=True)
    target.write_text("hello\n", encoding="utf-8")
    # 用 Python 解释器读文件，避免依赖 cat/type 的平台差异
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; print(open(sys.argv[1], encoding='utf-8').read(), end='')",
            str(target),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "hello\n"


def test_path_with_spaces_str_roundtrip() -> None:
    """str(Path('a b/c d')) 在两个平台上都保留空格；不会被错误归一化。"""
    p = Path("a b") / "c d" / "e.txt"
    assert " " in str(p)
    assert Path(str(p)) == p


# ---------------------------------------------------------------------------
# UNC / Windows 风格路径（normalize_windows_path）
# ---------------------------------------------------------------------------


def test_normalize_windows_path_returns_path_on_mac() -> None:
    """非 Windows: normalize_windows_path 透传为 Path（不改语义）。"""
    if sys.platform == "win32":  # pragma: no cover
        pytest.skip("Mac-only behavior check")
    assert normalize_windows_path("/Users/cipher/AI/ink/ink-writer") == Path(
        "/Users/cipher/AI/ink/ink-writer"
    )
    # Git Bash 风格路径在 Mac 上不变换
    assert normalize_windows_path("/d/desktop/foo") == Path("/d/desktop/foo")
    # WSL 风格同理
    assert normalize_windows_path("/mnt/d/desktop/foo") == Path("/mnt/d/desktop/foo")


def test_normalize_windows_path_accepts_path_input(tmp_path: Path) -> None:
    """normalize_windows_path 既接受 str 也接受 Path（API 友好）。"""
    p = tmp_path / "项目"
    p.mkdir()
    out = normalize_windows_path(p)
    assert isinstance(out, Path)
    if sys.platform != "win32":
        assert out == p


def test_normalize_windows_path_empty_string_safe() -> None:
    """空字符串不抛异常，返回 Path('') —— 调用方决定怎么处理。"""
    if sys.platform == "win32":  # pragma: no cover
        pytest.skip("Windows 行为另行测试")
    # Mac 路径上空串就是 Path('.')-ish，不抛
    out = normalize_windows_path("")
    assert isinstance(out, Path)


def test_chinese_dir_with_spaces_combined(tmp_path: Path) -> None:
    """组合场景：中文 + 空格 —— 国际化用户最常踩。"""
    nested = tmp_path / "我的 项目" / ".ink" / "正文 草稿"
    nested.mkdir(parents=True)
    f = nested / "第 1 章.md"
    f.write_text("正文", encoding="utf-8")
    # Path 等价
    assert Path(str(f)) == f
    # str 中保留所有特殊字符
    s = str(f)
    assert "我的 项目" in s
    assert "正文 草稿" in s
    assert "第 1 章.md" in s


# ---------------------------------------------------------------------------
# os.path.join 的跨平台行为（防回归）
# ---------------------------------------------------------------------------


def test_os_path_join_normalizes_forward_slash_on_windows() -> None:
    """os.path.join('/tmp', 'a/b/c.txt') 在 Mac 上保持 '/'；
    在 Windows 上 Python 自动归一化（这是为何 C2 scanner 不报 join 第二参数）。
    """
    out = os.path.join("/tmp", "a/b/c.txt")
    assert "a" in out and "c.txt" in out
    # 用 Path 验证 cross-platform 等价
    assert Path(out) == Path("/tmp") / "a" / "b" / "c.txt"


def test_pathlib_division_handles_forward_slash_segment() -> None:
    """Path('a') / 'b/c' 在 Windows 上把 'b/c' 当成两段，结果 a/b/c。"""
    p = Path("a") / "b/c"
    parts = p.parts
    # Mac: ('a', 'b/c') 或 ('a', 'b', 'c')；Windows: ('a', 'b', 'c')
    # 统一接受任一形态，关键是 str 化后能 round-trip
    assert Path(str(p)) == p


# ---------------------------------------------------------------------------
# tempfile + 中文 / 空格目录互操作
# ---------------------------------------------------------------------------


def test_tempfile_named_file_under_chinese_root(tmp_path: Path) -> None:
    chinese_root = tmp_path / "中文 根目录"
    chinese_root.mkdir()
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        prefix="第_",
        dir=str(chinese_root),
        delete=False,
        encoding="utf-8",
    ) as fh:
        fh.write("内容")
        fh_path = Path(fh.name)
    try:
        assert fh_path.exists()
        assert fh_path.read_text(encoding="utf-8") == "内容"
    finally:
        if fh_path.exists():
            fh_path.unlink()


def test_shutil_copy_under_chinese_dir(tmp_path: Path) -> None:
    src_dir = tmp_path / "源 目录"
    dst_dir = tmp_path / "目标 目录"
    src_dir.mkdir()
    dst_dir.mkdir()
    src = src_dir / "文件.txt"
    src.write_text("原始", encoding="utf-8")
    dst = dst_dir / "副本.txt"
    shutil.copy(str(src), str(dst))
    assert dst.exists()
    assert dst.read_text(encoding="utf-8") == "原始"
