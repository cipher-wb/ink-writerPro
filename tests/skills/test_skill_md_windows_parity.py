"""US-008 仓库级红线：SKILL.md 引用 `.sh` 处必须有 Windows PowerShell 等价块。

由 `scripts/audit_cross_platform.py:scan_c7_skill_md_windows_block` 守护。这里把
同一约束挪进 pytest，后续 PR 若新增 SKILL.md 的 `.sh` 代码块但忘了补
`<!-- windows-ps1-sibling -->` 标记 + 同名 `.ps1` 引用，直接在 CI 挂掉，不用等
下次 audit 跑。

规则（与 CLAUDE.md Windows 兼容守则第 3 条一致）：
- SKILL.md 一旦引用任何 `.sh`，必须同时具备：
  1. 至少一个 `<!-- windows-ps1-sibling -->` 标记（显式提示 Claude Code Windows 用户）
  2. 至少一个 `.ps1` 引用（PowerShell 等价命令）
- 更强约束（stem 级 parity）：每个被引用的 `foo.sh` 必须有同 stem `foo.ps1`
  在同一文件内被引用——避免"标记对但引用的 .ps1 和 .sh 不是一对"的漂移。

排除范围：
- `archive/` / `__pycache__/` / `.venv/` 等（与 audit `EXCLUDE_DIR_NAMES` 对齐）
- 嵌套 git 仓库（如 `/ralph/` 外部 clone，`.gitignore:63`，不在跨平台承诺范围）
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# 与 scripts/audit_cross_platform.py:EXCLUDE_DIR_NAMES 同步（手动固化，避免 import 副作用）
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

_SH_REF_RE = re.compile(r"\b([\w./\-]+\.sh)\b")
_PS1_REF_RE = re.compile(r"\b([\w./\-]+\.ps1)\b")
_WIN_SIBLING_MARKER_RE = re.compile(r"<!--\s*windows-ps1-sibling\s*-->", re.I)


def _is_nested_git_repo(path: Path, root: Path) -> bool:
    """与 `scripts/audit_cross_platform.py:_is_nested_git_repo_dir` 语义一致：
    若 path 位于 root 下某个含 `.git/` 子目录内（嵌套 clone），视为外部仓库跳过。
    """
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


def _iter_skill_md(root: Path):
    for path in root.rglob("SKILL.md"):
        if any(part in _EXCLUDE_DIR_NAMES for part in path.parts):
            continue
        if _is_nested_git_repo(path, root):
            continue
        yield path


def _sh_refs(src: str) -> list[str]:
    return [m.group(1) for m in _SH_REF_RE.finditer(src)]


def _ps1_refs(src: str) -> list[str]:
    return [m.group(1) for m in _PS1_REF_RE.finditer(src)]


def test_every_skill_md_referencing_sh_has_windows_sibling_marker() -> None:
    """SKILL.md 若引用 `.sh`，必须至少含一个 `<!-- windows-ps1-sibling -->` 标记。

    这是 Claude Code Windows 场景识别"同文件内有 PowerShell 等价命令"的明确信号。
    """
    violators: list[str] = []
    for md in _iter_skill_md(REPO_ROOT):
        src = md.read_text(encoding="utf-8")
        if not _sh_refs(src):
            continue
        if not _WIN_SIBLING_MARKER_RE.search(src):
            violators.append(str(md.relative_to(REPO_ROOT)))

    assert not violators, (
        "以下 SKILL.md 引用 .sh 但缺 <!-- windows-ps1-sibling --> 标记：\n  "
        + "\n  ".join(violators)
        + "\n参考 ink-writer/skills/ink-auto/SKILL.md:51 模式。"
    )


def test_every_skill_md_referencing_sh_also_references_ps1() -> None:
    """SKILL.md 若引用 `.sh`，同文件必须引用至少一个 `.ps1`——给 Windows 用户可执行替代。"""
    violators: list[str] = []
    for md in _iter_skill_md(REPO_ROOT):
        src = md.read_text(encoding="utf-8")
        if not _sh_refs(src):
            continue
        if not _ps1_refs(src):
            violators.append(str(md.relative_to(REPO_ROOT)))

    assert not violators, (
        "以下 SKILL.md 引用 .sh 但未引用任何 .ps1：\n  "
        + "\n  ".join(violators)
    )


def test_every_sh_reference_has_matching_ps1_stem_in_same_skill_md() -> None:
    """更强约束：每个被引用的 `foo.sh` 必须在同一 SKILL.md 内有同 stem `foo.ps1` 引用。

    防止"标记对齐但引用的 `.ps1` 和 `.sh` 实际不是一对"的漂移——比如只引用了
    `env-setup.ps1` 却还在新块里写了 `run.sh`，会让 Windows 用户拿不到 `run.ps1` 的
    线索。
    """
    violators: list[str] = []
    for md in _iter_skill_md(REPO_ROOT):
        src = md.read_text(encoding="utf-8")
        sh_stems = {Path(s).stem for s in _sh_refs(src)}
        ps1_stems = {Path(p).stem for p in _ps1_refs(src)}
        missing = sh_stems - ps1_stems
        if missing:
            rel = md.relative_to(REPO_ROOT)
            violators.append(f"{rel}: .sh stems 缺同名 .ps1: {sorted(missing)}")

    assert not violators, (
        "以下 SKILL.md 的 .sh 引用在同文件内缺同 stem .ps1 等价引用：\n  "
        + "\n  ".join(violators)
    )


@pytest.mark.parametrize(
    "skill_md_rel",
    [
        # ink-writer 全套 skill（v19 已补齐，固化防误删；ink-dashboard / ink-query /
        # ink-migrate 等 14 个 SKILL.md 任一丢 sibling 标记直接失败）
        "ink-writer/skills/ink-auto/SKILL.md",
        "ink-writer/skills/ink-write/SKILL.md",
        "ink-writer/skills/ink-plan/SKILL.md",
        "ink-writer/skills/ink-review/SKILL.md",
        "ink-writer/skills/ink-fix/SKILL.md",
        "ink-writer/skills/ink-init/SKILL.md",
        "ink-writer/skills/ink-resume/SKILL.md",
        "ink-writer/skills/ink-dashboard/SKILL.md",
        "ink-writer/skills/ink-query/SKILL.md",
        "ink-writer/skills/ink-resolve/SKILL.md",
        "ink-writer/skills/ink-audit/SKILL.md",
        "ink-writer/skills/ink-migrate/SKILL.md",
        "ink-writer/skills/ink-macro-review/SKILL.md",
        "ink-writer/skills/ink-learn/SKILL.md",
    ],
)
def test_known_ink_skill_md_has_windows_sibling(skill_md_rel: str) -> None:
    """v19 起 ink-writer 全套 SKILL.md 均已补 Windows sibling；逐个固化防误删。"""
    md = REPO_ROOT / skill_md_rel
    if not md.exists():
        pytest.skip(f"{skill_md_rel} 不在仓库中（可能已重构），跳过")
    src = md.read_text(encoding="utf-8")
    assert _WIN_SIBLING_MARKER_RE.search(src), (
        f"{skill_md_rel}: 缺 <!-- windows-ps1-sibling --> 标记"
    )
    assert _ps1_refs(src), f"{skill_md_rel}: 未引用任何 .ps1"
