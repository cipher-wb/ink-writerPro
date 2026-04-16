#!/usr/bin/env python3
"""
audit_architecture.py - 架构静态扫描脚本

扫描 ink-writer 项目的架构健康度：
  1. Python import 循环依赖检测
  2. 未被引用的模块（dead code 候选）
  3. Agent IO 契约表 + 职责重叠检测
  4. Prompt 重复片段（>30 token n-gram）

输出 Markdown 报告到 reports/architecture_audit.md。
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

PYTHON_PACKAGES = [
    PROJECT_ROOT / "ink_writer",
    PROJECT_ROOT / "ink-writer" / "scripts",
]

AGENT_DIRS = [
    PROJECT_ROOT / "ink-writer" / "agents",
]

NGRAM_SIZE = 6
MIN_NGRAM_TOKENS = 30
OVERLAP_THRESHOLD = 0.35


# ---------------------------------------------------------------------------
# 1. Import cycle detection (pure-Python DFS on AST)
# ---------------------------------------------------------------------------

def _collect_python_files(roots: list[Path]) -> list[Path]:
    files = []
    for root in roots:
        if root.is_dir():
            files.extend(sorted(root.rglob("*.py")))
    return files


def _module_name_from_path(py_file: Path, roots: list[Path]) -> str | None:
    for root in roots:
        try:
            rel = py_file.relative_to(root)
        except ValueError:
            continue
        parts = list(rel.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts) if parts else None
    return None


def _extract_imports(py_file: Path) -> list[str]:
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    except (SyntaxError, UnicodeDecodeError):
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def build_import_graph(roots: list[Path]) -> tuple[dict[str, set[str]], dict[str, Path]]:
    files = _collect_python_files(roots)
    known_modules: dict[str, Path] = {}
    for f in files:
        name = _module_name_from_path(f, roots)
        if name:
            known_modules[name] = f

    graph: dict[str, set[str]] = defaultdict(set)
    for mod, path in known_modules.items():
        raw_imports = _extract_imports(path)
        for imp in raw_imports:
            target = imp
            while target and target not in known_modules:
                target = target.rsplit(".", 1)[0] if "." in target else ""
            if target and target in known_modules and target != mod:
                graph[mod].add(target)

    return dict(graph), known_modules


def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = defaultdict(int)
    path: list[str] = []
    cycles: list[list[str]] = []

    def dfs(node: str) -> None:
        color[node] = GRAY
        path.append(node)
        for neighbor in graph.get(node, []):
            if color[neighbor] == GRAY:
                idx = path.index(neighbor)
                cycle = path[idx:] + [neighbor]
                cycles.append(cycle)
            elif color[neighbor] == WHITE:
                dfs(neighbor)
        path.pop()
        color[node] = BLACK

    all_nodes = set(graph.keys())
    for targets in graph.values():
        all_nodes.update(targets)
    for node in sorted(all_nodes):
        if color[node] == WHITE:
            dfs(node)

    seen: set[tuple[str, ...]] = set()
    unique: list[list[str]] = []
    for c in cycles:
        key = tuple(sorted(c[:-1]))
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


# ---------------------------------------------------------------------------
# 2. Unused modules (dead code candidates)
# ---------------------------------------------------------------------------

def find_unused_modules(
    graph: dict[str, set[str]], known_modules: dict[str, Path]
) -> list[str]:
    imported_anywhere: set[str] = set()
    for targets in graph.values():
        imported_anywhere.update(targets)

    unused = []
    for mod in sorted(known_modules):
        if mod in imported_anywhere:
            continue
        if mod.endswith("__init__"):
            continue
        path = known_modules[mod]
        if path.name.startswith("test_"):
            continue
        unused.append(mod)
    return unused


# ---------------------------------------------------------------------------
# 3. Agent IO contract parsing
# ---------------------------------------------------------------------------

def _parse_agent_frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            fm[key.strip()] = val.strip().strip("[]\"'")
    return fm


def _extract_section(text: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\b.*?\n(.*?)(?=\n##\s|\Z)"
    m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _extract_io_section(text: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\b.*?\n(.*?)(?=\n##\s|\Z)"
    m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if m:
        return m.group(1).strip()
    pattern2 = rf"^##\s+.*{re.escape(heading)}.*\n(.*?)(?=\n##\s|\Z)"
    m2 = re.search(pattern2, text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return m2.group(1).strip() if m2 else ""


def parse_agents(agent_dirs: list[Path]) -> list[dict[str, Any]]:
    agents = []
    for d in agent_dirs:
        if not d.is_dir():
            continue
        for md in sorted(d.glob("*.md")):
            text = md.read_text(encoding="utf-8")
            fm = _parse_agent_frontmatter(text)
            inputs = _extract_io_section(text, "输入") or _extract_io_section(text, "Input")
            outputs = _extract_io_section(text, "输出格式") or _extract_io_section(text, "输出") or _extract_io_section(text, "Output")
            agents.append({
                "file": str(md),
                "name": fm.get("name", md.stem),
                "description": fm.get("description", ""),
                "tools": fm.get("tools", ""),
                "inputs_raw": inputs,
                "outputs_raw": outputs,
                "full_text": text,
                "dir": str(d),
            })
    return agents


_TEMPLATE_REF_RE = re.compile(r"\{\{PROMPT_TEMPLATE:[^}]+\}\}")


def _tokenize_simple(text: str) -> list[str]:
    return re.findall(r"[\w\u4e00-\u9fff]+", text.lower())


def _strip_template_refs(text: str) -> str:
    return _TEMPLATE_REF_RE.sub("", text)


def detect_agent_overlaps(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    overlaps = []
    for i in range(len(agents)):
        for j in range(i + 1, len(agents)):
            a, b = agents[i], agents[j]
            tokens_a = set(_tokenize_simple(a["description"]))
            tokens_b = set(_tokenize_simple(b["description"]))
            if not tokens_a or not tokens_b:
                continue
            intersection = tokens_a & tokens_b
            smaller = min(len(tokens_a), len(tokens_b))
            ratio = len(intersection) / smaller if smaller else 0
            if ratio >= OVERLAP_THRESHOLD:
                overlaps.append({
                    "agent_a": a["name"],
                    "agent_b": b["name"],
                    "overlap_ratio": round(ratio, 3),
                    "shared_terms": sorted(intersection),
                })
    return overlaps


# ---------------------------------------------------------------------------
# 4. Prompt repeated fragments (n-gram dedup)
# ---------------------------------------------------------------------------

def find_repeated_prompt_fragments(
    agents: list[dict[str, Any]], ngram_size: int = NGRAM_SIZE
) -> list[dict[str, Any]]:
    ngram_sources: dict[tuple[str, ...], list[str]] = defaultdict(list)

    for agent in agents:
        tokens = _tokenize_simple(_strip_template_refs(agent["full_text"]))
        seen_in_agent: set[tuple[str, ...]] = set()
        for k in range(len(tokens) - ngram_size + 1):
            ngram = tuple(tokens[k : k + ngram_size])
            if ngram not in seen_in_agent:
                seen_in_agent.add(ngram)
                ngram_sources[ngram].append(agent["name"])

    duplicates = []
    seen_ngram_groups: set[tuple[str, ...]] = set()
    for ngram, sources in sorted(ngram_sources.items(), key=lambda x: -len(x[1])):
        if len(sources) < 2:
            continue
        key = tuple(sorted(sources))
        if key in seen_ngram_groups:
            already = any(
                d["agents"] == sorted(sources) and
                any(tok in d["fragment"] for tok in ngram[:3])
                for d in duplicates
            )
            if already:
                continue
        seen_ngram_groups.add(key)
        duplicates.append({
            "fragment": " ".join(ngram),
            "agents": sorted(sources),
            "count": len(sources),
        })

    duplicates.sort(key=lambda x: -x["count"])
    return duplicates[:50]


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    cycles: list[list[str]],
    unused: list[str],
    agents: list[dict[str, Any]],
    overlaps: list[dict[str, Any]],
    prompt_dupes: list[dict[str, Any]],
    known_modules: dict[str, Path],
) -> str:
    lines: list[str] = []
    lines.append("# Architecture Audit Report")
    lines.append("")
    lines.append(f"> Generated by `scripts/audit_architecture.py`")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Python modules scanned**: {len(known_modules)}")
    lines.append(f"- **Import cycles found**: {len(cycles)}")
    lines.append(f"- **Unused module candidates**: {len(unused)}")
    lines.append(f"- **Agents scanned**: {len(agents)}")
    lines.append(f"- **Agent overlap pairs**: {len(overlaps)}")
    lines.append(f"- **Repeated prompt fragments**: {len(prompt_dupes)}")
    lines.append("")

    # Cycles
    lines.append("## 1. Import Cycles")
    lines.append("")
    if cycles:
        for i, cycle in enumerate(cycles, 1):
            lines.append(f"{i}. `{'` → `'.join(cycle)}`")
    else:
        lines.append("No import cycles detected. ✓")
    lines.append("")

    # Unused
    lines.append("## 2. Unused Module Candidates")
    lines.append("")
    if unused:
        for mod in unused:
            path = known_modules.get(mod)
            lines.append(f"- `{mod}` ({path})")
    else:
        lines.append("No unused modules detected. ✓")
    lines.append("")

    # Agent IO Contract Table
    lines.append("## 3. Agent IO Contract Table")
    lines.append("")
    lines.append("| Agent | Description | Tools | Inputs | Outputs |")
    lines.append("|-------|-------------|-------|--------|---------|")
    for a in agents:
        desc = a["description"][:60] + "…" if len(a["description"]) > 60 else a["description"]
        inputs_summary = a["inputs_raw"][:50].replace("\n", " ").replace("|", "\\|") + "…" if len(a["inputs_raw"]) > 50 else a["inputs_raw"].replace("\n", " ").replace("|", "\\|")
        outputs_summary = a["outputs_raw"][:50].replace("\n", " ").replace("|", "\\|") + "…" if len(a["outputs_raw"]) > 50 else a["outputs_raw"].replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {a['name']} | {desc} | {a['tools']} | {inputs_summary} | {outputs_summary} |")
    lines.append("")

    # Overlaps
    lines.append("## 4. Agent Responsibility Overlaps")
    lines.append("")
    if overlaps:
        for ov in overlaps:
            lines.append(f"- **{ov['agent_a']}** ↔ **{ov['agent_b']}** (overlap ratio: {ov['overlap_ratio']})")
            lines.append(f"  Shared terms: {', '.join(ov['shared_terms'][:10])}")
    else:
        lines.append("No significant agent overlaps detected. ✓")
    lines.append("")

    # Prompt dupes
    lines.append("## 5. Repeated Prompt Fragments")
    lines.append("")
    if prompt_dupes:
        lines.append("Fragments appearing in 2+ agent specs (top 50):")
        lines.append("")
        for d in prompt_dupes:
            lines.append(f"- **{d['count']}x** in [{', '.join(d['agents'])}]: `{d['fragment']}`")
    else:
        lines.append("No repeated prompt fragments detected. ✓")
    lines.append("")

    return "\n".join(lines)


def run_audit(
    project_root: Path,
    python_packages: list[Path] | None = None,
    agent_dirs: list[Path] | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    if python_packages is None:
        python_packages = [
            project_root / "ink_writer",
            project_root / "ink-writer" / "scripts",
        ]
    if agent_dirs is None:
        agent_dirs = [
            project_root / "ink-writer" / "agents",
        ]
    if output_path is None:
        output_path = project_root / "reports" / "architecture_audit.md"

    graph, known_modules = build_import_graph(python_packages)
    cycles = find_cycles(graph)
    unused = find_unused_modules(graph, known_modules)

    agents = parse_agents(agent_dirs)
    overlaps = detect_agent_overlaps(agents)
    prompt_dupes = find_repeated_prompt_fragments(agents)

    report = generate_report(cycles, unused, agents, overlaps, prompt_dupes, known_modules)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    return {
        "cycles": cycles,
        "unused_modules": unused,
        "agents": [
            {"name": a["name"], "description": a["description"], "tools": a["tools"]}
            for a in agents
        ],
        "overlaps": overlaps,
        "prompt_duplicates": prompt_dupes,
        "modules_scanned": len(known_modules),
        "report_path": str(output_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Architecture audit for ink-writer")
    parser.add_argument(
        "--project-root", type=Path, default=PROJECT_ROOT,
        help="Project root directory",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output report path (default: reports/architecture_audit.md)",
    )
    args = parser.parse_args()

    result = run_audit(args.project_root, output_path=args.output)

    print(f"Modules scanned: {result['modules_scanned']}")
    print(f"Import cycles: {len(result['cycles'])}")
    print(f"Unused modules: {len(result['unused_modules'])}")
    print(f"Agents scanned: {len(result['agents'])}")
    print(f"Agent overlaps: {len(result['overlaps'])}")
    print(f"Prompt duplicates: {len(result['prompt_duplicates'])}")
    print(f"Report written to: {result['report_path']}")


if __name__ == "__main__":
    main()
