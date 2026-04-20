#!/usr/bin/env python3
"""audit_cross_platform.py — 跨平台兼容性全盘静态扫描（US-001）

扫描 9 类风险点，输出 Markdown findings 报告 + 种子 US 清单：

    C1  open()/read_text()/write_text() 文本模式缺 encoding="utf-8"
    C2  硬编码路径分隔符（Python 字符串字面量内的 "a/b/c" 等）
    C3  subprocess.run/Popen 文本模式缺 encoding 或显式 shell=True
    C4  asyncio.run / asyncio.new_event_loop 入口未调 set_windows_proactor_policy
    C5  Path.symlink_to / os.symlink 未走 runtime_compat.safe_symlink
    C6  *.sh 缺同目录同名 .ps1 / .cmd 对等
    C7  SKILL.md 引用 .sh 但缺 Windows PowerShell sibling 块
    C8  脚本 / .ps1 / .cmd / .sh / SKILL.md 中硬编码 python3 / python（未走 find_python_launcher）
    C9  Python CLI 入口（含 if __name__ == "__main__"）未调 enable_windows_utf8_stdio

每条 finding 含: 文件、行号、严重级别（Blocker/High/Medium/Low）、修复建议。
末尾生成 seed_us_list（按严重级别排序，便于下一轮 PRD 迭代）。

只用 stdlib（ast + re + pathlib），不依赖第三方库。
"""

from __future__ import annotations

# Windows UTF-8 stdio：Mac no-op
import os as _os_win_stdio
import sys as _sys_win_stdio

_INK_SCRIPTS = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    "..",
    "ink-writer",
    "scripts",
)
if _os_win_stdio.path.isdir(_INK_SCRIPTS) and _INK_SCRIPTS not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _INK_SCRIPTS)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass

import argparse
import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# 这些目录跳过（生成产物 / 第三方 / 临时归档）
EXCLUDE_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".ink",
    "archive",  # 历史归档，不影响当前发版
    ".coverage",
    "htmlcov",
}

# 严重级别（用于排序）
SEVERITY_ORDER = {"Blocker": 0, "High": 1, "Medium": 2, "Low": 3}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """单条审计发现。"""

    category: str  # C1~C9
    severity: str  # Blocker / High / Medium / Low
    path: str
    line: int
    message: str
    suggestion: str

    def as_md_row(self, root: Optional[Path] = None) -> str:
        rel = self.path
        if root is not None:
            try:
                rel = str(Path(self.path).resolve().relative_to(root.resolve()))
            except ValueError:
                rel = self.path
        return f"| `{rel}:{self.line}` | {self.severity} | {self.message} | {self.suggestion} |"


@dataclass
class AuditReport:
    """所有 finding 的容器。"""

    findings: list[Finding] = field(default_factory=list)

    def by_category(self) -> dict[str, list[Finding]]:
        out: dict[str, list[Finding]] = {f"C{i}": [] for i in range(1, 10)}
        for f in self.findings:
            out.setdefault(f.category, []).append(f)
        return out

    def severity_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {k: 0 for k in SEVERITY_ORDER}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def iter_files(root: Path, suffixes: tuple[str, ...]) -> Iterable[Path]:
    """递归遍历 root，跳过 EXCLUDE_DIR_NAMES。"""
    if not root.exists():
        return
    for entry in sorted(root.rglob("*")):
        if not entry.is_file():
            continue
        # 跳过位于排除目录下的文件
        if any(part in EXCLUDE_DIR_NAMES for part in entry.parts):
            continue
        if entry.suffix.lower() in suffixes:
            yield entry


def safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""


# ---------------------------------------------------------------------------
# C1: open() / read_text() / write_text() 文本模式缺 encoding="utf-8"
# ---------------------------------------------------------------------------


_TEXT_BINARY_FLAGS = re.compile(r"['\"][^'\"]*b[^'\"]*['\"]")


def _is_binary_mode(call: ast.Call) -> bool:
    """判断 open() 调用是否在二进制模式（mode 参数包含 'b'）。

    区分两种形态：
    - 内建 ``open(file, mode, ...)`` —— ``ast.Name('open')``，mode 在 args[1]
    - 方法调用 ``path.open(mode, ...)`` —— ``ast.Attribute(attr='open')``，mode 在 args[0]
    """
    is_method_call = isinstance(call.func, ast.Attribute)
    mode_idx = 0 if is_method_call else 1
    mode_node: Optional[ast.expr] = None
    if len(call.args) > mode_idx:
        mode_node = call.args[mode_idx]
    for kw in call.keywords:
        if kw.arg == "mode":
            mode_node = kw.value
    if mode_node is None:
        return False
    if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
        return "b" in mode_node.value
    return False


