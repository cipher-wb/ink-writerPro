"""US-007 仓库级红线：`.sh` 面向用户入口必须伴随同名 `.ps1` + `.cmd` 对等。

由 `scripts/audit_cross_platform.py:scan_c6_sh_ps1_cmd_parity` 守护。这里把
同一断言挪进 pytest，后续 PR 引入新 `.sh` 但忘了补 Windows 对等时直接在 CI 挂掉，
不用等下次 audit 跑。

额外断言：
- `.ps1` 文件必须以 UTF-8 BOM 开头（PowerShell 5.1 Windows 默认读取 .ps1 用 ANSI
  解码，没有 BOM 会让中文变乱码；Codebase Patterns / CLAUDE.md Windows 守则已固化）
- `.cmd` 必须转发到同名 `.ps1`（双击入口最小行为：一行 `powershell … -File %~dp0foo.ps1`）
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# 与 scripts/audit_cross_platform.py:EXCLUDE_DIR_NAMES 保持同步（手动固化一份避免 import 副作用）
_EXCLUDE_DIR_NAMES = {
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
    "archive",
    ".coverage",
    "htmlcov",
}

UTF8_BOM = b"\xef\xbb\xbf"


def _is_nested_git_repo(path: Path, root: Path) -> bool:
    """若 path 位于 root 下某个含 `.git/` 的子目录内（嵌套 git 仓库，如 /ralph/ 的
    外部 clone），视为"不在本仓库跨平台承诺范围内"——与 `scripts/audit_cross_platform.py`
    的 `_is_nested_git_repo_dir` 保持语义一致。"""
    try:
        root_resolved = root.resolve()
    except OSError:
        root_resolved = root
    current = path.parent
    while True:
        try:
            current_resolved = current.resolve()
        except OSError:
            return False
        if current_resolved == root_resolved:
            return False
        if (current / ".git").exists():
            return True
        if current.parent == current:
            return False
        current = current.parent


def _iter_sh_scripts(root: Path):
    for path in root.rglob("*.sh"):
        if any(part in _EXCLUDE_DIR_NAMES for part in path.parts):
            continue
        if _is_nested_git_repo(path, root):
            continue
        yield path


def test_every_sh_has_ps1_and_cmd_sibling():
    """`.sh` 入口必须有同目录同名 `.ps1` + `.cmd` 对等，否则 Windows 用户无法使用。"""
    missing: list[str] = []
    for sh in _iter_sh_scripts(REPO_ROOT):
        ps1 = sh.with_suffix(".ps1")
        cmd = sh.with_suffix(".cmd")
        gaps = []
        if not ps1.exists():
            gaps.append(".ps1")
        if not cmd.exists():
            gaps.append(".cmd")
        if gaps:
            rel = sh.relative_to(REPO_ROOT)
            missing.append(f"{rel}: 缺 {', '.join(gaps)}")

    assert not missing, (
        "以下 .sh 缺同目录对等入口（Windows 用户无法使用）：\n  "
        + "\n  ".join(missing)
        + "\n参考 ink-writer/scripts/ink-auto.{ps1,cmd} 模式。"
    )


def test_every_ps1_sibling_has_utf8_bom():
    """PowerShell 5.1 默认按 ANSI 解码 `.ps1`，没有 UTF-8 BOM 会让中文字符串乱码。

    只检查那些确实是 `.sh` sibling 的 `.ps1`（避免把独立 `.ps1` 脚本也一并检查，
    保持最小作用域）。
    """
    violators: list[str] = []
    for sh in _iter_sh_scripts(REPO_ROOT):
        ps1 = sh.with_suffix(".ps1")
        if not ps1.exists():
            continue
        head = ps1.read_bytes()[:3]
        if head != UTF8_BOM:
            violators.append(str(ps1.relative_to(REPO_ROOT)))

    assert not violators, (
        "以下 .ps1 缺 UTF-8 BOM（PowerShell 5.1 下中文乱码）：\n  "
        + "\n  ".join(violators)
    )


def test_every_cmd_sibling_forwards_to_ps1():
    """`.cmd` 最小行为：双击/CMD 下转发到同名 `.ps1`。

    允许形式宽松——只要同时包含 `powershell` 关键字和对应 `.ps1` 文件名即可，
    不强要求参数细节（各 .cmd 已在 env-setup/ink-auto/migrate_webnovel_to_ink/ralph
    中统一走 `-NoProfile -ExecutionPolicy Bypass -File`，但若未来有脚本需要自定义
    转发策略也不被本测试阻断）。
    """
    violators: list[str] = []
    for sh in _iter_sh_scripts(REPO_ROOT):
        cmd = sh.with_suffix(".cmd")
        ps1_name = sh.with_suffix(".ps1").name
        if not cmd.exists():
            continue
        body = cmd.read_text(encoding="utf-8", errors="replace").lower()
        if "powershell" not in body or ps1_name.lower() not in body:
            violators.append(str(cmd.relative_to(REPO_ROOT)))

    assert not violators, (
        "以下 .cmd 未转发到同名 .ps1（双击入口失效）：\n  " + "\n  ".join(violators)
    )


@pytest.mark.parametrize(
    "sh_rel",
    [
        # US-007 新增：migrate_webnovel_to_ink 面向用户迁移脚本
        "ink-writer/scripts/migrate_webnovel_to_ink.sh",
        # 既有（v19 已补）：scripts/ralph 的 in-repo ralph 入口（/ralph/ 是外部 clone，
        # 被 _is_nested_git_repo 扫描器自动跳过，这里关注 in-repo 副本）
        "scripts/ralph/ralph.sh",
    ],
)
def test_newly_added_siblings_exist(sh_rel: str):
    """US-007 本轮显式补齐 + 既有 in-repo 入口，单独固化防误删。"""
    sh = REPO_ROOT / sh_rel
    if not sh.exists():
        pytest.skip(f"{sh_rel} 不在仓库中（可能已重构），跳过")
    assert sh.with_suffix(".ps1").exists(), f"缺 {sh_rel[:-3]}.ps1"
    assert sh.with_suffix(".cmd").exists(), f"缺 {sh_rel[:-3]}.cmd"
