#!/usr/bin/env python3
"""v13 US-022：自动校验 README / architecture.md / agent_topology_v13.md 中的
关键数字与实际代码/文件系统是否一致。

用途：防止文档长期落后于代码（v5 审计 Major：README 38 实际 37，
agent_topology 17 实际 22）。CI 中作为一步跑，不一致即 exit 1。

检查项：
  1. README.md 中的 '37 种题材模板' vs ink-writer/templates/genres/*.md count
  2. agent_topology_v13.md 中的 'After (v13.X): N Agents' vs ink-writer/agents/*.md count
  3. architecture.md 中的 checker 数（如声明） vs ink-writer/agents/*-checker.md count

Usage:
    python3 scripts/verify_docs.py              # 校验，不一致 exit 1
    python3 scripts/verify_docs.py --report     # 仅打印实测值不校验
"""
from __future__ import annotations

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio
_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    '../ink-writer/scripts',
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

README = ROOT / "README.md"
TOPOLOGY = ROOT / "docs" / "agent_topology_v13.md"
ARCHITECTURE = ROOT / "docs" / "architecture.md"

TEMPLATES_DIR = ROOT / "ink-writer" / "templates" / "genres"
AGENTS_DIR = ROOT / "ink-writer" / "agents"
SKILLS_DIR = ROOT / "ink-writer" / "skills"
PIPELINE_MANAGER = ROOT / "ink_writer" / "parallel" / "pipeline_manager.py"


class Finding:
    def __init__(self, file: str, claim: str, actual: str, ok: bool) -> None:
        self.file = file
        self.claim = claim
        self.actual = actual
        self.ok = ok

    def render(self) -> str:
        icon = "✅" if self.ok else "❌"
        return f"{icon} {self.file}: claim='{self.claim}' actual='{self.actual}'"


def count_files(pattern_dir: Path, glob_pat: str = "*.md") -> int:
    if not pattern_dir.exists():
        return 0
    return len(list(pattern_dir.glob(glob_pat)))


def check_readme_templates() -> Finding:
    actual = count_files(TEMPLATES_DIR)
    if not README.exists():
        return Finding("README.md", "N/A", f"{actual}", False)
    content = README.read_text(encoding="utf-8")
    # 匹配 "N 种题材模板" 或 "N 种模板"（多种表述容忍）
    m = re.search(r"(\d+)\s*种(?:题材)?模板", content)
    if not m:
        return Finding("README.md", "no match for 'N 种题材模板'", f"{actual}", False)
    claim = int(m.group(1))
    return Finding("README.md", f"{claim} 种题材模板", f"{actual}", claim == actual)


def check_topology_agents() -> Finding:
    # Count all *.md in agents/ (including agent + checker)
    actual = count_files(AGENTS_DIR)
    if not TOPOLOGY.exists():
        return Finding("agent_topology_v13.md", "N/A", f"{actual}", False)
    content = TOPOLOGY.read_text(encoding="utf-8")
    # 匹配 "After (v13.X): N Agents" 或 "N Agents, Single Directory"
    m = re.search(r"(?:After\s*\(v13[.\w]*\):|^)\s*(\d+)\s*Agents", content, re.MULTILINE)
    if not m:
        return Finding("agent_topology_v13.md", "no match for 'N Agents'", f"{actual}", False)
    claim = int(m.group(1))
    return Finding("agent_topology_v13.md", f"{claim} Agents", f"{actual}", claim == actual)


CHAPTER_LOCK_FORBIDDEN_PATTERNS: tuple[str, ...] = (
    r"ChapterLockManager\s*保护",
    r"parallel\s*>\s*1\s*安全",
)


# v16 US-006：FIX-11 设计稿 §6.2 零裸路径 + §6.3 零 data_modules 校验。
DATA_MODULES_SCAN_DIRS: tuple[Path, ...] = (
    ROOT / "ink_writer",
    ROOT / "ink-writer" / "scripts",
    ROOT / "scripts",
)
DATA_MODULES_IMPORT_RE = re.compile(
    r"(?m)^(\s*)(from\s+data_modules|import\s+data_modules)\b"
)
DATA_MODULES_WHITELIST_SUBPATHS: tuple[str, ...] = (
    "archive/",
    "benchmark/",
    "tests/migration/",
    "ralph/",
)