# 已知非文件 I/O 的 ``.open()`` 接收者（模块名 / 对象名）——全部跳过。
# 这些调用语义与编码无关，不应触发 C1。
_NON_FILE_OPEN_RECEIVERS = {
    "webbrowser",
    "os",  # os.open 是低级 fd，无 encoding 参数
    "socket",
    "urllib",
    "connection",
    "conn",
    "db",
    "cursor",
    "engine",
    "driver",
    "browser",
    "page",
    "tab",
    "dialog",
    "window",
}


def _is_non_file_open_call(call: ast.Call) -> bool:
    """识别 webbrowser.open / os.open / socket.open 等非文件 I/O 的 ``.open()`` 调用。"""
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != "open":
        return False
    receiver = func.value
    # 直接的 Name：webbrowser.open / os.open / driver.open
    if isinstance(receiver, ast.Name) and receiver.id in _NON_FILE_OPEN_RECEIVERS:
        return True
    # 链式属性：x.webbrowser.open / self.driver.open —— 看最后一段
    if isinstance(receiver, ast.Attribute) and receiver.attr in _NON_FILE_OPEN_RECEIVERS:
        return True
    return False


def _has_encoding_kw(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "encoding":
            return True
    return False


def _call_func_name(call: ast.Call) -> Optional[str]:
    """提取调用的函数名（最后一段）。"""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def scan_c1_open_encoding(py_files: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    targets = {"open", "read_text", "write_text"}
    for path in py_files:
        src = safe_read_text(path)
        if not src:
            continue
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_func_name(node)
            if name not in targets:
                continue
            # open() 二进制模式跳过（区分 builtin open 与 path.open 的 mode 位置）
            if name == "open" and _is_binary_mode(node):
                continue
            # 非文件 I/O 的 .open() 跳过（webbrowser.open / os.open / socket.open 等）
            if name == "open" and _is_non_file_open_call(node):
                continue
            if _has_encoding_kw(node):
                continue
            # write_text/read_text 在 Path 对象上调用：skip if 显式给了 encoding
            severity = "High" if name == "open" else "Medium"
            findings.append(
                Finding(
                    category="C1",
                    severity=severity,
                    path=str(path),
                    line=node.lineno,
                    message=f"`{name}()` 文本模式缺 encoding=utf-8",
                    suggestion='补 encoding="utf-8"（二进制模式 "b" 保持不变）',
                )
            )
    return findings


# ---------------------------------------------------------------------------
# C2: 硬编码路径分隔符（仅 filesystem 上下文 + 看起来像路径）
# ---------------------------------------------------------------------------


# 启发式：字符串含至少 2 段 "/" 分隔的非空小段，且不是 URL / 正则锚点 / glob 通配
_PATH_LIKE_RE = re.compile(
    r"^(?!https?://|//|file://|s3://)"
    r"(?P<core>(?:\.{0,2}/?)?[\w\-.]+(?:/[\w\-.]+){2,})/?$"
)

# CJK 范围：用于排除"中文显示标签"假阳（如 '设定集/角色库/主要角色'）
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
# 段必须看起来像 ASCII 路径分量（字母/数字/._-）
_ASCII_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._\-]+$")
# HTTP route 形态：以 / 开头，全是 ASCII 字母数字 - _ . :{} 的段
_HTTP_ROUTE_RE = re.compile(r"^/(?:[A-Za-z0-9._\-:{}]+)(?:/[A-Za-z0-9._\-:{}]*)*$")


def _looks_like_hardcoded_path(value: str) -> bool:
    """启发式：字符串看起来像 filesystem 路径（不是 URL/route/中文显示标签）。"""
    if not value or len(value) > 200:
        return False
    if "\n" in value or " " in value:
        return False
    if value.startswith(("http://", "https://", "//", "ws://", "wss://", "git@", "s3://", "file://")):
        return False
    if value.endswith((".com", ".org", ".net", ".io", ".cn")):
        return False
    if "/" not in value:
        return False
    parts = [p for p in value.split("/") if p]
    if len(parts) < 2:
        return False
    # 任一段含 CJK：判定为显示标签（如 '设定集/角色库/主要角色'）
    for p in parts:
        if _CJK_CHAR_RE.search(p):
            return False
    # 至少一段必须是 ASCII 路径分量（排除 '../../etc/hosts' 这种 traversal 测试 fixture
    # 仍允许通过：前两段是 '..'，第三段是 'etc'，是合法 ASCII 段）
    if not any(_ASCII_PATH_SEGMENT_RE.match(p) for p in parts):
        return False
    return bool(_PATH_LIKE_RE.match(value))


# 已知"消费 filesystem 路径"的调用目标（按调用名末段或限定名匹配）
_FS_CONSUMING_NAMES = {
    "Path",
    "PurePath",
    "PosixPath",
    "WindowsPath",
    "PurePosixPath",
    "PureWindowsPath",
    # 不含 "open" —— 由 C1 负责且会触发误报
}

_FS_CONSUMING_QUALIFIED = {
    # os.path
    "os.path.join",
    "os.path.exists",
    "os.path.isfile",
    "os.path.isdir",
    "os.path.dirname",
    "os.path.abspath",
    "os.path.realpath",
    "os.path.basename",
    "os.path.split",
    "os.path.splitext",
    "os.path.expanduser",
    "os.path.expandvars",
    "os.path.normpath",
    "os.path.relpath",
    # os
    "os.remove",
    "os.rename",
    "os.unlink",
    "os.makedirs",
    "os.mkdir",
    "os.listdir",
    "os.stat",
    "os.access",
    "os.rmdir",
    "os.chdir",
    "os.scandir",
    # shutil
    "shutil.copy",
    "shutil.copyfile",
    "shutil.move",
    "shutil.rmtree",
    "shutil.copytree",
    "shutil.copy2",
    "shutil.make_archive",
    # pathlib (qualified)
    "pathlib.Path",
    "pathlib.PurePath",
}

# os.path.join 的二三参数本就允许 "/"（Python 在 Windows 上会归一化），不报告
_FS_JOIN_TARGETS = {"os.path.join", "join"}

# 路径变量名启发式：以 _PATH / _DIR / _FILE / _ROOT 结尾，或 PATH_*/DIR_*/...
_PATH_VAR_NAME_RE = re.compile(r"(?:^|_)(PATH|DIR|FILE|ROOT|FOLDER)$", re.I)


def _is_fs_consuming_call(call: ast.Call) -> bool:
    """该 Call 是否以 filesystem 路径为参数（Path()/os.*/shutil.* 等）。"""
    func = call.func
    # Name: Path(...) / PurePath(...)
    if isinstance(func, ast.Name):
        return func.id in _FS_CONSUMING_NAMES
    # Attribute: os.path.exists / shutil.copy / pathlib.Path
    if isinstance(func, ast.Attribute):
        qualified = _resolve_call_target(call)
        if qualified and qualified in _FS_CONSUMING_QUALIFIED:
            return True
        # 末段名（兼容 from os.path import join 后直接 join(...) 不一定可识别，
        # 但 attribute 形态下用 attr 末段）
        if func.attr in _FS_CONSUMING_NAMES:
            return True
    return False


def _is_path_named_target(target: ast.expr) -> bool:
    """Assign target 名是否暗示是 filesystem 路径变量（_PATH / _DIR / _FILE / _ROOT）。"""
    name: Optional[str] = None
    if isinstance(target, ast.Name):
        name = target.id
    elif isinstance(target, ast.Attribute):
        name = target.attr
    if not name:
        return False
    return bool(_PATH_VAR_NAME_RE.search(name))


def _string_constants_in_call(call: ast.Call) -> Iterable[ast.Constant]:
    """提取 Call 的字符串字面量参数（args + keywords）。"""
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            yield arg
    for kw in call.keywords:
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            yield kw.value


def _string_constants_in_assign(assign: ast.Assign) -> Iterable[ast.Constant]:
    """Assign 右值若是字符串字面量直接 yield。"""
    if isinstance(assign.value, ast.Constant) and isinstance(assign.value.value, str):
        yield assign.value


def scan_c2_hardcoded_paths(py_files: Iterable[Path]) -> list[Finding]:
    """C2: 仅在"字符串作为 filesystem 路径被使用"时报告。

    检测策略（context-aware）：

    1. **filesystem call** — 字符串作为 ``Path()`` / ``os.path.exists()`` /
       ``shutil.copy()`` 等已知文件系统 API 的参数；
    2. **path-named target** — 字符串赋给名字暗示是路径的变量
       （``X_PATH`` / ``X_DIR`` / ``X_FILE`` / ``X_ROOT`` / ``X_FOLDER``）。

    其余场景（HTTP route / 中文显示标签 / 配置 dict 值 / sys.path
    bootstrap 中的 ``os.path.join`` 第二参数）**一律不报告**——这些
    在 Windows 上要么是 idiomatic 安全，要么根本不是路径。
    """
    findings: list[Finding] = []
    seen: set[tuple[str, int, str]] = set()

    def _emit(path: Path, const: ast.Constant) -> None:
        key = (str(path), const.lineno, const.value)
        if key in seen:
            return
        seen.add(key)
        findings.append(
            Finding(
                category="C2",
                severity="Low",
                path=str(path),
                line=const.lineno,
                message=f"疑似硬编码路径字面量: {const.value!r}",
                suggestion="改用 pathlib.Path 拼接，让分隔符在 Windows 上自动归一化",
            )
        )

    for path in py_files:
        src = safe_read_text(path)
        if not src:
            continue
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            # filesystem call
            if isinstance(node, ast.Call) and _is_fs_consuming_call(node):
                qualified = _resolve_call_target(node) or ""
                # os.path.join：除第一个参数外的字符串属于"组件"，跨平台安全 —— 跳过
                is_join = qualified in _FS_JOIN_TARGETS or (
                    isinstance(node.func, ast.Attribute) and node.func.attr == "join"
                )
                for idx, arg in enumerate(node.args):
                    if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                        continue
                    # join 的非首参视为安全组件
                    if is_join and idx > 0:
                        continue
                    if _looks_like_hardcoded_path(arg.value):
                        _emit(path, arg)
                # keyword string args 全检
                for kw in node.keywords:
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        if _looks_like_hardcoded_path(kw.value.value):
                            _emit(path, kw.value)

            # path-named assign target
            if isinstance(node, ast.Assign):
                if not any(_is_path_named_target(t) for t in node.targets):
                    continue
                for const in _string_constants_in_assign(node):
                    if _looks_like_hardcoded_path(const.value):
                        _emit(path, const)

            # AnnAssign 也覆盖：CONST_PATH: str = "a/b/c"
            if isinstance(node, ast.AnnAssign):
                if node.target is None or not _is_path_named_target(node.target):
                    continue
                if (
                    node.value is not None
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                    and _looks_like_hardcoded_path(node.value.value)
                ):
                    _emit(path, node.value)
    return findings


# ---------------------------------------------------------------------------
# C3: subprocess.run / Popen 文本模式缺 encoding 或 shell=True
# ---------------------------------------------------------------------------


def _resolve_call_target(call: ast.Call) -> Optional[str]:
    """对 ast.Call.func 做 'a.b.c' 形式的字符串还原。"""
    func = call.func
    parts: list[str] = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
        return ".".join(reversed(parts))
    return None


def _kw_value(call: ast.Call, name: str) -> Optional[ast.expr]:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _is_text_mode_subprocess(call: ast.Call) -> bool:
    """文本模式 = text=True 或 universal_newlines=True 或带 encoding=。"""
    for kw_name in ("text", "universal_newlines"):
        node = _kw_value(call, kw_name)
        if isinstance(node, ast.Constant) and node.value is True:
            return True
    if _kw_value(call, "encoding") is not None:
        return True
    return False


def scan_c3_subprocess(py_files: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    sub_targets = {
        "subprocess.run",
        "subprocess.Popen",
        "subprocess.check_output",
        "subprocess.check_call",
        "subprocess.call",
    }
    for path in py_files:
        src = safe_read_text(path)
        if not src:
            continue
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = _resolve_call_target(node)
            if target not in sub_targets:
                continue

            # shell=True 标志（Windows 引号地狱）
            shell_kw = _kw_value(node, "shell")
            if isinstance(shell_kw, ast.Constant) and shell_kw.value is True:
                findings.append(
                    Finding(
                        category="C3",
                        severity="High",
                        path=str(path),
                        line=node.lineno,
                        message=f"`{target}` 使用 shell=True (Windows 下中文/引号风险)",
                        suggestion="改用 args 列表传递；如必须 shell，显式指定 executable",
                    )
                )

            # 文本模式但缺 encoding
            if _is_text_mode_subprocess(node) and _kw_value(node, "encoding") is None:
                findings.append(
                    Finding(
                        category="C3",
                        severity="High",
                        path=str(path),
                        line=node.lineno,
                        message=f"`{target}` 文本模式缺 encoding=utf-8",
                        suggestion='补 encoding="utf-8"，避免 Windows cp936 解码',
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# C4: asyncio 入口未调 set_windows_proactor_policy
# ---------------------------------------------------------------------------


def _ancestor_conftest_covers_proactor(path: Path, root: Path) -> bool:
    """Walk up from ``path`` to ``root`` looking for a ``conftest.py`` that
    calls ``set_windows_proactor_policy`` at module load.

    pytest loads conftest.py in the collection tree before any test module, so
    a call inside ``tests/conftest.py`` applies the policy for every downstream
    test file. We honor the same inheritance in the scanner to avoid reporting
    redundant per-test-file policy calls (US-005).
    """
    try:
        current = path.resolve().parent
        root_resolved = root.resolve()
    except (OSError, ValueError):  # pragma: no cover - defensive
        return False
    # Bound the walk to ``root`` so we don't traverse outside the project.
    for _ in range(len(current.parts)):
        conftest = current / "conftest.py"
        if conftest.is_file():
            text = safe_read_text(conftest)
            if text and "set_windows_proactor_policy" in text:
                return True
        if current == root_resolved or root_resolved not in current.parents and current != root_resolved:
            if current.parent == current:
                break
        if current == root_resolved:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    return False


def scan_c4_asyncio(py_files: Iterable[Path], root: Optional[Path] = None) -> list[Finding]:
    findings: list[Finding] = []
    scan_root = root or PROJECT_ROOT
    # Cache conftest coverage per directory (expensive filesystem walk otherwise).
    _conftest_cache: dict[Path, bool] = {}
    for path in py_files:
        src = safe_read_text(path)
        if not src:
            continue
        if "asyncio" not in src:
            continue
        # 是否调用了 asyncio.run / new_event_loop / get_event_loop().run_*
        triggers = (
            "asyncio.run(",
            "asyncio.new_event_loop(",
            "asyncio.get_event_loop(",
            "asyncio.run_until_complete(",
        )
        if not any(t in src for t in triggers):
            continue
        # 检查是否调用了 set_windows_proactor_policy
        if "set_windows_proactor_policy" in src:
            continue
        # 若 ancestor conftest.py 已调 set_windows_proactor_policy，等同于已覆盖（pytest 自动加载）
        try:
            parent_key = path.resolve().parent
        except (OSError, ValueError):  # pragma: no cover
            parent_key = path.parent
        cached = _conftest_cache.get(parent_key)
        if cached is None:
            cached = _ancestor_conftest_covers_proactor(path, scan_root)
            _conftest_cache[parent_key] = cached
        if cached:
            continue
        # 找第一个 trigger 行号
        first_line = 1
        for idx, line in enumerate(src.splitlines(), start=1):
            if any(t in line for t in triggers):
                first_line = idx
                break
        findings.append(
            Finding(
                category="C4",
                severity="High",
                path=str(path),
                line=first_line,
                message="asyncio 入口未调 set_windows_proactor_policy()",
                suggestion="在 main 函数顶部 import 并调用 set_windows_proactor_policy()（Mac no-op）",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# C5: Path.symlink_to / os.symlink 未走 runtime_compat.safe_symlink
# ---------------------------------------------------------------------------


# 这些函数体内的裸 symlink 是文档化的底层 primitive（privilege 探测 / helper
# 自身实现），不应报 C5。
_C5_PRIMITIVE_FUNCS = {"_has_symlink_privilege", "safe_symlink"}

# 允许在行尾用 pragma 显式抑制（例如 symlink 是测试 SUT 时）
_C5_NOQA_RE = re.compile(r"#\s*(?:noqa\s*:\s*[cC]5|[cC]5-ok)\b")


def _is_raw_symlink_call(call: ast.Call) -> bool:
    """Return True for ``os.symlink(...)`` or ``<expr>.symlink_to(...)``.

    AST-based detection 天然跳过 docstring/字符串字面量 —— 相比旧的 line-regex
    扫描，不会把 ``'…os.symlink…'`` 这类字面量当作真实调用。
    """
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr == "symlink_to":
        # Path(...).symlink_to(...) / self.link.symlink_to(...)
        return True
    if func.attr == "symlink":
        # os.symlink(...)，含 x.os.symlink(...) 链式属性
        receiver = func.value
        if isinstance(receiver, ast.Name) and receiver.id == "os":
            return True
        if isinstance(receiver, ast.Attribute) and receiver.attr == "os":
            return True
    return False


def _line_has_c5_noqa(source: str, lineno: int) -> bool:
    lines = source.splitlines()
    if 1 <= lineno <= len(lines):
        return bool(_C5_NOQA_RE.search(lines[lineno - 1]))
    return False


def scan_c5_symlink(py_files: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in py_files:
        src = safe_read_text(path)
        if not src:
            continue
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue

        func_stack: list[str] = []
        file_findings: list[Finding] = []

        class _Visitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                func_stack.append(node.name)
                self.generic_visit(node)
                func_stack.pop()

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                func_stack.append(node.name)
                self.generic_visit(node)
                func_stack.pop()

            def visit_Call(self, node: ast.Call) -> None:
                self.generic_visit(node)
                if not _is_raw_symlink_call(node):
                    return
                # primitive 函数体内的裸 symlink 是有意为之
                if any(fn in _C5_PRIMITIVE_FUNCS for fn in func_stack):
                    return
                # 行尾 pragma 显式抑制
                if _line_has_c5_noqa(src, node.lineno):
                    return
                file_findings.append(
                    Finding(
                        category="C5",
                        severity="High",
                        path=str(path),
                        line=node.lineno,
                        message="裸 symlink 调用，Windows 非管理员会抛 OSError",
                        suggestion=(
                            "改走 runtime_compat.safe_symlink(src, dst)，"
                            "无权限自动 copyfile 降级"
                        ),
                    )
                )

        _Visitor().visit(tree)
        findings.extend(file_findings)
    return findings


# ---------------------------------------------------------------------------
# C6: *.sh 缺同目录同名 .ps1 / .cmd 对等
# ---------------------------------------------------------------------------


def scan_c6_sh_ps1_cmd_parity(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for sh in iter_files(root, (".sh",)):
        # 仅审计面向用户的入口：与 SKILL.md / docs / README 同处或 scripts/ 下
        # 启发式：所有 .sh 都纳入审计，让维护者自行决定是否例外
        ps1 = sh.with_suffix(".ps1")
        cmd = sh.with_suffix(".cmd")
        missing: list[str] = []
        if not ps1.exists():
            missing.append(".ps1")
        if not cmd.exists():
            missing.append(".cmd")
        if not missing:
            continue
        findings.append(
            Finding(
                category="C6",
                severity="High",
                path=str(sh),
                line=1,
                message=f".sh 缺对等入口: {', '.join(missing)}",
                suggestion=".ps1 必须 UTF-8 BOM；.cmd 双击包装。参考 ink-auto.ps1 / ink-auto.cmd（如已有）",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# C7: SKILL.md 引用 .sh 但缺 Windows PowerShell sibling 块
# ---------------------------------------------------------------------------


_SH_REF_RE = re.compile(r"\b([\w./\-]+\.sh)\b")
_WIN_SIBLING_MARKER_RE = re.compile(r"<!--\s*windows-ps1-sibling\s*-->", re.I)
_PS1_REF_RE = re.compile(r"\b([\w./\-]+\.ps1)\b")


def scan_c7_skill_md_windows_block(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for md in iter_files(root, (".md",)):
        # 只看 SKILL.md（本规则专门保障 Skill 入口）
        if md.name != "SKILL.md":
            continue
        src = safe_read_text(md)
        if not src:
            continue
        # 找所有 .sh 引用
        sh_refs: list[tuple[int, str]] = []
        for idx, line in enumerate(src.splitlines(), start=1):
            for m in _SH_REF_RE.finditer(line):
                sh_refs.append((idx, m.group(1)))
        if not sh_refs:
            continue
        # 必须有 windows-ps1-sibling 标记 OR 至少有一个 .ps1 引用
        has_marker = bool(_WIN_SIBLING_MARKER_RE.search(src))
        ps1_refs = [m.group(1) for m in _PS1_REF_RE.finditer(src)]
        if has_marker and ps1_refs:
            continue
        first_line = sh_refs[0][0]
        if not has_marker:
            findings.append(
                Finding(
                    category="C7",
                    severity="High",
                    path=str(md),
                    line=first_line,
                    message="SKILL.md 引用 .sh 但缺 <!-- windows-ps1-sibling --> 标记",
                    suggestion="在 .sh 代码块下方追加 sibling 标记 + PowerShell 等价块（参考 ink-auto/SKILL.md:51）",
                )
            )
        elif not ps1_refs:
            findings.append(
                Finding(
                    category="C7",
                    severity="Medium",
                    path=str(md),
                    line=first_line,
                    message="存在 sibling 标记但未引用任何 .ps1 文件",
                    suggestion="补 PowerShell 命令块，引用同名 .ps1 入口",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# C8: 硬编码 python3 / python（应走 find_python_launcher）
# ---------------------------------------------------------------------------


_PYTHON_HARDCODE_RE = re.compile(
    r"(?:(?<![\w/])python3(?![\w/])|(?<![\w/])py\s+-3(?![\w]))"
)


def scan_c8_python_launcher(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_files(root, (".sh", ".ps1", ".cmd", ".bat")):
        src = safe_read_text(path)
        if not src:
            continue
        for idx, line in enumerate(src.splitlines(), start=1):
            stripped = line.lstrip()
            # shebang 保留：#!/usr/bin/env python3 在 Mac/Linux 是标准做法
            if stripped.startswith("#!"):
                continue
            if stripped.startswith("#") or stripped.startswith("//"):
                continue
            # 寻找硬编码
            if not _PYTHON_HARDCODE_RE.search(line):
                continue
            # 已经在调用 find_python_launcher 的行跳过
            if "find_python_launcher" in line:
                continue
            findings.append(
                Finding(
                    category="C8",
                    severity="Medium",
                    path=str(path),
                    line=idx,
                    message="硬编码 python3 / py -3 启动器",
                    suggestion="改走 find_python_launcher() 输出（脚本中可先 export PY_LAUNCHER=$(...) 再用）",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# C9: Python CLI 入口未调 enable_windows_utf8_stdio
# ---------------------------------------------------------------------------


def scan_c9_cli_utf8_stdio(py_files: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in py_files:
        src = safe_read_text(path)
        if not src:
            continue
        # 启发式 1：必须含 if __name__ == "__main__":
        if 'if __name__ == "__main__"' not in src and "if __name__ == '__main__'" not in src:
            continue
        if "enable_windows_utf8_stdio" in src:
            continue
        # 找 if __name__ 行
        first_line = 1
        for idx, line in enumerate(src.splitlines(), start=1):
            if "__name__" in line and "__main__" in line:
                first_line = idx
                break
        # 严重级别：用户面向 CLI = High；纯测试 / 内部脚本 = Medium
        # 启发式：路径含 'tests/' 降为 Medium
        rel = str(path)
        severity = "Medium" if "tests" in rel.split("/") else "High"
        findings.append(
            Finding(
                category="C9",
                severity=severity,
                path=rel,
                line=first_line,
                message="CLI 入口（__main__）未调 enable_windows_utf8_stdio()",
                suggestion="文件顶部 import runtime_compat 后，在 main 开头 enable_windows_utf8_stdio()（Mac no-op）",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# 顶层调度
# ---------------------------------------------------------------------------


def collect_python_files(root: Path) -> list[Path]:
    return list(iter_files(root, (".py",)))


def run_audit(root: Path) -> AuditReport:
    """执行所有 9 类扫描。"""
    report = AuditReport()
    py_files = collect_python_files(root)

    report.findings.extend(scan_c1_open_encoding(py_files))
    report.findings.extend(scan_c2_hardcoded_paths(py_files))
    report.findings.extend(scan_c3_subprocess(py_files))
    report.findings.extend(scan_c4_asyncio(py_files, root=root))
    report.findings.extend(scan_c5_symlink(py_files))
    report.findings.extend(scan_c6_sh_ps1_cmd_parity(root))
    report.findings.extend(scan_c7_skill_md_windows_block(root))
    report.findings.extend(scan_c8_python_launcher(root))
    report.findings.extend(scan_c9_cli_utf8_stdio(py_files))

    # 排序: 严重级别 → 类别 → 路径 → 行号
    report.findings.sort(
        key=lambda f: (
            SEVERITY_ORDER.get(f.severity, 99),
            f.category,
            f.path,
            f.line,
        )
    )
    return report


# ---------------------------------------------------------------------------
# Markdown 渲染
# ---------------------------------------------------------------------------


_CATEGORY_TITLES = {
    "C1": "C1 — `open()` / `read_text()` / `write_text()` 缺 UTF-8 编码",
    "C2": "C2 — 硬编码路径分隔符（疑似）",
    "C3": "C3 — `subprocess` 调用文本模式缺 encoding 或 `shell=True`",
    "C4": "C4 — asyncio 入口未调 `set_windows_proactor_policy()`",
    "C5": "C5 — 裸 `symlink` 调用未走 `safe_symlink()` 兜底",
    "C6": "C6 — `*.sh` 缺同目录 `.ps1` / `.cmd` 对等入口",
    "C7": "C7 — `SKILL.md` 引用 `.sh` 缺 Windows PowerShell sibling 块",
    "C8": "C8 — 脚本硬编码 `python3` / `py -3`（未走 `find_python_launcher`）",
    "C9": "C9 — Python CLI 入口未调 `enable_windows_utf8_stdio()`",
}

_CATEGORY_TO_US = {
    "C1": "US-002",
    "C2": "US-003",
    "C3": "US-004",
    "C4": "US-005",
    "C5": "US-006",
    "C6": "US-007",
    "C7": "US-008",
    "C8": "US-009",
    "C9": "US-010",
}


def render_markdown(report: AuditReport, root: Path) -> str:
    """把 AuditReport 渲染为 Markdown findings 报告。"""
    lines: list[str] = []
    lines.append("# 跨平台兼容性审计 Findings 报告（US-001）")
    lines.append("")
    lines.append(f"扫描根目录: `{root}`")
    lines.append("")
    counts = report.severity_counts()
    total = len(report.findings)
    lines.append(
        f"**总 finding 数**: {total} "
        f"(Blocker={counts.get('Blocker',0)} / "
        f"High={counts.get('High',0)} / "
        f"Medium={counts.get('Medium',0)} / "
        f"Low={counts.get('Low',0)})"
    )
    lines.append("")
    lines.append("## 按类别汇总")
    lines.append("")
    lines.append("| 类别 | 数量 | 对应修复 US |")
    lines.append("|------|------|-------------|")
    by_cat = report.by_category()
    for cat in [f"C{i}" for i in range(1, 10)]:
        n = len(by_cat.get(cat, []))
        us = _CATEGORY_TO_US.get(cat, "-")
        lines.append(f"| {cat} | {n} | {us} |")
    lines.append("")

    # 各类别明细
    for cat in [f"C{i}" for i in range(1, 10)]:
        items = by_cat.get(cat, [])
        if not items:
            continue
        title = _CATEGORY_TITLES[cat]
        lines.append(f"## {title}")
        lines.append("")
        lines.append(f"对应修复 US: **{_CATEGORY_TO_US.get(cat, '-')}**  数量: **{len(items)}**")
        lines.append("")
        lines.append("| 文件:行 | 严重级别 | 现象 | 修复建议 |")
        lines.append("|---------|----------|------|----------|")
        for item in items[:200]:  # 单类别最多展示 200 条，避免报告膨胀
            lines.append(item.as_md_row(root=root))
        if len(items) > 200:
            lines.append(f"| ... | ... | （省略 {len(items) - 200} 条，详见脚本 JSON 输出） | - |")
        lines.append("")

    # seed_us_list
    lines.append("## Seed US List（按严重级别排序）")
    lines.append("")
    lines.append("供下一轮 PRD 迭代直接消费。已与本 PRD 既有 US-002~US-010 对齐，")
    lines.append("数字列表为各类风险对应 US 的优先级再排序参考：")
    lines.append("")
    seed: list[tuple[str, int, str]] = []  # (US, 数量, 类别)
    for cat, items in by_cat.items():
        if not items:
            continue
        # 该类别最严重 finding 决定排序键
        worst = min(SEVERITY_ORDER.get(it.severity, 99) for it in items)
        seed.append((_CATEGORY_TO_US.get(cat, "-"), len(items), cat))
        # 将 worst 也带上以便排序
    # 重新排序
    seed_with_worst: list[tuple[int, str, int, str]] = []
    for cat, items in by_cat.items():
        if not items:
            continue
        worst = min(SEVERITY_ORDER.get(it.severity, 99) for it in items)
        seed_with_worst.append(
            (worst, _CATEGORY_TO_US.get(cat, "-"), len(items), cat)
        )
    seed_with_worst.sort()
    for idx, (_w, us, n, cat) in enumerate(seed_with_worst, start=1):
        lines.append(f"{idx}. **{us}**（{cat}, {n} 处）— {_CATEGORY_TITLES[cat].split('—', 1)[1].strip()}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_报告由 `scripts/audit_cross_platform.py` 自动生成，请勿手工编辑。_")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=PROJECT_ROOT,
        help="扫描根目录（默认仓库根）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "reports" / "cross-platform-audit-findings.md",
        help="Markdown 报告输出路径",
    )
    parser.add_argument(
        "--fail-on",
        choices=["never", "blocker", "high"],
        default="never",
        help="非零退出阈值（never/blocker/high）",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()
    if not root.exists():
        print(f"[audit_cross_platform] root not found: {root}", file=_sys_win_stdio.stderr)
        return 2

    report = run_audit(root)
    markdown = render_markdown(report, root)

    out_path: Path = args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    print(f"[audit_cross_platform] {len(report.findings)} findings → {out_path}")

    if args.fail_on == "blocker":
        if any(f.severity == "Blocker" for f in report.findings):
            return 1
    elif args.fail_on == "high":
        if any(f.severity in ("Blocker", "High") for f in report.findings):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
