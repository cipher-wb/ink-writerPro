#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迁移审计工具 (Migration Auditor)

三个子命令：
  discover     - Phase 1: 资产发现（只读扫描）
  create-tables - Phase 2.2: 创建 v9.0 新增的 index.db 表
  audit        - Phase 3: 迁移审计，生成报告

用法:
  python migration_auditor.py --project-root <path> discover
  python migration_auditor.py --project-root <path> create-tables
  python migration_auditor.py --project-root <path> audit
"""

from __future__ import annotations

# US-010: ensure Windows stdio is UTF-8 wrapped when launched directly.
import os as _os_win_stdio
import sys as _sys_win_stdio
_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    '.',
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:
    pass
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def _ink_dir(project_root: Path) -> Path:
    return project_root / ".ink"


def _state_path(project_root: Path) -> Path:
    return _ink_dir(project_root) / "state.json"


def _index_db_path(project_root: Path) -> Path:
    return _ink_dir(project_root) / "index.db"


# ---------------------------------------------------------------------------
# Phase 1: Asset Discovery
# ---------------------------------------------------------------------------

def discover_assets(project_root: Path) -> Dict[str, Any]:
    """扫描项目资产，返回资产清单"""
    ink = _ink_dir(project_root)
    assets: Dict[str, Any] = {
        "project_root": str(project_root),
        "scan_time": datetime.now().isoformat(),
    }

    # 1. state.json
    sp = _state_path(project_root)
    if sp.exists():
        with open(sp, "r", encoding="utf-8") as f:
            state = json.load(f)
        assets["state_json"] = {
            "exists": True,
            "schema_version": state.get("schema_version", 5),
            "current_chapter": state.get("progress", {}).get("current_chapter", 0),
        }
    else:
        assets["state_json"] = {"exists": False}

    # 2. index.db
    db = _index_db_path(project_root)
    if db.exists():
        tables = _list_tables(db)
        assets["index_db"] = {
            "exists": True,
            "table_count": len(tables),
            "tables": tables,
            "has_harness_evaluations": "harness_evaluations" in tables,
            "has_computational_gate_log": "computational_gate_log" in tables,
        }
    else:
        assets["index_db"] = {"exists": False}

    # 3. Chapter files
    chapter_dirs = ["正文", "chapters"]
    chapter_files: List[str] = []
    for d in chapter_dirs:
        cp = project_root / d
        if cp.is_dir():
            for f in sorted(cp.glob("*.md")):
                chapter_files.append(str(f.relative_to(project_root)))
    assets["chapters"] = {
        "count": len(chapter_files),
        "files": chapter_files[:10],  # 只列前10个
        "total_listed": min(len(chapter_files), 10),
    }

    # 4. Summaries
    summary_dir = ink / "summaries"
    if summary_dir.is_dir():
        summaries = list(summary_dir.glob("ch*.md"))
        assets["summaries"] = {
            "count": len(summaries),
            "coverage": f"{len(summaries)}/{len(chapter_files)}" if chapter_files else "N/A",
        }
    else:
        assets["summaries"] = {"count": 0, "coverage": "0/0"}

    # 5. Outlines
    outline_dirs = ["大纲", "outlines"]
    outline_count = 0
    for d in outline_dirs:
        op = project_root / d
        if op.is_dir():
            outline_count += sum(1 for _ in op.rglob("*.md"))
    assets["outlines"] = {"count": outline_count}

    # 6. Review reports
    review_dirs = ["审查报告", "review_reports"]
    review_count = 0
    for d in review_dirs:
        rp = project_root / d
        if rp.is_dir():
            review_count += sum(1 for _ in rp.glob("*.md"))
    assets["reviews"] = {"count": review_count}

    # 7. vectors.db
    assets["vectors_db"] = {"exists": (ink / "vectors.db").exists()}

    return assets


def _list_tables(db_path: Path) -> List[str]:
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tables
    except Exception:
        return []


def cmd_discover(project_root: Path) -> int:
    """Phase 1: 资产发现"""
    state_path = _state_path(project_root)
    if not state_path.exists():
        print("❌ state.json 不存在。请先运行 /ink-init 初始化项目。")
        return 1

    assets = discover_assets(project_root)

    # 检查是否已经是 v9.0
    schema_ver = assets.get("state_json", {}).get("schema_version", 5)
    if schema_ver >= 7:
        print(f"✅ 项目已是 v9.0 架构（schema v{schema_ver}），无需迁移。")
        return 0

    # 输出资产清单
    print("\n" + "=" * 50)
    print("  ink-migrate Phase 1: 资产发现")
    print("=" * 50)

    print(f"\n  项目路径: {project_root}")
    print(f"  Schema 版本: v{schema_ver} → 需要迁移到 v7")

    ch = assets.get("chapters", {})
    print(f"\n  章节文件: {ch.get('count', 0)} 个")

    sm = assets.get("summaries", {})
    print(f"  摘要覆盖: {sm.get('coverage', 'N/A')}")

    ol = assets.get("outlines", {})
    print(f"  大纲文件: {ol.get('count', 0)} 个")

    rv = assets.get("reviews", {})
    print(f"  审查报告: {rv.get('count', 0)} 个")

    db = assets.get("index_db", {})
    if db.get("exists"):
        print(f"  index.db: {db.get('table_count', 0)} 张表")
        print(f"    harness_evaluations: {'✅' if db.get('has_harness_evaluations') else '❌ 需创建'}")
        print(f"    computational_gate_log: {'✅' if db.get('has_computational_gate_log') else '❌ 需创建'}")
    else:
        print("  index.db: ❌ 不存在")

    vdb = assets.get("vectors_db", {})
    print(f"  vectors.db: {'✅' if vdb.get('exists') else '❌ 不存在'}")

    # 保存资产清单
    migration_dir = _ink_dir(project_root) / "migration"
    migration_dir.mkdir(parents=True, exist_ok=True)
    inv_path = migration_dir / "asset_inventory.json"
    with open(inv_path, "w", encoding="utf-8") as f:
        json.dump(assets, f, ensure_ascii=False, indent=2)
    print(f"\n  资产清单已保存: {inv_path}")
    print("=" * 50)

    return 0


# ---------------------------------------------------------------------------
# Phase 2.2: Create v9.0 Tables
# ---------------------------------------------------------------------------

HARNESS_EVALUATIONS_DDL = """
CREATE TABLE IF NOT EXISTS harness_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter INTEGER NOT NULL,
    hook_strength REAL,
    curiosity_continuation REAL,
    emotional_reward REAL,
    protagonist_pull REAL,
    cliffhanger_drive REAL,
    filler_risk REAL,
    repetition_risk REAL,
    total REAL,
    verdict TEXT,
    review_depth TEXT DEFAULT 'core',
    created_at TEXT DEFAULT (datetime('now'))
);
"""

COMPUTATIONAL_GATE_LOG_DDL = """
CREATE TABLE IF NOT EXISTS computational_gate_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter INTEGER NOT NULL,
    gate_pass INTEGER NOT NULL DEFAULT 1,
    checks_run INTEGER,
    checks_passed INTEGER,
    hard_failures TEXT,
    soft_warnings TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


