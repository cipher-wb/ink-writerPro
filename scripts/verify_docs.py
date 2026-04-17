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
