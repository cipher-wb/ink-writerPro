"""US-008 深度健康审计：死代码与未使用资源扫描。

扫描范围：
1. ink_writer/ Python 模块的导入关系（AST）
2. ink-writer/references/ *.md 引用情况
3. data/ 文件引用情况
4. ink-writer/agents/ 引用情况
5. archive/ 和 docs/archive/ 路径清点 + 大小统计

只读审计，不修改源码。
复现方式：
    python3 scripts/audit/scan_unused.py           # 标准扫描，打印报告摘要
    python3 scripts/audit/scan_unused.py --json    # 输出 JSON 给下游消费
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

# ----------------------------------------------------------------------
# 路径配置
# ----------------------------------------------------------------------

PROJECT_ROOT = Path("/Users/cipher/AI/ink/ink-writer")
INK_WRITER_PKG = PROJECT_ROOT / "ink_writer"           # python 包
AGENTS_DIR = PROJECT_ROOT / "ink-writer" / "agents"    # agent 规格目录
REFERENCES_DIR = PROJECT_ROOT / "ink-writer" / "references"
SKILLS_DIR = PROJECT_ROOT / "ink-writer" / "skills"
DATA_DIR = PROJECT_ROOT / "data"
ARCHIVE_DIR = PROJECT_ROOT / "archive"
DOCS_ARCHIVE_DIR = PROJECT_ROOT / "docs" / "archive"
DOCS_DIR = PROJECT_ROOT / "docs"

# 搜索根（查找引用时）
SEARCH_ROOTS = [
    PROJECT_ROOT / "ink_writer",
    PROJECT_ROOT / "ink-writer",
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "tests",
    PROJECT_ROOT / "config",
    PROJECT_ROOT / "schemas",
    PROJECT_ROOT / "tasks",
    PROJECT_ROOT / "reports",
    PROJECT_ROOT / ".codex",
    PROJECT_ROOT / ".github",
    DOCS_DIR,
]

# 根目录下零散但不可忽略的文件
EXTRA_ROOT_FILES = [
    "README.md", "CLAUDE.md", "GEMINI.md", "AGENTS.md", "prd.json",
    "progress.txt", "pyproject.toml", "pytest.ini",
    "requirements.txt", "gemini-extension.json",
]

# 扫描时忽略的目录
IGNORED_DIR_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".git",
    ".DS_Store",
    ".ink",
    "archive",          # 不深入搜索归档目录
    "docs/archive",
}


def _is_ignored(path: Path) -> bool:
    parts = set(path.parts)
    if parts & IGNORED_DIR_PARTS:
        return True
    if path.name == ".DS_Store":
        return True
    # 跳过 docs/archive
    try:
        rel = path.resolve().relative_to(PROJECT_ROOT.resolve())
        if str(rel).startswith("docs/archive"):
            return True
        if str(rel).startswith("archive/"):
            return True
    except ValueError:
        pass
    return False


# ----------------------------------------------------------------------
# (1) Python 死代码扫描（AST）
# ----------------------------------------------------------------------

@dataclass
class PyModuleInfo:
    path: Path
    dotted: str                           # ink_writer.foo.bar
    imports: Set[str] = field(default_factory=set)
    imports_by: Set[str] = field(default_factory=set)  # 被谁导入
    defined_funcs: Set[str] = field(default_factory=set)
    called_names: Set[str] = field(default_factory=set)


def iter_python_files(root: Path):
    for p in root.rglob("*.py"):
        if _is_ignored(p):
            continue
        yield p


def module_dotted(pyfile: Path, pkg_root: Path) -> str:
    rel = pyfile.relative_to(pkg_root.parent)
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def parse_py_module(pyfile: Path, pkg_root: Path) -> PyModuleInfo:
    info = PyModuleInfo(path=pyfile, dotted=module_dotted(pyfile, pkg_root))
    try:
        tree = ast.parse(pyfile.read_text(encoding="utf-8"))
    except Exception as exc:  # 语法错误就跳过，不影响整体扫描
        return info

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                info.imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                # 补齐相对导入
                if node.level and node.level > 0:
                    # 相对导入，拼当前包
                    parent_parts = info.dotted.split(".")
                    base = ".".join(parent_parts[: -node.level])
                    full = f"{base}.{node.module}" if base else node.module
                else:
                    full = node.module
                info.imports.add(full)
                for alias in node.names:
                    info.imports.add(f"{full}.{alias.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # 仅收集顶层函数（避免嵌套函数噪声）
            # 粗略判断：通过遍历树时，外层的 FunctionDef 一定会出现在 body 里
            info.defined_funcs.add(node.name)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                info.called_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                info.called_names.add(func.attr)
        elif isinstance(node, ast.Attribute):
            # 属性访问（property 装饰的方法）也算被使用
            info.called_names.add(node.attr)
        elif isinstance(node, ast.Name):
            # 裸名字引用（例如作为参数传递）
            info.called_names.add(node.id)
    return info


def scan_python_dead_code(pkg_root: Path) -> Tuple[Dict[str, PyModuleInfo], List[str], List[Tuple[str, str]]]:
    """返回 (模块表, 未被 import 的模块列表, (模块, 未被调用函数) 列表)。"""
    modules: Dict[str, PyModuleInfo] = {}
    for pyfile in iter_python_files(pkg_root):
        info = parse_py_module(pyfile, pkg_root)
        modules[info.dotted] = info

    # 所有已知的 dotted 名 + 其所有前缀
    known_dotted = set(modules.keys())

    # 构建 imports_by
    for caller_name, info in modules.items():
        for imp in info.imports:
            # 某模块 foo.bar.Baz 也可能命中 foo.bar
            for cand in (imp, imp.rsplit(".", 1)[0]):
                if cand in known_dotted and cand != caller_name:
                    modules[cand].imports_by.add(caller_name)

    # 额外在非包代码（scripts/, tests/, ink-writer/scripts/）里搜索 ink_writer.xxx
    extra_importers = defaultdict(set)
    for root in SEARCH_ROOTS:
        if root == pkg_root:
            continue
        if not root.exists():
            continue
        for pyfile in iter_python_files(root):
            try:
                src = pyfile.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for dotted in known_dotted:
                # 匹配 import ink_writer.xxx / from ink_writer.xxx import ...
                patt = r"\b" + re.escape(dotted) + r"\b"
                if re.search(patt, src):
                    extra_importers[dotted].add(str(pyfile.relative_to(PROJECT_ROOT)))

    # unused modules：既不在内部 imports_by，又不被外部代码引用
    # 排除 __init__（常作为包挂载点）
    unused_modules: List[str] = []
    for name, info in modules.items():
        if name.endswith("__init__") or name == "ink_writer":
            continue
        if info.imports_by:
            continue
        if extra_importers.get(name):
            continue
        # 纯顶层包入口也排除：ink_writer.xxx（只有一个层级且有子模块），避免误伤
        unused_modules.append(name)

    # 未被调用的函数：只看本包内是否出现其名字
    # 粗略：收集所有模块里 called_names 的并集，函数名不在其中 = 未调用
    all_called = set()
    for info in modules.values():
        all_called |= info.called_names

    unused_funcs: List[Tuple[str, str]] = []
    for name, info in modules.items():
        for fn in info.defined_funcs:
            if fn.startswith("_"):
                continue          # 私有函数容忍
            if fn in {"main", "run", "handle", "cli"}:
                continue          # 常见入口
            if fn in all_called:
                continue
            # 再到非包代码里 grep 一次，避免 CLI 调用没被识别
            hit = False
            patt = r"\b" + re.escape(fn) + r"\b"
            for root in SEARCH_ROOTS:
                if not root.exists():
                    continue
                for pyfile in iter_python_files(root):
                    if pyfile == info.path:
                        continue
                    try:
                        if re.search(patt, pyfile.read_text(encoding="utf-8", errors="ignore")):
                            hit = True
                            break
                    except Exception:
                        continue
                if hit:
                    break
            if not hit:
                unused_funcs.append((name, fn))
    return modules, unused_modules, unused_funcs


# ----------------------------------------------------------------------
# (2) references/ 文件引用情况
# ----------------------------------------------------------------------

@dataclass
class RefCheckResult:
    path: str
    size_bytes: int
    referenced_by_code: List[str] = field(default_factory=list)
    referenced_by_docs: List[str] = field(default_factory=list)
    status: str = "unreferenced"  # code / docs / unreferenced


def collect_text_files() -> List[Path]:
    """收集所有可能包含引用的文本文件（py/md/sh/json/yaml/toml/ini/txt）。

    注意：会排除本报告（`docs/audit/08-unused-resources.md`）避免自指。
    """
    exts = {".py", ".md", ".sh", ".json", ".yaml", ".yml", ".toml", ".ini", ".txt", ".bash", ".zsh"}
    self_report = (PROJECT_ROOT / "docs" / "audit" / "08-unused-resources.md").resolve()
    result: List[Path] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in exts and not _is_ignored(p):
                if p.resolve() == self_report:
                    continue
                result.append(p)
    for name in EXTRA_ROOT_FILES:
        p = PROJECT_ROOT / name
        if p.exists() and p.is_file():
            result.append(p)
    return result


def scan_refs_references(text_files: List[Path]) -> List[RefCheckResult]:
    results: List[RefCheckResult] = []
    md_files = sorted(p for p in REFERENCES_DIR.rglob("*.md") if not _is_ignored(p))
    # 缓存文本文件内容，避免反复读盘
    cache: Dict[Path, str] = {}
    for f in text_files:
        try:
            cache[f] = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            cache[f] = ""

    for md in md_files:
        rel = md.relative_to(PROJECT_ROOT)
        name = md.name
        patt_path = str(rel)
        patt_name = name

        code_hits: List[str] = []   # py 或 skills/agents 规格（运行时实际加载）
        doc_hits: List[str] = []    # 仅文档提及（docs/ 或 tasks/ 等）
        for f, src in cache.items():
            if f == md:
                continue
            if patt_path in src or patt_name in src:
                rel_f = str(f.relative_to(PROJECT_ROOT))
                if (f.suffix == ".py"
                        or rel_f.startswith("ink_writer/")
                        or rel_f.startswith("scripts/")
                        or "/skills/" in rel_f
                        or "/agents/" in rel_f):
                    code_hits.append(rel_f)
                else:
                    doc_hits.append(rel_f)
        status = "code" if code_hits else ("docs" if doc_hits else "unreferenced")
        results.append(RefCheckResult(
            path=str(rel),
            size_bytes=md.stat().st_size,
            referenced_by_code=code_hits[:5],
            referenced_by_docs=doc_hits[:5],
            status=status,
        ))
    return results


# ----------------------------------------------------------------------
# (3) data/ 文件引用情况
# ----------------------------------------------------------------------

def scan_refs_data(text_files: List[Path]) -> List[RefCheckResult]:
    """扫描 data/ 下每个文件的引用情况。

    补充规则：对于 data/xxx/ 目录下的文件，若代码中引用了父目录（例如 DEFAULT_DATA_DIR），
    且 stem 被用作 genre/category 枚举值，也视为 code 引用（避免误报）。
    """
    results: List[RefCheckResult] = []
    data_files = []
    for p in DATA_DIR.rglob("*"):
        if p.is_file() and not _is_ignored(p):
            data_files.append(p)
    data_files.sort()

    cache: Dict[Path, str] = {}
    for f in text_files:
        try:
            cache[f] = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            cache[f] = ""

    # 预先找出"哪些代码文件引用了 data/XXX/ 目录"
    dir_refs: Dict[str, List[str]] = defaultdict(list)
    for f, src in cache.items():
        if f.suffix != ".py":
            continue
        rel_f = str(f.relative_to(PROJECT_ROOT))
        for d in DATA_DIR.iterdir():
            if d.is_dir():
                # 代码中出现 "data" / "XXX" 或 'XXX' 紧跟 .json 等动态加载模式
                sub = d.name
                # 两种匹配：字符串 'XXX' 出现 + 动态加载模式 f"{...}.json"
                if f'"{sub}"' in src or f"'{sub}'" in src or f'"data" / "{sub}"' in src:
                    dir_refs[sub].append(rel_f)

    # 一些过于通用的文件名不能用 name 来查引用，以免产生大量假阳性
    generic_names = {"README.md", "readme.md", "INDEX.md", "__init__.py", "config.json"}

    for df in data_files:
        rel = df.relative_to(PROJECT_ROOT)
        name = df.name
        stem = df.stem
        patt_path = str(rel)
        patt_rel_data = str(df.relative_to(DATA_DIR))  # e.g. naming/surnames.json
        patt_name = name
        parent_name = df.parent.name                   # e.g. cultural_lexicon

        code_hits: List[str] = []
        doc_hits: List[str] = []
        for f, src in cache.items():
            if f == df:
                continue
            # 对通用文件名只匹配完整路径或带父目录的相对路径，避免误匹配
            if name in generic_names:
                matched = (patt_path in src) or (patt_rel_data in src)
            else:
                matched = (patt_path in src) or (patt_rel_data in src) or (patt_name in src)
            if matched:
                rel_f = str(f.relative_to(PROJECT_ROOT))
                if f.suffix == ".py":
                    code_hits.append(rel_f)
                else:
                    doc_hits.append(rel_f)

        # 补救：父目录被代码引用 + stem 出现在代码字符串中 = 动态加载
        # 跳过对过于通用的文件名（README、__init__ 等）应用此规则
        generic_stems = {"README", "readme", "INDEX", "index", "TODO", "CHANGELOG"}
        if not code_hits and parent_name in dir_refs and stem not in generic_stems:
            # 再查 stem 是否作为字符串出现在任一代码文件中
            stem_patt = [f'"{stem}"', f"'{stem}'"]
            for f, src in cache.items():
                if f.suffix != ".py":
                    continue
                if any(sp in src for sp in stem_patt):
                    code_hits.append(f"{str(f.relative_to(PROJECT_ROOT))} [dynamic-load]")
                    break

        status = "code" if code_hits else ("docs" if doc_hits else "unreferenced")
        results.append(RefCheckResult(
            path=str(rel),
            size_bytes=df.stat().st_size,
            referenced_by_code=code_hits[:5],
            referenced_by_docs=doc_hits[:5],
            status=status,
        ))
    return results


# ----------------------------------------------------------------------
# (4) agent 规格扫描
# ----------------------------------------------------------------------

@dataclass
class AgentRefResult:
    path: str
    agent_name: str
    size_bytes: int
    referenced_in_skills: List[str] = field(default_factory=list)
    referenced_in_python: List[str] = field(default_factory=list)
    referenced_in_docs: List[str] = field(default_factory=list)
    status: str = "unreferenced"


def scan_refs_agents() -> List[AgentRefResult]:
    results: List[AgentRefResult] = []
    agents = sorted(AGENTS_DIR.glob("*.md"))

    # 收集 skills/ 和 checker_pipeline/ 下的文件
    target_files: List[Path] = []
    if SKILLS_DIR.exists():
        target_files.extend(p for p in SKILLS_DIR.rglob("*") if p.is_file())
    if (INK_WRITER_PKG / "checker_pipeline").exists():
        target_files.extend(p for p in (INK_WRITER_PKG / "checker_pipeline").rglob("*.py") if p.is_file())
    # 全包 py 也要扫一遍，agent 名可能被 pipeline 直接引用
    target_files.extend(iter_python_files(INK_WRITER_PKG))
    target_files.extend(p for p in DOCS_DIR.rglob("*.md") if not _is_ignored(p))
    # 去重
    target_files = list({p.resolve(): p for p in target_files}.values())

    cache: Dict[Path, str] = {}
    for f in target_files:
        try:
            cache[f] = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            cache[f] = ""

    for agent in agents:
        rel = agent.relative_to(PROJECT_ROOT)
        stem = agent.stem                          # e.g. writer-agent
        patterns = [agent.name, stem]
        # stem 短的可能歧义，至少要 4 字符
        if len(stem) < 4:
            patterns = [agent.name]

        skills_hits: List[str] = []
        py_hits: List[str] = []
        doc_hits: List[str] = []
        for f, src in cache.items():
            if f == agent:
                continue
            for patt in patterns:
                if patt in src:
                    rel_f = str(f.relative_to(PROJECT_ROOT))
                    if "/skills/" in rel_f or rel_f.startswith("ink-writer/skills/"):
                        skills_hits.append(rel_f)
                    elif f.suffix == ".py":
                        py_hits.append(rel_f)
                    else:
                        doc_hits.append(rel_f)
                    break

        if skills_hits or py_hits:
            status = "code"
        elif doc_hits:
            status = "docs"
        else:
            status = "unreferenced"

        results.append(AgentRefResult(
            path=str(rel),
            agent_name=stem,
            size_bytes=agent.stat().st_size,
            referenced_in_skills=list(dict.fromkeys(skills_hits))[:5],
            referenced_in_python=list(dict.fromkeys(py_hits))[:5],
            referenced_in_docs=list(dict.fromkeys(doc_hits))[:5],
            status=status,
        ))
    return results


# ----------------------------------------------------------------------
# (5) archive/ 和 docs/archive/ 清点
# ----------------------------------------------------------------------

def tally_archive(root: Path) -> Tuple[int, int, List[Tuple[str, int]]]:
    """返回 (总大小, 文件数, [(路径, 字节)])。"""
    total = 0
    items: List[Tuple[str, int]] = []
    if not root.exists():
        return 0, 0, []
    for p in root.rglob("*"):
        if p.is_file() and p.name != ".DS_Store":
            size = p.stat().st_size
            total += size
            items.append((str(p.relative_to(PROJECT_ROOT)), size))
    return total, len(items), sorted(items)


# 旧的 engineering-review-report.md 家族
LEGACY_REPORTS = [
    "docs/engineering-review-report.md",
    "docs/engineering-review-report-v2.md",
    "docs/engineering-review-report-v3.md",
    "docs/engineering-review-report-v4.md",
]


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------

def fmt_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.2f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def build_report() -> Dict:
    modules, unused_mods, unused_funcs = scan_python_dead_code(INK_WRITER_PKG)
    text_files = collect_text_files()
    refs_results = scan_refs_references(text_files)
    data_results = scan_refs_data(text_files)
    agent_results = scan_refs_agents()

    arch_total, arch_count, arch_items = tally_archive(ARCHIVE_DIR)
    docs_arch_total, docs_arch_count, docs_arch_items = tally_archive(DOCS_ARCHIVE_DIR)

    legacy_reports = []
    legacy_total = 0
    for rel in LEGACY_REPORTS:
        p = PROJECT_ROOT / rel
        if p.exists():
            legacy_reports.append((rel, p.stat().st_size))
            legacy_total += p.stat().st_size

    return {
        "python": {
            "total_modules": len(modules),
            "unused_modules": unused_mods,
            "unused_functions": unused_funcs,
        },
        "references": [asdict(r) for r in refs_results],
        "data": [asdict(r) for r in data_results],
        "agents": [asdict(r) for r in agent_results],
        "archive": {
            "total_bytes": arch_total,
            "count": arch_count,
            "items": arch_items,
        },
        "docs_archive": {
            "total_bytes": docs_arch_total,
            "count": docs_arch_count,
            "items": docs_arch_items,
        },
        "legacy_reports": legacy_reports,
        "legacy_reports_total_bytes": legacy_total,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="打印完整 JSON，供 CI/后续工具消费")
    args = parser.parse_args()

    data = build_report()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return 0

    # 控制台简报
    print("=== US-008 死代码与未使用资源扫描 ===")
    print(f"Python 模块总数：{data['python']['total_modules']}")
    print(f"  未被导入的模块：{len(data['python']['unused_modules'])}")
    print(f"  未被调用的函数（启发式）：{len(data['python']['unused_functions'])}")
    print(f"references/ 文件数：{len(data['references'])}")
    for s in ("code", "docs", "unreferenced"):
        c = sum(1 for r in data["references"] if r["status"] == s)
        print(f"  {s}: {c}")
    print(f"data/ 文件数：{len(data['data'])}")
    for s in ("code", "docs", "unreferenced"):
        c = sum(1 for r in data["data"] if r["status"] == s)
        print(f"  {s}: {c}")
    print(f"agents/ 规格数：{len(data['agents'])}")
    for s in ("code", "docs", "unreferenced"):
        c = sum(1 for r in data["agents"] if r["status"] == s)
        print(f"  {s}: {c}")
    print(f"archive/ 共 {data['archive']['count']} 个文件，{fmt_size(data['archive']['total_bytes'])}")
    print(f"docs/archive/ 共 {data['docs_archive']['count']} 个文件，{fmt_size(data['docs_archive']['total_bytes'])}")
    print(f"legacy engineering reports: {len(data['legacy_reports'])}, {fmt_size(data['legacy_reports_total_bytes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