def cmd_create_tables(project_root: Path) -> int:
    """Phase 2.2: 创建 v9.0 新增表"""
    db_path = _index_db_path(project_root)
    if not db_path.exists():
        print(f"❌ index.db 不存在: {db_path}")
        return 1

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(HARNESS_EVALUATIONS_DDL)
        cursor.execute(COMPUTATIONAL_GATE_LOG_DDL)
        conn.commit()
        conn.close()

        print("✅ v9.0 新表创建成功:")
        print("  - harness_evaluations")
        print("  - computational_gate_log")
        return 0

    except Exception as e:
        print(f"❌ 创建表失败: {e}")
        return 1


# ---------------------------------------------------------------------------
# Phase 3: Migration Audit
# ---------------------------------------------------------------------------

def cmd_audit(project_root: Path) -> int:
    """Phase 3: 迁移审计"""
    assets = discover_assets(project_root)
    state_path = _state_path(project_root)

    if not state_path.exists():
        print("❌ state.json 不存在，无法审计。")
        return 1

    with open(state_path, "r", encoding="utf-8") as f:
        state = json.load(f)

    schema_ver = state.get("schema_version", 5)

    # 审计项
    audit_results: List[Dict[str, Any]] = []

    # 1. Schema 版本
    audit_results.append({
        "item": "Schema 版本",
        "status": "pass" if schema_ver >= 7 else "fail",
        "detail": f"v{schema_ver}" + (" → 需要 v7" if schema_ver < 7 else " ✅"),
        "confidence": "high",
    })

    # 2. harness_config
    has_harness = "harness_config" in state
    audit_results.append({
        "item": "harness_config 字段",
        "status": "pass" if has_harness else "fail",
        "detail": "存在" if has_harness else "缺失",
        "confidence": "high",
    })

    # 3. index.db 新表
    db_info = assets.get("index_db", {})
    for table_name in ["harness_evaluations", "computational_gate_log"]:
        key = f"has_{table_name}"
        exists = db_info.get(key, False)
        audit_results.append({
            "item": f"index.db.{table_name}",
            "status": "pass" if exists else "fail",
            "detail": "存在" if exists else "需创建",
            "confidence": "high",
        })

    # 4. 章节完整性
    ch_count = assets.get("chapters", {}).get("count", 0)
    current_ch = state.get("progress", {}).get("current_chapter", 0)
    audit_results.append({
        "item": "章节文件完整性",
        "status": "pass" if ch_count >= current_ch else "warn",
        "detail": f"{ch_count}/{current_ch} 章",
        "confidence": "high" if ch_count >= current_ch else "medium",
    })

    # 5. 摘要覆盖
    sm_count = assets.get("summaries", {}).get("count", 0)
    audit_results.append({
        "item": "摘要覆盖率",
        "status": "pass" if sm_count >= ch_count else "warn",
        "detail": f"{sm_count}/{ch_count} 章",
        "confidence": "high" if sm_count >= ch_count else "medium",
    })

    # 6. 伏笔健康（检查严重逾期）
    overdue_threads = _check_overdue_threads(project_root, current_ch)
    audit_results.append({
        "item": "伏笔逾期检查",
        "status": "pass" if len(overdue_threads) == 0 else "warn",
        "detail": f"{len(overdue_threads)} 条逾期" if overdue_threads else "无逾期",
        "confidence": "medium" if overdue_threads else "high",
    })

    # 生成报告
    report = _generate_audit_report(project_root, audit_results, assets)

    migration_dir = _ink_dir(project_root) / "migration"
    migration_dir.mkdir(parents=True, exist_ok=True)
    report_path = migration_dir / "audit_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    # 统计
    passed = sum(1 for r in audit_results if r["status"] == "pass")
    warned = sum(1 for r in audit_results if r["status"] == "warn")
    failed = sum(1 for r in audit_results if r["status"] == "fail")

    print(f"\n迁移审计完成: {passed} 通过 / {warned} 警告 / {failed} 失败")
    print(f"审计报告: {report_path}")

    return 0 if failed == 0 else 1


