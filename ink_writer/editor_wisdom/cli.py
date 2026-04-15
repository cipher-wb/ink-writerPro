"""CLI subcommands for editor-wisdom: rebuild, query, stats."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "editor-wisdom"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "editor-wisdom"

PIPELINE_STEPS = [
    ("01_scan.py", "扫描数据源"),
    ("02_clean.py", "去重与噪音过滤"),
    ("03_classify.py", "主题分类"),
    ("04_build_kb.py", "生成知识库"),
    ("05_extract_rules.py", "抽取规则"),
    ("06_build_index.py", "构建向量索引"),
]


def cmd_rebuild(from_step: int = 1) -> int:
    """Run scripts 01..06 in order. Exit non-zero on any step failure.

    Args:
        from_step: Start from this step number (1..6). Steps before this are skipped.
    """
    if from_step < 1 or from_step > len(PIPELINE_STEPS):
        print(f"✗ --from-step 必须在 1..{len(PIPELINE_STEPS)} 之间，收到: {from_step}", file=sys.stderr)
        return 1

    steps = PIPELINE_STEPS[from_step - 1:]
    if from_step > 1:
        print(f"⏩ 跳过步骤 1..{from_step - 1}，从步骤 {from_step} 开始\n")

    for script_name, label in steps:
        script_path = SCRIPTS_DIR / script_name
        if not script_path.exists():
            print(f"✗ 脚本不存在: {script_path}", file=sys.stderr)
            return 1
        print(f"▶ [{script_name}] {label} ...")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(SCRIPTS_DIR.parent.parent),
        )
        if result.returncode != 0:
            print(f"✗ [{script_name}] 失败 (exit {result.returncode})", file=sys.stderr)
            return result.returncode
        print(f"✓ [{script_name}] 完成")
    print("\n✓ 全部步骤执行完毕")
    return 0


def cmd_query(query_text: str, top_k: int = 5) -> int:
    """Print top-K rules matching a query string."""
    try:
        from ink_writer.editor_wisdom.retriever import Retriever
    except ImportError as e:
        print(f"✗ 无法加载 retriever: {e}", file=sys.stderr)
        print("  请先运行 `ink editor-wisdom rebuild` 构建索引", file=sys.stderr)
        return 1

    index_dir = DATA_DIR / "vector_index"
    if not index_dir.exists():
        print("✗ 向量索引不存在，请先运行 `ink editor-wisdom rebuild`", file=sys.stderr)
        return 1

    retriever = Retriever(index_dir=index_dir)
    rules = retriever.retrieve(query=query_text, k=top_k)

    if not rules:
        print("未找到匹配的规则。")
        return 0

    print(f"查询: \"{query_text}\"  (top {top_k})\n")
    for i, r in enumerate(rules, 1):
        print(f"  {i}. [{r.id}] [{r.category}] [{r.severity}]")
        print(f"     {r.rule}")
        print()
    return 0


def cmd_stats() -> int:
    """Print rule stats: total, category distribution, indexed count, last rebuild."""
    rules_path = DATA_DIR / "rules.json"
    if not rules_path.exists():
        print("✗ rules.json 不存在，请先运行 `ink editor-wisdom rebuild`", file=sys.stderr)
        return 1

    rules: list[dict] = json.loads(rules_path.read_text(encoding="utf-8"))
    total = len(rules)

    cats: dict[str, int] = {}
    for r in rules:
        cat = r.get("category", "unknown")
        cats[cat] = cats.get(cat, 0) + 1

    index_dir = DATA_DIR / "vector_index"
    metadata_path = index_dir / "metadata.json"
    if metadata_path.exists():
        indexed = len(json.loads(metadata_path.read_text(encoding="utf-8")))
    else:
        indexed = 0

    faiss_path = index_dir / "rules.faiss"
    if faiss_path.exists():
        mtime = faiss_path.stat().st_mtime
        last_rebuild = datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    elif rules_path.exists():
        mtime = rules_path.stat().st_mtime
        last_rebuild = datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        last_rebuild = "未知"

    print(f"规则总数:       {total}")
    print(f"索引文档数:     {indexed}")
    print(f"上次构建时间:   {last_rebuild}")
    print("\n分类分布:")
    for cat in sorted(cats.keys()):
        print(f"  {cat:20s} {cats[cat]:4d}")

    return 0