def _is_whitelisted(rel: Path) -> bool:
    s = str(rel).replace("\\", "/")
    return any(s.startswith(w) for w in DATA_MODULES_WHITELIST_SUBPATHS)


def check_no_data_modules_imports(
    scan_dirs: tuple[Path, ...] = DATA_MODULES_SCAN_DIRS,
    root: Path = ROOT,
) -> list[Finding]:
    """FIX-11 §6.3：禁止代码中再出现 ``from data_modules`` / ``import data_modules``。

    白名单：archive/, benchmark/, tests/migration/, ralph/ 外部工具目录。
    """
    findings: list[Finding] = []
    for d in scan_dirs:
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            try:
                rel = py.resolve().relative_to(root.resolve())
            except ValueError:
                rel = py
            if _is_whitelisted(rel):
                continue
            text = py.read_text(encoding="utf-8", errors="ignore")
            if DATA_MODULES_IMPORT_RE.search(text):
                findings.append(
                    Finding(
                        str(rel),
                        "contains data_modules import (FIX-11 §6.3 violation)",
                        "must be migrated to ink_writer.core.*",
                        ok=False,
                    )
                )
    return findings


def check_chapter_lock_consistency(
    skills_dir: Path = SKILLS_DIR,
    pipeline_manager: Path = PIPELINE_MANAGER,
) -> list[Finding]:
    """v16 US-001：SKILL.md 如出现"ChapterLockManager 保护"或"parallel>1 安全"
    等并发安全声明，必须与 ``ink_writer/parallel/pipeline_manager.py`` 诚实
    降级段（"尚未接入"）同步——若 pipeline_manager 仍诚实声明未接入而 SKILL.md
    却声称保护，视为文档-代码漂移，CI fail。
    """
    findings: list[Finding] = []
    if not skills_dir.exists() or not pipeline_manager.exists():
        return findings

    pipeline_src = pipeline_manager.read_text(encoding="utf-8")
    # "尚未接入" = pipeline_manager.py:10-17 诚实降级段关键词
    pipeline_declares_not_integrated = "尚未接入" in pipeline_src

    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        content = skill_md.read_text(encoding="utf-8")
        for pat in CHAPTER_LOCK_FORBIDDEN_PATTERNS:
            if not re.search(pat, content):
                continue
            rel = skill_md.relative_to(ROOT) if skill_md.is_absolute() and ROOT in skill_md.parents else skill_md
            ok = not pipeline_declares_not_integrated
            findings.append(
                Finding(
                    str(rel),
                    f"claim matches /{pat}/",
                    (
                        "pipeline_manager.py 仍含 '尚未接入' 诚实声明 → 文档与代码矛盾"
                        if not ok
                        else "pipeline_manager.py 已移除 '尚未接入' → 同步"
                    ),
                    ok,
                )
            )
    return findings


# v16 US-020：Skill/Agent frontmatter completeness 守卫。
# 规则：
#   - 所有 ink-writer/skills/*/SKILL.md 必须含 name/description/allowed-tools 三字段。
#   - 所有 ink-writer/agents/*.md 必须含 name/description/tools 三字段。
#   - 新增 agent 如声明默认 allowed-tools 超出 "Read"（例如 Bash/Write/Edit 等
#     高权限工具）且未在 description 中给出理由关键字（"需要"/"因为"/"since"），
#     CI 发 warning（不 fail，仅提示人工审阅）。
SKILL_REQUIRED_FIELDS: tuple[str, ...] = ("name", "description", "allowed-tools")
AGENT_REQUIRED_FIELDS: tuple[str, ...] = ("name", "description", "tools")
HIGH_PRIV_TOOLS: tuple[str, ...] = ("Bash", "Write", "Edit", "Task", "WebFetch")


def _parse_frontmatter(md_path: Path) -> dict[str, str]:
    """Return field→value dict from the first YAML-ish frontmatter block.

    Minimal parser: accepts `key: value` on single line within the first
    `---` / `---` fence. Values are kept raw (trimmed)."""
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return fm


