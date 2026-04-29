"""preflight 路径解析回归（针对 2026-04-29 真实用户 bug）

历史 bug 描述：
  `_build_preflight_report` 把 reference_corpus / case_library / editor-wisdom rules.json
  当成 project 级资源，挂在用户的小说项目根下找。但这三类资源是 plugin/repo 级别
  （每装一次共用一份）。结果：
    - 用户在自己的小说目录跑 /ink-auto → preflight 在 <小说项目>/benchmark/reference_corpus
      找不到（不存在）→ exit 1
    - 用户根本走不到 v27 / S1 分支（即使 R1/R3 已修也救不了）

修复：用 repo_root（= scripts_dir.parent.parent）替换 project_root 作为这三类资源的根。

本测试守护两条不变量：
  1. _build_preflight_report 必须在调用 PreflightConfig 时使用 repo_root（或其他
     非 project_root 的解析），而不是 project_root 子目录
  2. 这三个文件在源码仓库里是真实存在的（防止 git rm 误删）
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INK_PY = REPO_ROOT / "ink_writer" / "core" / "cli" / "ink.py"


def test_plugin_level_resources_not_under_project_root():
    """preflight 不能把 reference_corpus / case_library / editor-wisdom 挂在 project_root 下。

    具体守护：源码不能再出现 `pr / "benchmark"` / `pr / "data"` 这类把
    project_root 当 plugin 资源根的写法。
    """
    src = INK_PY.read_text(encoding="utf-8")
    offenders: list[tuple[int, str]] = []
    for lineno, line in enumerate(src.splitlines(), start=1):
        # 跳过注释行（修复说明里会出现 "pr /" 但是注释）
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # 命中以下任一即视为回退到旧 bug 写法
        if re.search(r'\bpr\s*/\s*["\']benchmark["\']', line):
            offenders.append((lineno, line.rstrip()))
        if re.search(r'\bpr\s*/\s*["\']data["\']\s*/\s*["\']case_library["\']', line):
            offenders.append((lineno, line.rstrip()))
        if re.search(r'\bpr\s*/\s*["\']data["\']\s*/\s*["\']editor-wisdom["\']', line):
            offenders.append((lineno, line.rstrip()))

    assert not offenders, (
        "ink.py 不能把 reference_corpus / case_library / editor-wisdom 挂在 project_root（pr）下。\n"
        "这三类是 plugin/repo 级资源，应该用 repo_root（= scripts_dir.parent.parent）。\n"
        "回退位置：\n"
        + "\n".join(f"  line {ln}: {text}" for ln, text in offenders)
    )


def test_preflight_uses_repo_root_for_plugin_resources():
    """正向断言：_build_preflight_report 必须出现 repo_root 这个变量名 + 用它构造 PreflightConfig。"""
    src = INK_PY.read_text(encoding="utf-8")

    # 1. 必须有 repo_root 解析
    assert "repo_root = plugin_root.parent" in src, (
        "_build_preflight_report 必须解析 repo_root = plugin_root.parent，"
        "用于定位 plugin/repo 级资源。"
    )

    # 2. 必须用 repo_root 构造 reference_root / case_library_root / editor_wisdom_rules_path
    patterns = [
        r"reference_root\s*=\s*repo_root\s*/",
        r"case_library_root\s*=\s*repo_root\s*/",
        r"editor_wisdom_rules_path\s*=\s*repo_root\s*/",
    ]
    for pat in patterns:
        assert re.search(pat, src), (
            f"_build_preflight_report 必须用 repo_root 构造 plugin 级资源路径；"
            f"未找到匹配模式: {pat}"
        )


def test_plugin_resources_actually_exist_in_repo():
    """防御性：仓库里这三个资源必须真实存在，不能被误删。

    数量阈值与 preflight 阈值对齐，避免误删导致测试通过但用户跑预检失败。
    """
    reference = REPO_ROOT / "benchmark" / "reference_corpus"
    assert reference.is_dir(), f"reference_corpus 缺失: {reference}"
    txt_count = sum(1 for _ in reference.rglob("*.txt"))
    assert txt_count >= 100, (
        f"reference_corpus 里 .txt 文件数 ({txt_count}) 少于 preflight 阈值 100。"
    )

    cases = REPO_ROOT / "data" / "case_library" / "cases"
    assert cases.is_dir(), f"case_library/cases 缺失: {cases}"
    case_count = sum(1 for _ in cases.glob("CASE-*.yaml"))
    assert case_count >= 1, f"case_library 里没有 CASE-*.yaml: {cases}"

    rules = REPO_ROOT / "data" / "editor-wisdom" / "rules.json"
    assert rules.is_file(), f"editor-wisdom rules.json 缺失: {rules}"
    assert rules.stat().st_size > 1000, f"editor-wisdom rules.json 文件过小，疑似被清空"