def _check_overdue_threads(project_root: Path, current_ch: int) -> List[str]:
    db_path = _index_db_path(project_root)
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT thread_id, planted_chapter, expected_payoff_chapter "
            "FROM plot_threads WHERE status = 'active' AND expected_payoff_chapter < ?",
            (current_ch,)
        )
        results = []
        for row in cursor.fetchall():
            delay = current_ch - row[2]
            if delay > 20:
                results.append(f"伏笔 '{row[0]}' (第{row[1]}章埋, 预期第{row[2]}章回收, 已逾期{delay}章)")
        conn.close()
        return results
    except Exception:
        return []


def _generate_audit_report(
    project_root: Path,
    results: List[Dict[str, Any]],
    assets: Dict[str, Any],
) -> str:
    lines = [
        "# 迁移审计报告",
        "",
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 项目路径: {project_root}",
        "",
        "## 审计结果",
        "",
        "| 检查项 | 状态 | 详情 | 置信度 |",
        "|--------|------|------|--------|",
    ]

    status_map = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
    for r in results:
        icon = status_map.get(r["status"], "?")
        lines.append(f"| {r['item']} | {icon} | {r['detail']} | {r['confidence']} |")

    # 置信度分级
    high = [r for r in results if r["confidence"] == "high" and r["status"] == "pass"]
    medium = [r for r in results if r["confidence"] == "medium"]
    low = [r for r in results if r["confidence"] == "low"]

    lines.extend([
        "",
        "## 置信度分级",
        "",
        f"- **高置信（自动完成）**: {len(high)} 项",
        f"- **中置信（建议人工抽查）**: {len(medium)} 项",
        f"- **低置信（需人工确认）**: {len(low)} 项",
    ])

    if low:
        lines.append("")
        lines.append("### 低置信项详情")
        for r in low:
            lines.append(f"- {r['item']}: {r['detail']}")

    lines.extend([
        "",
        "## 推荐操作",
        "",
        "1. 运行 `/ink-resolve` 处理待确认项",
        "2. 运行 `/ink-auto 1` 验证新流程正常",
    ])

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="迁移审计工具")
    parser.add_argument("--project-root", required=True, help="书项目根目录")
    parser.add_argument("command", choices=["discover", "create-tables", "audit"],
                        help="discover=资产发现, create-tables=创建新表, audit=迁移审计")

    args = parser.parse_args()
    project_root = Path(args.project_root)

    if not project_root.is_dir():
        print(f"❌ 目录不存在: {project_root}")
        return 1

    if args.command == "discover":
        return cmd_discover(project_root)
    elif args.command == "create-tables":
        return cmd_create_tables(project_root)
    elif args.command == "audit":
        return cmd_audit(project_root)

    return 2


if __name__ == "__main__":
    sys.exit(main())