def check_skill_frontmatter(
    skills_dir: Path = SKILLS_DIR,
) -> list[Finding]:
    """Every SKILL.md must include name/description/allowed-tools."""
    findings: list[Finding] = []
    if not skills_dir.exists():
        return findings
    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        fm = _parse_frontmatter(skill_md)
        missing = [f for f in SKILL_REQUIRED_FIELDS if f not in fm or not fm[f]]
        try:
            rel = skill_md.relative_to(ROOT)
        except ValueError:
            rel = skill_md
        if missing:
            findings.append(
                Finding(
                    str(rel),
                    f"frontmatter must include {SKILL_REQUIRED_FIELDS}",
                    f"missing={missing}",
                    ok=False,
                )
            )
        else:
            findings.append(
                Finding(
                    str(rel),
                    "skill frontmatter complete",
                    "name/description/allowed-tools present",
                    ok=True,
                )
            )
    return findings


def check_agent_frontmatter(
    agents_dir: Path = AGENTS_DIR,
) -> list[Finding]:
    """Every agent .md must include name/description/tools.

    Additionally emits a soft warning (still ok=True) when a newly
    added agent declares high-privilege default tools beyond ``Read``
    without a justification keyword in description — CI 只提示不 fail。
    """
    findings: list[Finding] = []
    if not agents_dir.exists():
        return findings
    for agent_md in sorted(agents_dir.glob("*.md")):
        fm = _parse_frontmatter(agent_md)
        missing = [f for f in AGENT_REQUIRED_FIELDS if f not in fm or not fm[f]]
        try:
            rel = agent_md.relative_to(ROOT)
        except ValueError:
            rel = agent_md
        if missing:
            findings.append(
                Finding(
                    str(rel),
                    f"frontmatter must include {AGENT_REQUIRED_FIELDS}",
                    f"missing={missing}",
                    ok=False,
                )
            )
            continue

        # Soft warn: high-privilege tools beyond Read + no justification keyword.
        tools_field = fm.get("tools", "")
        declared = [t.strip() for t in re.split(r"[\s,]+", tools_field) if t.strip()]
        escalated = [t for t in declared if t in HIGH_PRIV_TOOLS]
        desc = fm.get("description", "")
        justified = any(kw in desc for kw in ("需要", "因为", "since", "requires"))
        if escalated and not justified:
            # warn-only: emit a Finding that renders with ⚠ prefix but
            # remains ok=True so CI does not fail.
            findings.append(
                Finding(
                    str(rel),
                    f"default tools include high-priv {escalated}",
                    "consider adding justification in description (warn only)",
                    ok=True,
                )
            )
        else:
            findings.append(
                Finding(
                    str(rel),
                    "agent frontmatter complete",
                    "name/description/tools present",
                    ok=True,
                )
            )
    return findings


def check_architecture_checkers() -> Finding | None:
    """architecture.md 若声明 checker 数则校验（仅匹配 '+ N Checkers' 模式）。"""
    if not ARCHITECTURE.exists():
        return None
    content = ARCHITECTURE.read_text(encoding="utf-8")
    # 匹配形如 "+ 16 Checkers" / "+ 10 Checkers"（容忍空格与加号/中文加）
    m = re.search(r"[+＋]\s*(\d+)\s*(?:Checker|checker|个Checker)", content)
    if not m:
        return None
    claim = int(m.group(1))
    actual = count_files(AGENTS_DIR, "*-checker.md")
    if not (1 <= claim <= 30):
        return None
    return Finding("architecture.md", f"{claim} Checkers", f"{actual}", claim == actual)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="仅打印实测值，不校验")
    args = parser.parse_args()

    findings: list[Finding] = []
    findings.append(check_readme_templates())
    findings.append(check_topology_agents())
    arch = check_architecture_checkers()
    if arch is not None:
        findings.append(arch)
    findings.extend(check_chapter_lock_consistency())
    findings.extend(check_no_data_modules_imports())
    findings.extend(check_skill_frontmatter())
    findings.extend(check_agent_frontmatter())

    if args.report:
        print("=== Docs numbers report ===")
        for f in findings:
            print(f.render())
        return 0

    print("=== verify_docs.py ===")
    failures = [f for f in findings if not f.ok]
    for f in findings:
        print(f.render())
    print(f"\nSummary: {len(findings) - len(failures)}/{len(findings)} ok, {len(failures)} drift")
    if failures:
        print("\n❌ Docs-code drift detected. Fix claims above or adjust verify_docs.py.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
